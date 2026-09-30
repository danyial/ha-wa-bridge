const { Client, LocalAuth, MessageMedia, Poll, ScheduledEvent } = require('whatsapp-web.js');
const qrcode = require('qrcode');
const { readOptions, loadConfig, webVersionOptions } = require('./lib/config');
const { loadOrCreateToken } = require('./lib/auth');
const { createBridgeServer, PROTOCOL_VERSION } = require('./lib/server');
const { createCommandHandler } = require('./lib/commands');
const { announce } = require('./lib/discovery');
const { createStatusTracker, createHealthMonitor } = require('./lib/status');
const { createLidResolver, bareId } = require('./lib/ids');
const { createFilter } = require('./lib/filter');
const { createEventBuilder } = require('./lib/events');
const { errorText, isHarmlessRejection } = require('./lib/errors');

const BRIDGE_VERSION = require('./package.json').version;
const WWEBJS_VERSION = require('whatsapp-web.js/package.json').version;
const DATA_PATH = process.env.WA_DATA_PATH || './.wwebjs_auth';
const STARTUP_TIMEOUT_MS = 3 * 60 * 1000;

const {
    authToken,
    port,
    restartUnresponsiveMinutes,
    waWebVersion,
    detectOwnMessages,
    incomingMode,
    allowedGroups,
    allowedGroupsLower,
    allowedNumbers,
    allowedNumbersSet,
    incomingLogLevel,
} = loadConfig(readOptions());

console.log(`WhatsApp Web version: ${waWebVersion || 'live (not pinned)'}`);
console.log(`Incoming messages mode: ${incomingMode}`);
console.log(`Incoming message log level: ${incomingLogLevel}`);
if (allowedGroupsLower.length > 0) {
    console.log(`Allowed groups filter: ${allowedGroups.join(', ')}`);
}
if (detectOwnMessages) {
    console.warn('detect_own_messages is deprecated and has no effect: own messages always reach Home Assistant; choose what to do with them in the integration options');
}
if (allowedNumbersSet.size > 0) {
    console.log(`Allowed numbers filter: ${allowedNumbers.join(', ')}`);
}

// Log incoming messages and votes according to incoming_message_log_level.
function logIncomingData(type, data) {
    if (incomingLogLevel === 'NONE') return;
    const sender = data.sender_phone || data.sender || data.voter_phone || data.voter_id || 'unknown';
    const chat = data.is_group ? ` in ${data.chatName || data.chat_id}` : '';
    if (incomingLogLevel === 'FULL') {
        console.log(`[${type}] from ${sender}${chat}:`, JSON.stringify(data));
    } else {
        console.log(`[${type}] from ${sender}${chat}`);
    }
}

// Initialize WhatsApp Client
const client = new Client({
    authStrategy: new LocalAuth({
        dataPath: DATA_PATH
    }),
    ...webVersionOptions({ waWebVersion }),
    puppeteer: {
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote', 
            '--disable-gpu',
            '--disable-extensions',
            '--disable-software-rasterizer',
        ],
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined
    },
    // How long whatsapp-web.js waits for WhatsApp Web to load. It treats 0 as
    // "use the default" (30 s), not as "forever" (upstream relied on that);
    // a first start on a small VM takes longer and then looped on
    // "auth timeout".
    authTimeoutMs: STARTUP_TIMEOUT_MS,
});

// Own account: phone id on ready, LID resolved once (notes to self, #6).
const me = { phone: null, lid: null };
const resolver = createLidResolver({ lookup: (ids) => client.getContactLidAndPhone(ids) });
const events = createEventBuilder({ client, resolver, me: () => me });
const shouldForward = createFilter({ incomingMode, allowedGroupsLower, allowedNumbersSet });

let lastQr = null;
let shuttingDown = false;
let restarting = false;
let unresponsiveTimer = null;

const { token, source: tokenSource } = loadOrCreateToken({ configured: authToken, dir: DATA_PATH });
console.log(`Auth token: ${tokenSource === 'configured' ? 'from configuration' : `stored in ${DATA_PATH}/auth_token`}`);

// Declared before the tracker, which broadcasts through it.
let broadcast = () => {};
const status = createStatusTracker({ emit: (frame) => broadcast(frame) });

// Engine probe: browser and page alive, and the WhatsApp socket state
// readable within the timeout. A hung page never answers the evaluate.
const health = createHealthMonitor({
    probe: async () => {
        if (!client.pupBrowser?.isConnected()) throw new Error('browser disconnected');
        if (!client.pupPage || client.pupPage.isClosed()) throw new Error('page closed');
        return client.getState();
    },
    onState: (waState) => {
        if (status.status === 'ready') status.set('ready', { wa_state: waState });
    },
    onUnresponsive: (err) => {
        console.warn(`WhatsApp Web reports ready but does not answer (${errorText(err)}); restart the add-on if this persists`);
        status.set('unresponsive', { reason: errorText(err) });
        if (restartUnresponsiveMinutes > 0) {
            unresponsiveTimer = setTimeout(() => {
                if (status.status === 'unresponsive') restartClient('unresponsive');
            }, restartUnresponsiveMinutes * 60 * 1000);
        }
    },
    onRecovered: (waState) => {
        console.log('WhatsApp Web answers again');
        clearTimeout(unresponsiveTimer);
        status.set('ready', { wa_state: waState, reason: null });
    },
});
const handleCommand = createCommandHandler({
    client,
    wwebjs: { MessageMedia, Poll, ScheduledEvent },
    isReady: () => status.status === 'ready',
    actions: {
        status: () => status.snapshot(),
        restart: () => restartClient('requested'),
        logout: async () => {
            if (!['ready', 'unresponsive', 'authenticated'].includes(status.status)) {
                throw new Error('not linked');
            }
            console.warn('Logging out and unlinking this device (requested)');
            restarting = true;
            try {
                await client.logout();
            } finally {
                restarting = false;
            }
            await restartClient('logged out');
        },
    },
});

const bridge = createBridgeServer({
    port,
    token,
    onConnection: (send) => {
        send({
            type: 'hello',
            protocol: PROTOCOL_VERSION,
            bridge_version: BRIDGE_VERSION,
            wwebjs_version: WWEBJS_VERSION,
        });
        send({ type: 'status', ...status.snapshot() });
        if (status.status === 'qr' && lastQr) send({ type: 'qr', data: lastQr });
    },
    onCommand: handleCommand,
});
broadcast = bridge.broadcast;

// Close the browser and initialize again (new QR if the session is gone).
async function restartClient(reason) {
    if (restarting || shuttingDown) return;
    restarting = true;
    console.log(`Restarting WhatsApp client (${reason})`);
    health.stop();
    clearTimeout(unresponsiveTimer);
    lastQr = null;
    status.set('initializing', { reason, phone: status.snapshot().phone ?? null });
    try {
        await client.destroy();
    } catch (err) {
        console.error('Error closing the browser:', errorText(err));
    }
    restarting = false;
    await startClient();
}

// WhatsApp Client Events
client.on('qr', (qr) => {
    console.log('QR Code received');
    lastQr = qr;
    status.set('qr', { reason: null });
    // Generate terminal QR for local debugging logs
    qrcode.toString(qr, { type: 'terminal', small: true }, function (err, url) {
        if (!err) console.log(url);
    });
    
    broadcast({ type: 'qr', data: qr });
});

client.on('ready', () => {
    console.log('WhatsApp Client is ready!');
    lastQr = null;
    me.phone = bareId(client.info?.wid?._serialized) ?? null;
    status.set('ready', { phone: client.info?.wid?.user ?? null, reason: null });
    health.start();
    resolver.lidOf(me.phone).then((lid) => {
        me.lid = lid;
    });
});

client.on('authenticated', () => {
    console.log('Authenticated');
    lastQr = null;
    status.set('authenticated', { reason: null });
});

client.on('auth_failure', msg => {
    console.error('AUTHENTICATION FAILURE', msg);
    status.set('auth_failure', { reason: String(msg) });
});

// Logged out on the phone, or the session was lost: report it and start over,
// which shows a new QR code. Without this the bridge kept reporting "ready".
client.on('disconnected', async (reason) => {
    if (restarting) return;
    console.warn('WhatsApp disconnected:', reason);
    health.stop();
    status.set('disconnected', { reason: String(reason), phone: null, wa_state: null });
    await restartClient(`disconnected: ${reason}`);
});

client.on('vote_update', async (vote) => {
    try {
        const data = await events.vote(vote);
        const forward = shouldForward({
            isGroup: data.is_group,
            chatName: data.chatName,
            senderPhone: data.voter_phone,
        });
        if (!forward) return;
        logIncomingData('VOTE', data);
        broadcast({ type: 'poll_vote', data });
    } catch (err) {
        console.error('Dropping poll vote, could not process it:', errorText(err));
    }
});

if (incomingMode !== 'disabled') {
    client.on('message_create', async (msg) => {
        try {
            const data = await events.message(msg);
            // Own messages always go to Home Assistant, which decides with its
            // "own messages" option (off / notes to self / all). The incoming
            // filters are about other people's messages.
            const forward =
                msg.fromMe ||
                shouldForward({
                    isGroup: data.is_group,
                    chatName: data.chatName,
                    senderPhone: data.sender_phone,
                });
            if (!forward) return;
            logIncomingData('MESSAGE', data);
            broadcast({ type: 'message', data });
        } catch (err) {
            // Fail closed: a message we cannot inspect is not forwarded.
            console.error('Dropping message, could not process it:', errorText(err));
        }
    });
} else {
    console.log('Incoming messages are disabled; the bridge only sends.');
}

// Start the client. Failures (Chromium crash, network down at boot) are
// retried with backoff instead of exiting: the add-on has no watchdog, so an
// exit would leave WhatsApp down until someone restarts it.
const RETRY_MIN_MS = 10 * 1000;
const RETRY_MAX_MS = 5 * 60 * 1000;
let retryMs = RETRY_MIN_MS;

async function startClient() {
    if (shuttingDown) return;
    console.log('Initializing WhatsApp client...');
    try {
        await client.initialize();
        retryMs = RETRY_MIN_MS;
    } catch (err) {
        console.error(`Failed to initialize client, retrying in ${retryMs / 1000}s: ${errorText(err)}`);
        try {
            await client.destroy();
        } catch {
            // Browser may not have started at all.
        }
        setTimeout(startClient, retryMs);
        retryMs = Math.min(retryMs * 2, RETRY_MAX_MS);
    }
}

process.on('unhandledRejection', (err) => {
    if (isHarmlessRejection(err)) {
        console.log(`Ignored whatsapp-web.js cache read error: ${errorText(err)}`);
        return;
    }
    console.error('Unhandled rejection:', err);
});

// The Supervisor sends SIGTERM on stop and kills after a grace period; close
// Chromium cleanly so its profile locks do not outlive the container.
async function shutdown(signal) {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`${signal} received, shutting down`);
    health.stop();
    const force = setTimeout(() => process.exit(0), 8000);
    force.unref();
    try {
        await bridge.close();
        await client.destroy();
    } catch (err) {
        console.error('Error during shutdown:', errorText(err));
    }
    process.exit(0);
}
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

async function main() {
    const listening = await bridge.listen();
    console.log(`WebSocket server listening on port ${listening} (token required)`);
    try {
        await announce({ port: listening, token });
    } catch (err) {
        console.error('Discovery failed (set up the integration manually):', errorText(err));
    }
    await startClient();
}

main();
