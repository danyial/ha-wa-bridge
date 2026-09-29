'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { createCommandHandler } = require('../lib/commands');

class MessageMedia {
    constructor(mimetype, data, filename) {
        Object.assign(this, { mimetype, data, filename });
    }
}
class Poll {
    constructor(question, options, extra) {
        Object.assign(this, { question, options, extra });
    }
}
class ScheduledEvent {
    constructor(name, start, options) {
        Object.assign(this, { name, start, options });
    }
}

function group(id, name) {
    return { isGroup: true, name, id: { _serialized: id } };
}

function setup({ ready = true, chats = [] } = {}) {
    const sent = [];
    const client = {
        getChats: async () => chats,
        getChatById: async (id) => chats.find((c) => c.id._serialized === id) || { isGroup: false },
        sendMessage: async (chatId, content, options) => {
            sent.push({ chatId, content, options });
            return { id: { _serialized: `msg-${sent.length}` } };
        },
    };
    const replies = [];
    const handle = createCommandHandler({
        client,
        wwebjs: { MessageMedia, Poll, ScheduledEvent },
        isReady: () => ready,
        log: { log() {} },
    });
    return { handle: (cmd) => handle(cmd, (f) => replies.push(f)), sent, replies };
}

async function rejectsWith(promise, code) {
    await assert.rejects(promise, (err) => err.code === code);
}

test('send_message to a number: digits only', async () => {
    const { handle, sent } = setup();
    const result = await handle({ type: 'send_message', number: '+49 170-0000001', message: 'hi' });
    assert.deepEqual(result, { chat_id: '491700000001@c.us', message_id: 'msg-1' });
    assert.equal(sent[0].content, 'hi');
});

test('send_message: group_id beats group_name beats number', async () => {
    const chats = [group('111@g.us', 'Familie')];
    const { handle, sent } = setup({ chats });
    await handle({ type: 'send_message', group_id: '222', group_name: 'Familie', number: '49', message: 'a' });
    await handle({ type: 'send_message', group_name: 'familie', number: '49', message: 'b' });
    assert.deepEqual(sent.map((s) => s.chatId), ['222@g.us', '111@g.us']);
});

test('send_message: ambiguous or unknown group name is an error', async () => {
    const chats = [group('1@g.us', 'Haus'), group('2@g.us', 'haus')];
    const { handle, sent } = setup({ chats });
    await rejectsWith(handle({ type: 'send_message', group_name: 'Haus', message: 'x' }), 'ambiguous_group');
    await rejectsWith(handle({ type: 'send_message', group_name: 'Nope', message: 'x' }), 'group_not_found');
    assert.equal(sent.length, 0);
});

test('send_message: media with caption, validation', async () => {
    const { handle, sent } = setup();
    await handle({
        type: 'send_message',
        number: '49',
        message: 'cap',
        media: { mimetype: 'image/png', data: 'AAAA', filename: 'a.png' },
    });
    assert.ok(sent[0].content instanceof MessageMedia);
    assert.deepEqual(sent[0].options, { caption: 'cap' });
    await rejectsWith(handle({ type: 'send_message', number: '49', media: { data: 1 } }), 'invalid_media');
    await rejectsWith(handle({ type: 'send_message', number: '49' }), 'empty_message');
    await rejectsWith(handle({ type: 'send_message', message: 'x' }), 'no_target');
    await rejectsWith(handle({ type: 'send_message', number: 'abc', message: 'x' }), 'invalid_number');
});

test('commands need a ready client', async () => {
    const { handle, replies } = setup({ ready: false });
    await rejectsWith(handle({ type: 'send_message', number: '49', message: 'x' }), 'not_ready');
    await rejectsWith(handle({ type: 'get_groups' }), 'not_ready');
    // Legacy response frame still sent for old integrations.
    assert.deepEqual(replies[0].type, 'get_groups_response');
    assert.deepEqual(await handle({ type: 'ping' }), { pong: true });
});

test('unknown command', async () => {
    const { handle } = setup();
    await rejectsWith(handle({ type: 'rm_rf' }), 'unknown_command');
});

test('broadcast: group names, numbers, partial failure', async () => {
    const chats = [group('1@g.us', 'Familie'), group('2@g.us', 'Doppelt'), group('3@g.us', 'doppelt')];
    const { handle, sent } = setup({ chats });
    const result = await handle({ type: 'broadcast', targets: ['Familie', '4917', 'Doppelt'], message: 'm' });
    assert.deepEqual(result.sent, ['1@g.us', '4917@c.us']);
    assert.equal(result.failed.length, 1);
    assert.equal(result.failed[0].target, 'Doppelt');
    assert.equal(sent.length, 2);
    await rejectsWith(handle({ type: 'broadcast', targets: ['Doppelt'], message: 'm' }), 'broadcast_failed');
    await rejectsWith(handle({ type: 'broadcast', targets: [], message: 'm' }), 'no_target');
});

test('send_poll validation', async () => {
    const { handle, sent } = setup();
    await handle({ type: 'send_poll', number: '49', message: 'Q?', options: ['a', 'b'], allow_multiple_answers: true });
    assert.deepEqual(sent[0].content.extra, { allowMultipleAnswers: true });
    await rejectsWith(handle({ type: 'send_poll', number: '49', message: 'Q?', options: ['a'] }), 'invalid_poll');
    await rejectsWith(handle({ type: 'send_poll', number: '49', message: 'Q?', options: 'a,b' }), 'invalid_poll');
    await rejectsWith(handle({ type: 'send_poll', number: '49', options: ['a', 'b'] }), 'invalid_poll');
});

test('send_event validation', async () => {
    const { handle, sent } = setup();
    await handle({
        type: 'send_event',
        number: '49',
        name: 'Grillen',
        start_time: '2026-10-01T18:00:00Z',
        end_time: '2026-10-01T22:00:00Z',
        location: 'Garten',
    });
    assert.equal(sent[0].content.options.location, 'Garten');
    assert.equal(sent[0].content.options.callType, 'none');
    await rejectsWith(handle({ type: 'send_event', number: '49', name: 'x', start_time: 'morgen' }), 'invalid_event');
    await rejectsWith(handle({ type: 'send_event', number: '49', start_time: '2026-10-01' }), 'invalid_event');
});

test('get_groups returns data and the legacy frame', async () => {
    const { handle, replies } = setup({ chats: [group('1@g.us', 'A'), { isGroup: false, name: 'x', id: { _serialized: '4@c.us' } }] });
    assert.deepEqual(await handle({ type: 'get_groups' }), [{ id: '1@g.us', name: 'A' }]);
    assert.deepEqual(replies[0], { type: 'get_groups_response', data: [{ id: '1@g.us', name: 'A' }] });
});

test('set_group_subject: success, rejection, not a group', async () => {
    const g = group('1@g.us', 'A');
    g.setSubject = async (subject) => subject !== 'nope';
    const { handle, replies } = setup({ chats: [g] });
    assert.deepEqual(await handle({ type: 'set_group_subject', group_id: '1', subject: 'B' }), { success: true });
    await rejectsWith(handle({ type: 'set_group_subject', group_id: '1', subject: 'nope' }), 'rejected');
    await rejectsWith(handle({ type: 'set_group_subject', group_id: '9', subject: 'B' }), 'not_a_group');
    assert.deepEqual(
        replies.map((r) => r.success),
        [true, false, false],
    );
});
