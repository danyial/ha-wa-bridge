'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { createEventBuilder } = require('../lib/events');

const ME = '491700000009@c.us';
const LID = '123456789012345@lid';
const PHONE = '491700000001@c.us';
const GROUP = '120363000000000001@g.us';

const resolver = {
    phoneOf: async (id) => (id === LID ? PHONE : id?.endsWith('@c.us') ? id : null),
};

function builder(chats = {}) {
    return createEventBuilder({
        client: {
            getChatById: async (id) => {
                if (!chats[id]) throw new Error('not found');
                return chats[id];
            },
        },
        resolver,
        me: () => ({ phone: ME }),
        log: { warn() {} },
    });
}

function msg(fields, chatName = 'Chat') {
    return {
        body: 'hi',
        timestamp: 1,
        fromMe: false,
        getChat: async () => {
            if (chatName === null) throw new Error('not found');
            return { name: chatName };
        },
        ...fields,
    };
}

test('direct message from a LID sender resolves sender_phone', async () => {
    const data = await builder().message(msg({ from: LID, to: ME }, 'Anna'));
    assert.equal(data.chat_id, LID);
    assert.equal(data.sender, LID);
    assert.equal(data.sender_phone, PHONE);
    assert.equal(data.sender_lid, LID);
    assert.equal(data.is_group, false);
    assert.equal(data.from, LID, 'legacy field unchanged');
});

test('group message: sender is the author, chat is the group', async () => {
    const data = await builder().message(msg({ from: GROUP, to: ME, author: LID }, 'Familie'));
    assert.equal(data.chat_id, GROUP);
    assert.equal(data.groupId, GROUP);
    assert.equal(data.sender, LID);
    assert.equal(data.sender_phone, PHONE);
    assert.equal(data.chatName, 'Familie');
    assert.equal(data.isGroup, true);
});

test('own message: sender is me, chat is the recipient', async () => {
    const data = await builder().message(msg({ from: `${ME.split('@')[0]}:3@c.us`, to: PHONE, fromMe: true }));
    assert.equal(data.sender, ME);
    assert.equal(data.sender_phone, ME);
    assert.equal(data.chat_id, PHONE);
});

test('own message in a group', async () => {
    const data = await builder().message(msg({ from: LID, to: GROUP, fromMe: true }));
    assert.equal(data.chat_id, GROUP);
    assert.equal(data.is_group, true);
    assert.equal(data.sender, ME);
});

test('chat lookup failure keeps the message with chatName null', async () => {
    const data = await builder().message(msg({ from: LID, to: ME }, null));
    assert.equal(data.chatName, null);
    assert.equal(data.sender_phone, PHONE);
});

test('poll vote from a LID voter in a group', async () => {
    const data = await builder({ [GROUP]: { name: 'Familie' } }).vote({
        voter: LID,
        selectedOptions: [{ name: 'Ja' }],
        timestamp: 5,
        parentMessage: { to: GROUP, id: { _serialized: 'poll-1', remote: GROUP } },
    });
    assert.equal(data.voter, '491700000001', 'legacy digits are now the phone number');
    assert.equal(data.voter_id, LID);
    assert.equal(data.voter_phone, PHONE);
    assert.equal(data.group_id, '120363000000000001');
    assert.equal(data.chat_id, GROUP);
    assert.equal(data.chatName, 'Familie');
    assert.equal(data.pollCreationMessageId, 'poll-1');
});

test('poll vote in a direct chat, voter unresolved', async () => {
    const data = await builder().vote({
        voter: '999@lid',
        selectedOptions: [],
        parentMessage: { to: ME, id: { _serialized: 'p', remote: '999@lid' } },
    });
    assert.equal(data.voter, '999');
    assert.equal(data.voter_phone, null);
    assert.equal(data.is_group, false);
    assert.equal(data.group_id, null);
});

const MY_LID = '555555555555555@lid';

function selfBuilder(ownLid) {
    return createEventBuilder({
        client: { getChatById: async () => ({}) },
        resolver: {
            phoneOf: async (id) => (id === MY_LID ? ME : id === LID ? PHONE : id?.endsWith('@c.us') ? id : null),
        },
        me: () => ({ phone: ME, lid: ownLid }),
        log: { warn() {} },
    });
}

test('to_self: note to self as seen live (from own number, to own LID)', async () => {
    for (const ownLid of [MY_LID, null]) {
        const data = await selfBuilder(ownLid).message(msg({ from: ME, to: MY_LID, fromMe: true }));
        assert.equal(data.to_self, true, `own lid known: ${Boolean(ownLid)}`);
    }
});

test('to_self: to == from and to == own number', async () => {
    const b = selfBuilder(MY_LID);
    assert.equal((await b.message(msg({ from: ME, to: ME, fromMe: true }))).to_self, true);
    assert.equal((await b.message(msg({ from: MY_LID, to: ME, fromMe: true }))).to_self, true);
});

test('to_self is false for other chats, groups and incoming messages', async () => {
    const b = selfBuilder(MY_LID);
    assert.equal((await b.message(msg({ from: ME, to: PHONE, fromMe: true }))).to_self, false);
    assert.equal((await b.message(msg({ from: ME, to: LID, fromMe: true }))).to_self, false);
    assert.equal((await b.message(msg({ from: MY_LID, to: GROUP, fromMe: true }))).to_self, false);
    assert.equal((await b.message(msg({ from: MY_LID, to: ME, fromMe: false }))).to_self, false);
});
