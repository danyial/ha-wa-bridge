'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { announce } = require('../lib/discovery');

const quiet = { log() {} };

test('skips outside the Supervisor', async () => {
    assert.equal(await announce({ port: 3000, token: 't', env: {}, log: quiet }), null);
});

test('announces hostname, port and token', async () => {
    const calls = [];
    const fetchImpl = async (url, init = {}) => {
        calls.push({ url, init });
        if (url.endsWith('/addons/self/info')) {
            return { ok: true, json: async () => ({ data: { hostname: 'abcd1234-ha-wa-bridge' } }) };
        }
        return { ok: true, json: async () => ({}) };
    };
    const result = await announce({
        port: 3000,
        token: 'secret',
        env: { SUPERVISOR_TOKEN: 'sv' },
        fetchImpl,
        log: quiet,
    });
    assert.deepEqual(result, { host: 'abcd1234-ha-wa-bridge', port: 3000 });
    assert.equal(calls[0].init.headers.Authorization, 'Bearer sv');
    assert.equal(calls[1].url, 'http://supervisor/discovery');
    assert.deepEqual(JSON.parse(calls[1].init.body), {
        service: 'whatsapp',
        config: { host: 'abcd1234-ha-wa-bridge', port: 3000, token: 'secret' },
    });
});

test('raises on Supervisor errors', async () => {
    const fetchImpl = async () => ({ ok: false, status: 403 });
    await assert.rejects(
        announce({ port: 3000, token: 't', env: { SUPERVISOR_TOKEN: 'sv' }, fetchImpl, log: quiet }),
        /HTTP 403/,
    );
});
