'use strict';

const fs = require('fs');

// Read the add-on options written by the Supervisor. Missing or unreadable
// options fall back to environment variables (standalone Docker).
function readOptions(path = '/data/options.json') {
    try {
        if (fs.existsSync(path)) {
            return JSON.parse(fs.readFileSync(path, 'utf8'));
        }
    } catch (err) {
        console.error('Error reading options.json:', err);
    }
    return {};
}

// Accept a list or a comma-separated string (env vars).
function toList(value) {
    if (typeof value === 'string') {
        return value.split(',').map(v => v.trim()).filter(Boolean);
    }
    return value;
}

function loadConfig(options = {}, env = process.env) {
    const detectOwnMessages = options.detect_own_messages || env.DETECT_OWN_MESSAGES === 'true' || false;

    // Mode: 'all' (default) | 'disabled' | 'groups_only' | 'numbers_only'
    const incomingMode = options.incoming_messages_mode || env.INCOMING_MESSAGES_MODE || 'all';

    // Group names to forward (groups_only mode, and as a filter in 'all' mode).
    const allowedGroups = toList(options.allowed_groups || env.ALLOWED_GROUPS || []);
    const allowedGroupsLower = allowedGroups.map(g => g.toLowerCase());

    // Phone numbers in international format without '+', e.g. "40741234567".
    const allowedNumbers = toList(options.allowed_numbers || env.ALLOWED_NUMBERS || []);
    const allowedNumbersSet = new Set(allowedNumbers.map(n => `${n}@c.us`));

    // Mode: 'FULL' (default) | 'COMPACT' | 'NONE'
    const incomingLogLevel = (options.incoming_message_log_level || env.INCOMING_MESSAGE_LOG_LEVEL || 'FULL').toUpperCase();

    // Optional emergency pin of the WhatsApp Web version, e.g. "2.3000.1017054665".
    // Empty: always load the live version.
    const waWebVersion = (options.wa_web_version || env.WA_WEB_VERSION || '').trim();

    return {
        waWebVersion,
        detectOwnMessages,
        incomingMode,
        allowedGroups,
        allowedGroupsLower,
        allowedNumbers,
        allowedNumbersSet,
        incomingLogLevel,
    };
}

const WA_VERSION_URL = 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/{version}.html';

// whatsapp-web.js options selecting the WhatsApp Web version. By default the
// live version is loaded and nothing is cached: a pinned version breaks as
// soon as WhatsApp retires it.
function webVersionOptions({ waWebVersion }) {
    if (!waWebVersion) {
        return { webVersionCache: { type: 'none' } };
    }
    return {
        webVersion: waWebVersion,
        webVersionCache: { type: 'remote', remotePath: WA_VERSION_URL, strict: true },
    };
}

module.exports = { readOptions, loadConfig, webVersionOptions };
