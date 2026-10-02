'use strict';

const { bareId, serialize, isGroup } = require('./ids');
const { withTimeout } = require('./status');

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 50;
// Searching all chats can take a while on a small VM; stays below the
// integration's request timeout (60 s).
const TIMEOUT_MS = 45000;

function clampLimit(value) {
    const limit = Number.parseInt(value, 10);
    if (!Number.isFinite(limit) || limit < 1) return DEFAULT_LIMIT;
    return Math.min(limit, MAX_LIMIT);
}

// Plain data for messages from search or chat history: who wrote what, when,
// in which chat. Media is not downloaded.
async function summarize(messages, { client, resolver, me, log = console }) {
    const names = new Map();
    async function chatName(chatId) {
        if (!names.has(chatId)) {
            names.set(
                chatId,
                client
                    .getChatById(chatId)
                    .then((chat) => chat?.name ?? null)
                    .catch((err) => {
                        log.warn?.(`Chat ${chatId} not found: ${err.message}`);
                        return null;
                    }),
            );
        }
        return names.get(chatId);
    }

    const result = [];
    for (const msg of messages) {
        const from = bareId(msg.from);
        const to = bareId(msg.to);
        const group = isGroup(from) || isGroup(to);
        const chatId = group ? (isGroup(from) ? from : to) : msg.fromMe ? to : from;
        const sender = bareId(msg.fromMe ? me().phone : msg.author || msg.from);
        result.push({
            id: serialize(msg.id),
            chat_id: chatId,
            chat_name: chatId ? await chatName(chatId) : null,
            is_group: group,
            sender,
            sender_phone: sender ? await resolver.phoneOf(sender) : null,
            fromMe: Boolean(msg.fromMe),
            body: msg.body ?? '',
            type: msg.type ?? null,
            hasMedia: Boolean(msg.hasMedia),
            timestamp: msg.timestamp ?? null,
        });
    }
    return result;
}

module.exports = { summarize, clampLimit, DEFAULT_LIMIT, MAX_LIMIT, TIMEOUT_MS, withTimeout };
