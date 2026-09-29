const { Client, LocalAuth, MessageMedia, Poll, ScheduledEvent } = require('whatsapp-web.js');
const qrcode = require('qrcode');
const { readOptions, loadConfig, webVersionOptions } = require('./lib/config');
const { loadOrCreateToken } = require('./lib/auth');
const { createBridgeServer, PROTOCOL_VERSION } = require('./lib/server');
const { createCommandHandler } = require('./lib/commands');
const { announce } = require('./lib/discovery');
const { createStatusTracker, createHealthMonitor } = require('./lib/status');

const BRIDGE_VERSION = require('./package.json').version;
const WWEBJS_VERSION = require('whatsapp-web.js/package.json').version;
const DATA_PATH = process.env.WA_DATA_PATH || './.wwebjs_auth';

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
if (allowedNumbersSet.size > 0) {
    console.log(`Allowed numbers filter: ${allowedNumbers.join(', ')}`);
}

// Helper to log incoming data based on log level
function logIncomingData(type, data, rawObj) {
    if (incomingLogLevel === 'NONE') return;

    if (incomingLogLevel === 'COMPACT') {
        const sender = data.from || data.voter || 'unknown';
        const group = data.isGroup ? ` (Group: ${data.chatName})` : (data.group_id ? ` (Group ID: ${data.group_id})` : '');
        console.log(`[${type}] received from ${sender}${group}`);
    } else {
        // FULL logging
        console.log(`[${type}] RECEIVED`, rawObj);
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
    authTimeoutMs: 0 // Wait indefinitely for QR scan
});

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
        console.warn(`WhatsApp Web reports ready but does not answer (${err.message}); restart the add-on if this persists`);
        status.set('unresponsive', { reason: err.message });
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
        console.error('Error closing the browser:', err.message);
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
    status.set('ready', { phone: client.info?.wid?.user ?? null, reason: null });
    health.start();
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

client.on('vote_update', async vote => {

    let parentMsgId = null;
    let groupId = null;
    let voter = vote.voter;
    let isGroup = false;
    let chatName = '';
    
    // Extract purely the phone number from the JID format
    if (voter && typeof voter === 'string') {
        voter = voter.split('@')[0];
        if (voter.includes(':')) {
            voter = voter.split(':')[0];
        }
    }
    
    if (vote.parentMessage) {
        if (vote.parentMessage.id && vote.parentMessage.id._serialized) {
            parentMsgId = vote.parentMessage.id._serialized;
        }
        
        let to = vote.parentMessage.to;
        if (to) {
            isGroup = to.includes('@g.us');
            if (isGroup) {
               groupId = to.split('@')[0];
            }
        }
        
        // We need the chat name for group filtering
        try {
            const chat = await client.getChatById(to || vote.parentMessage.id.remote);
            chatName = chat.name;
            isGroup = chat.isGroup;
        } catch (err) {
            console.error('Error fetching chat info for poll vote:', err);
        }
    }
    
    // groups_only mode: skip non-group votes
    if (incomingMode === 'groups_only' && !isGroup) {
        return;
    }

    // numbers_only mode: skip group votes and votes not from allowed numbers
    if (incomingMode === 'numbers_only') {
        if (isGroup || !allowedNumbersSet.has(`${voter}@c.us`)) {
            return;
        }
    }

    // allowed_groups filter: skip votes from groups not in the list
    if (allowedGroupsLower.length > 0) {
        if (!isGroup || !allowedGroupsLower.includes((chatName || '').toLowerCase())) {
            return;
        }
    }

    // allowed_numbers filter: skip votes from numbers not in the list
    if (allowedNumbersSet.size > 0 && incomingMode !== 'numbers_only') {
        if (isGroup || !allowedNumbersSet.has(`${voter}@c.us`)) {
            return;
        }
    }

    const payloadData = {
        voter: voter,
        group_id: groupId,
        selectedOptions: vote.selectedOptions,
        pollCreationMessageId: parentMsgId,
        timestamp: vote.timestamp
    };

    logIncomingData('VOTE_UPDATE', payloadData, vote);

    broadcast({
        type: 'poll_vote',
        data: payloadData
    });
});

if (incomingMode !== 'disabled') {
    client.on('message_create', async msg => {
        // If detect_own_messages is false, ignore messages sent by the bot itself
        if (msg.fromMe && !detectOwnMessages) {
            return;
        }

        let chatInfo = {};
        try {
            const chat = await msg.getChat();
            chatInfo = {
                chatName: chat.name,
                isGroup: chat.isGroup,
                groupId: chat.isGroup ? chat.id._serialized : null
            };

            // groups_only mode: skip non-group messages
            if (incomingMode === 'groups_only' && !chat.isGroup) {
                return;
            }

            // numbers_only mode: skip group messages and messages not from allowed numbers
            if (incomingMode === 'numbers_only') {
                if (chat.isGroup || (!allowedNumbersSet.has(msg.from) && !allowedNumbersSet.has(msg.author))) {
                    return;
                }
            }

            // allowed_groups filter: skip messages from groups not in the list
            if (allowedGroupsLower.length > 0) {
                if (!chat.isGroup || !allowedGroupsLower.includes(chat.name.toLowerCase())) {
                    return;
                }
            }

            // allowed_numbers filter: skip messages from numbers not in the list
            if (allowedNumbersSet.size > 0 && incomingMode !== 'numbers_only') {
                if (chat.isGroup || (!allowedNumbersSet.has(msg.from) && !allowedNumbersSet.has(msg.author))) {
                    return;
                }
            }
        } catch (err) {
            console.error('Error fetching chat info:', err);
        }

        const payloadData = {
            from: msg.from,
            to: msg.to,
            body: msg.body,
            timestamp: msg.timestamp,
            hasMedia: msg.hasMedia,
            author: msg.author,
            deviceType: msg.deviceType,
            isForwarded: msg.isForwarded,
            fromMe: msg.fromMe,
            ...chatInfo
        };

        logIncomingData('MESSAGE', payloadData, msg);

        // Broadcast incoming message to HA
        broadcast({
            type: 'message',
            data: payloadData
        });
    });
} else {
    console.log('Incoming message handling is DISABLED. The bridge will not forward any received messages to Home Assistant.');
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
        console.error(`Failed to initialize client, retrying in ${retryMs / 1000}s:`, err.message);
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
        console.error('Error during shutdown:', err.message);
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
        console.error('Discovery failed (set up the integration manually):', err.message);
    }
    await startClient();
}

main();
