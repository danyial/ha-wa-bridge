'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const WebSocket = require('ws');

const { createBridgeServer, CommandError } = require('../lib/server');

const TOKEN = 't0ken';
const quiet = { log() {}, warn() {}, error() {} };

async function start(options = {}) {
    const bridge = createBridgeServer({
        port: 0,
        host: '127.0.0.1',
        token: TOKEN,
        log: quiet,
        onConnection: (send) => send({ type: 'hello' }),
        onCommand: async (cmd, reply) => {
            if (cmd.type === 'echo') return { echo: cmd.value };
            if (cmd.type === 'reply') {
                reply({ type: 'legacy_response' });
                return null;
            }
            if (cmd.type === 'fail') throw new CommandError('bad_thing', 'went wrong');
            throw new Error('boom');
        },
        ...options,
    });
    const port = await bridge.listen();
    return { bridge, url: `ws://127.0.0.1:${port}` };
}

function connect(url, token, options = {}) {
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const ws = new WebSocket(url, { headers, ...options });
    const frames = [];
    const waiters = [];
    ws.on('message', (raw) => {
        frames.push(JSON.parse(raw));
        while (waiters.length) waiters.shift()();
    });
    ws.next = async () => {
        while (!frames.length) await new Promise((resolve) => waiters.push(resolve));
        return frames.shift();
    };
    return ws;
}

function rejection(ws) {
    return new Promise((resolve) => {
        ws.on('unexpected-response', (req, res) => resolve(res.statusCode));
        ws.on('error', () => {});
    });
}

test('rejects missing and wrong tokens with 401', async () => {
    const { bridge, url } = await start();
    assert.equal(await rejection(connect(url)), 401);
    assert.equal(await rejection(connect(url, 'wrong')), 401);
    await bridge.close();
});

test('accepts the token, greets, answers commands by id', async () => {
    const { bridge, url } = await start();
    const ws = connect(url, TOKEN);
    assert.deepEqual(await ws.next(), { type: 'hello' });

    ws.send(JSON.stringify({ type: 'echo', id: 1, value: 42 }));
    assert.deepEqual(await ws.next(), { type: 'result', id: 1, ok: true, data: { echo: 42 } });

    ws.send(JSON.stringify({ type: 'fail', id: 2 }));
    assert.deepEqual(await ws.next(), {
        type: 'result',
        id: 2,
        ok: false,
        code: 'bad_thing',
        error: 'went wrong',
    });

    ws.send(JSON.stringify({ type: 'crash', id: 3 }));
    const crash = await ws.next();
    assert.equal(crash.ok, false);
    assert.equal(crash.code, 'internal_error');

    // Legacy clients: no id, no result frame, but *_response frames still come.
    ws.send(JSON.stringify({ type: 'reply' }));
    ws.send(JSON.stringify({ type: 'echo', id: 4, value: 'after' }));
    assert.deepEqual(await ws.next(), { type: 'legacy_response' });
    assert.deepEqual((await ws.next()).id, 4);

    ws.close();
    await bridge.close();
});

test('broadcast reaches authenticated clients', async () => {
    const { bridge, url } = await start();
    const ws = connect(url, TOKEN);
    await ws.next();
    bridge.broadcast({ type: 'message', data: { body: 'hi' } });
    assert.deepEqual(await ws.next(), { type: 'message', data: { body: 'hi' } });
    ws.close();
    await bridge.close();
});

test('oversized frames close the connection', async () => {
    const { bridge, url } = await start({ maxPayload: 1024 });
    const ws = connect(url, TOKEN);
    await ws.next();
    const closed = new Promise((resolve) => ws.on('close', (code) => resolve(code)));
    ws.send(JSON.stringify({ type: 'echo', id: 1, value: 'x'.repeat(4096) }));
    assert.equal(await closed, 1009);
    await bridge.close();
});

test('heartbeat drops peers that stop answering pings', async () => {
    const { bridge, url } = await start({ heartbeatMs: 50 });
    try {
        // autoPong: false makes this client ignore the server's pings.
        const ws = connect(url, TOKEN, { autoPong: false });
        await ws.next();
        await new Promise((resolve) => ws.on('close', resolve));
        // The server drops the socket from its set on its own close event.
        for (let i = 0; i < 50 && bridge.clients.size > 0; i++) {
            await new Promise((resolve) => setTimeout(resolve, 10));
        }
        assert.equal(bridge.clients.size, 0);
    } finally {
        await bridge.close();
    }
});

test('heartbeat keeps healthy peers', async () => {
    const { bridge, url } = await start({ heartbeatMs: 30 });
    try {
        const ws = connect(url, TOKEN);
        await ws.next();
        await new Promise((resolve) => setTimeout(resolve, 200));
        assert.equal(ws.readyState, WebSocket.OPEN);
        ws.close();
    } finally {
        await bridge.close();
    }
});
