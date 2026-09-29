'use strict';

const http = require('http');
const { WebSocketServer } = require('ws');

const { authorized } = require('./auth');

const PROTOCOL_VERSION = 2;

// Errors a command handler throws on purpose; the message goes to the client.
class CommandError extends Error {
    constructor(code, message) {
        super(message || code);
        this.code = code;
    }
}

// WebSocket server for the Home Assistant integration.
//
// - Every connection must authenticate during the HTTP upgrade with
//   "Authorization: Bearer <token>"; anything else gets 401 and no socket.
// - A command may carry an `id`; the server then answers with
//   {type: 'result', id, ok, data?, error?, code?}. Commands without `id`
//   (older clients) get no result frame.
// - Dead peers are dropped by a ping/pong heartbeat.
function createBridgeServer({
    port,
    host,
    token,
    maxPayload = 20 * 1024 * 1024,
    heartbeatMs = 30000,
    onConnection = () => {},
    onCommand,
    log = console,
}) {
    const server = http.createServer((req, res) => {
        res.writeHead(426, { 'Content-Type': 'text/plain' });
        res.end('WebSocket only\n');
    });
    const wss = new WebSocketServer({ noServer: true, maxPayload });

    server.on('upgrade', (req, socket, head) => {
        if (!authorized(req.headers.authorization, token)) {
            log.warn(`Rejected unauthenticated connection from ${req.socket.remoteAddress}`);
            socket.write('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n');
            socket.destroy();
            return;
        }
        wss.handleUpgrade(req, socket, head, (ws) => wss.emit('connection', ws, req));
    });

    wss.on('connection', (ws, req) => {
        log.log(`Client connected from ${req.socket.remoteAddress}`);
        ws.isAlive = true;
        ws.on('pong', () => {
            ws.isAlive = true;
        });
        ws.on('error', (err) => log.error('WebSocket error:', err.message));
        ws.on('close', () => log.log('Client disconnected'));
        ws.on('message', (raw) => handleMessage(ws, raw));
        onConnection((frame) => send(ws, frame));
    });

    async function handleMessage(ws, raw) {
        let cmd;
        try {
            cmd = JSON.parse(raw);
        } catch {
            log.error('Ignoring frame that is not JSON');
            return;
        }
        if (!cmd || typeof cmd.type !== 'string') {
            log.error('Ignoring frame without type');
            return;
        }
        const id = cmd.id;
        log.log(`Command ${cmd.type}${id !== undefined ? ` (id ${id})` : ''}`);
        try {
            const data = await onCommand(cmd, (frame) => send(ws, frame));
            if (id !== undefined) send(ws, { type: 'result', id, ok: true, data: data ?? null });
        } catch (err) {
            const code = err instanceof CommandError ? err.code : 'internal_error';
            log.error(`Command ${cmd.type} failed: ${err.message}`);
            if (id !== undefined) {
                send(ws, { type: 'result', id, ok: false, code, error: err.message });
            }
        }
    }

    function send(ws, frame) {
        if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(frame));
    }

    function broadcast(frame) {
        for (const ws of wss.clients) send(ws, frame);
    }

    const heartbeat = setInterval(() => {
        for (const ws of wss.clients) {
            if (!ws.isAlive) {
                ws.terminate();
                continue;
            }
            ws.isAlive = false;
            ws.ping();
        }
    }, heartbeatMs);
    heartbeat.unref();

    function listen() {
        return new Promise((resolve, reject) => {
            server.once('error', reject);
            server.listen(port, host, () => {
                server.off('error', reject);
                resolve(server.address().port);
            });
        });
    }

    async function close() {
        clearInterval(heartbeat);
        for (const ws of wss.clients) ws.terminate();
        await new Promise((resolve) => wss.close(resolve));
        await new Promise((resolve) => server.close(resolve));
    }

    return { listen, close, broadcast, clients: wss.clients };
}

module.exports = { createBridgeServer, CommandError, PROTOCOL_VERSION };
