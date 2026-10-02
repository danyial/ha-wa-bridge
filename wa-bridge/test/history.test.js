'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { createCommandHandler } = require('../lib/commands');
const { clampLimit, MAX_LIMIT, DEFAULT_LIMIT } = require('../lib/history');

const ME = '491700000009@c.us';
const LID = '123456789012345@lid';
const PHONE = '491700000001@c.us';
const GROUP = '120363000000000001@g.us';

function message(fields) {
    return { id: { _serialized: `m-${fields.body}` }, timestamp: 100, type: 'chat', ...fields };
}

const MESSAGES = [
    message({ from: LID, to: ME, body: 'Paket ist da' }),
    message({ from: GROUP, to: ME, author: LID, body: 'Paket abgeholt?' }),
    message({ from: ME, to: PHONE, fromMe: true, body: 'Paket kommt morgen', hasMedia: true }),
];

function setup({ ready = true, found = MESSAGES, chatMessages = MESSAGES } = {}) {
    const calls = [];
    const chats = {
        [GROUP]: { isGroup: true, name: 'Familie', id: { _serialized: GROUP } },
        [LID]: { isGroup: false, name: 'Anna' },
        [PHONE]: {
            isGroup: false,
            name: 'Bob',
            fetchMessages: async (opts) => {
                calls.push(['fetch', opts]);
                return chatMessages;
            },
        },
    };
    const client = {
        getChats: async () => Object.values(chats).filter((c) => c.id),
        getChatById: async (id) => {
            calls.push(['chat', id]);
            if (!chats[id]) throw new Error('not found');
            return chats[id];
        },
        searchMessages: async (query, opts) => {
            calls.push(['search', query, opts]);
            return found;
        },
    };
    const handle = createCommandHandler({
        client,
        wwebjs: { MessageMedia: class {}, Poll: class {}, ScheduledEvent: class {} },
        isReady: () => ready,
        resolver: { phoneOf: async (id) => (id === LID ? PHONE : id?.endsWith('@c.us') ? id : null) },
        me: () => ({ phone: ME }),
        log: { log() {}, warn() {} },
    });
    return { handle: (cmd) => handle(cmd, () => {}), calls };
}

test('clampLimit', () => {
    assert.equal(clampLimit(undefined), DEFAULT_LIMIT);
    assert.equal(clampLimit(0), DEFAULT_LIMIT);
    assert.equal(clampLimit('5'), 5);
    assert.equal(clampLimit(1000), MAX_LIMIT);
});

test('search_messages across all chats', async () => {
    const { handle, calls } = setup();
    const result = await handle({ type: 'search_messages', query: ' Paket ', limit: 10 });
    assert.equal(result.query, 'Paket');
    assert.equal(result.chat_id, null);
    assert.deepEqual(calls.find((c) => c[0] === 'search'), ['search', 'Paket', { chatId: undefined, limit: 10 }]);

    const [direct, group, own] = result.messages;
    assert.deepEqual(direct, {
        id: 'm-Paket ist da',
        chat_id: LID,
        chat_name: 'Anna',
        is_group: false,
        sender: LID,
        sender_phone: PHONE,
        fromMe: false,
        body: 'Paket ist da',
        type: 'chat',
        hasMedia: false,
        timestamp: 100,
    });
    assert.equal(group.chat_id, GROUP);
    assert.equal(group.chat_name, 'Familie');
    assert.equal(group.sender_phone, PHONE);
    assert.equal(own.sender, ME);
    assert.equal(own.chat_id, PHONE);
    assert.equal(own.hasMedia, true);
    // One lookup per chat, not per message.
    assert.equal(calls.filter((c) => c[0] === 'chat').length, 3);
});

test('search_messages in one chat, limit capped', async () => {
    const { handle, calls } = setup();
    const result = await handle({ type: 'search_messages', query: 'x', group_name: 'familie', limit: 500 });
    assert.equal(result.chat_id, GROUP);
    assert.deepEqual(calls.find((c) => c[0] === 'search')[2], { chatId: GROUP, limit: 50 });
});

test('search_messages validation and readiness', async () => {
    await assert.rejects(setup().handle({ type: 'search_messages', query: '  ' }), (e) => e.code === 'invalid_request');
    await assert.rejects(setup({ ready: false }).handle({ type: 'search_messages', query: 'x' }), (e) => e.code === 'not_ready');
});

test('get_messages: last N of a chat', async () => {
    const { handle, calls } = setup();
    const result = await handle({ type: 'get_messages', number: PHONE, limit: 2 });
    assert.equal(result.chat_id, PHONE);
    assert.equal(result.chat_name, 'Bob');
    assert.deepEqual(calls.find((c) => c[0] === 'fetch'), ['fetch', { limit: 2 }]);
    assert.deepEqual(result.messages.map((m) => m.body), ['Paket abgeholt?', 'Paket kommt morgen']);
});

test('get_messages needs a chat', async () => {
    await assert.rejects(setup().handle({ type: 'get_messages' }), (e) => e.code === 'no_target');
});
