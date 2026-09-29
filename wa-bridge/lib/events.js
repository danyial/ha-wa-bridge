'use strict';

const { bareId, serialize, isGroup, isLid } = require('./ids');

// Builds the payloads of `message` and `poll_vote` frames. Fields of earlier
// versions are kept; new ones:
//   chat_id       the chat (group …@g.us or the other person's id)
//   sender        who wrote it (group author, direct sender, or yourself)
//   sender_phone  sender's number …@c.us, also for LID senders; null if unknown
//   sender_lid    sender's LID if WhatsApp sent one
//   is_group
//   to_self       own message to your own chat ("notes to self")
function createEventBuilder({ client, resolver, me, log = console }) {
    async function chatName(chatId, getChat) {
        try {
            const chat = await getChat(chatId);
            return chat?.name ?? null;
        } catch (err) {
            // getChatById throws for some unknown LID chats (wwebjs #201939).
            log.warn?.(`Chat ${chatId} not found: ${err.message}`);
            return null;
        }
    }

    async function message(msg) {
        const from = bareId(msg.from);
        const to = bareId(msg.to);
        const group = isGroup(from) || isGroup(to);
        const chatId = group ? (isGroup(from) ? from : to) : msg.fromMe ? to : from;
        const sender = bareId(msg.fromMe ? me().phone : msg.author || msg.from);
        const senderPhone = sender ? await resolver.phoneOf(sender) : null;
        const name = await chatName(chatId, () => msg.getChat());
        const toSelf = msg.fromMe && !group ? await isOwnChat(from, to) : false;
        return {
            from: msg.from,
            to: msg.to,
            body: msg.body,
            timestamp: msg.timestamp,
            hasMedia: msg.hasMedia,
            author: msg.author,
            deviceType: msg.deviceType,
            isForwarded: msg.isForwarded,
            fromMe: msg.fromMe,
            chatName: name,
            isGroup: group,
            groupId: group ? chatId : null,
            chat_id: chatId,
            sender,
            sender_phone: senderPhone,
            sender_lid: isLid(sender) ? sender : null,
            is_group: group,
            to_self: toSelf,
        };
    }

    // Seen live: a note to yourself has from = <own number>@c.us and
    // to = <own LID>@lid. Also accept to == from, to == own number, or a LID
    // that resolves to the own number.
    async function isOwnChat(from, to) {
        const own = me();
        if (!to) return false;
        if (to === from) return true;
        if (own.phone && to === own.phone) return true;
        if (own.lid && to === own.lid) return true;
        if (isLid(to) && own.phone) return (await resolver.phoneOf(to)) === own.phone;
        return false;
    }

    async function vote(pollVote) {
        const voterId = bareId(serialize(pollVote.voter));
        const voterPhone = voterId ? await resolver.phoneOf(voterId) : null;
        const parent = pollVote.parentMessage;
        const chatId = bareId(parent?.to && isGroup(parent.to) ? parent.to : parent?.id?.remote ?? parent?.to);
        const group = isGroup(chatId);
        const name = chatId ? await chatName(chatId, (id) => client.getChatById(id)) : null;
        return {
            // Before 3.0: digits of the voter; now the phone number when a LID
            // can be resolved (it used to be the LID's digits).
            voter: (voterPhone || voterId || '').split('@')[0] || null,
            voter_id: voterId,
            voter_phone: voterPhone,
            group_id: group ? chatId.split('@')[0] : null,
            chat_id: chatId,
            chatName: name,
            is_group: group,
            selectedOptions: pollVote.selectedOptions,
            pollCreationMessageId: serialize(parent?.id),
            timestamp: pollVote.timestamp,
        };
    }

    return { message, vote };
}

module.exports = { createEventBuilder };
