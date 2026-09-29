'use strict';

const { CommandError } = require('./server');

// Command handlers for the bridge. Each handler returns result data or throws;
// the server turns that into a `result` frame. `reply` sends extra frames to
// the requesting client only (the pre-2.x *_response frames, kept for older
// integrations).
function createCommandHandler({ client, wwebjs, isReady, actions = {}, log = console }) {
    const { MessageMedia, Poll, ScheduledEvent } = wwebjs;

    function requireReady() {
        if (!isReady()) {
            throw new CommandError('not_ready', 'WhatsApp is not connected (not paired or still starting)');
        }
    }

    function toMedia(media) {
        if (!media) return null;
        if (typeof media.data !== 'string' || typeof media.mimetype !== 'string') {
            throw new CommandError('invalid_media', 'media needs mimetype and base64 data');
        }
        return new MessageMedia(media.mimetype, media.data, media.filename || 'media');
    }

    function groupJid(groupId) {
        const id = String(groupId).trim();
        return id.includes('@') ? id : `${id}@g.us`;
    }

    function numberJid(number) {
        const value = String(number).trim();
        if (value.includes('@')) return value;
        const digits = value.replace(/\D/g, '');
        if (!digits) throw new CommandError('invalid_number', `not a phone number: ${value}`);
        return `${digits}@c.us`;
    }

    async function groupsByName(name, chats) {
        const all = chats || (await client.getChats());
        const wanted = String(name).trim().toLowerCase();
        return all.filter((chat) => chat.isGroup && (chat.name || '').toLowerCase() === wanted);
    }

    // group_id beats group_name beats number. A group name must match exactly
    // one group: the first match could be a group someone else named the same.
    async function resolveChatId({ number, group_name: groupName, group_id: groupId }, chats) {
        if (groupId) return groupJid(groupId);
        if (groupName) {
            const matches = await groupsByName(groupName, chats);
            if (matches.length === 1) return matches[0].id._serialized;
            if (matches.length > 1) {
                throw new CommandError(
                    'ambiguous_group',
                    `${matches.length} groups are named "${groupName}"; use group_id`,
                );
            }
            if (!number) throw new CommandError('group_not_found', `no group named "${groupName}"`);
        }
        if (number) return numberJid(number);
        throw new CommandError('no_target', 'number, group_name or group_id is required');
    }

    async function sendMessage(cmd, chats) {
        const chatId = await resolveChatId(cmd, chats);
        const media = toMedia(cmd.media);
        if (!media && !cmd.message) throw new CommandError('empty_message', 'message or media is required');
        const sent = media
            ? await client.sendMessage(chatId, media, { caption: cmd.message })
            : await client.sendMessage(chatId, cmd.message);
        log.log(`Sent ${media ? 'media ' : ''}message to ${chatId}`);
        return { chat_id: chatId, message_id: sent?.id?._serialized ?? null };
    }

    const handlers = {
        async ping() {
            return { pong: true };
        },

        async get_status() {
            return actions.status();
        },

        async restart() {
            // Answer first; the restart takes the browser down for a while.
            setImmediate(() => actions.restart());
            return { restarting: true };
        },

        async logout() {
            try {
                await actions.logout();
            } catch (err) {
                throw new CommandError('not_linked', err.message);
            }
            return { logged_out: true };
        },

        async send_message(cmd) {
            requireReady();
            return sendMessage(cmd);
        },

        async broadcast(cmd) {
            requireReady();
            const targets = cmd.targets;
            if (!Array.isArray(targets) || targets.length === 0) {
                throw new CommandError('no_target', 'targets must be a non-empty list');
            }
            const chats = await client.getChats();
            const sent = [];
            const failed = [];
            for (const target of targets) {
                try {
                    // A target is a group name if such a group exists, else a number.
                    const result = await sendMessage(
                        { number: target, group_name: target, message: cmd.message, media: cmd.media },
                        chats,
                    );
                    sent.push(result.chat_id);
                } catch (err) {
                    failed.push({ target, error: err.message });
                }
            }
            if (sent.length === 0) {
                throw new CommandError('broadcast_failed', failed.map((f) => `${f.target}: ${f.error}`).join('; '));
            }
            return { sent, failed };
        },

        async send_poll(cmd) {
            requireReady();
            const options = cmd.options;
            if (!Array.isArray(options) || options.length < 2 || !options.every((o) => typeof o === 'string')) {
                throw new CommandError('invalid_poll', 'options must be a list of at least two strings');
            }
            if (!cmd.message) throw new CommandError('invalid_poll', 'message (the question) is required');
            const chatId = await resolveChatId(cmd);
            const poll = new Poll(cmd.message, options, { allowMultipleAnswers: Boolean(cmd.allow_multiple_answers) });
            const sent = await client.sendMessage(chatId, poll);
            log.log(`Sent poll to ${chatId}`);
            return { chat_id: chatId, message_id: sent?.id?._serialized ?? null };
        },

        async send_event(cmd) {
            requireReady();
            if (!cmd.name) throw new CommandError('invalid_event', 'name is required');
            const start = new Date(cmd.start_time);
            if (Number.isNaN(start.getTime())) {
                throw new CommandError('invalid_event', `invalid start_time: ${cmd.start_time}`);
            }
            const options = { callType: cmd.call_type || 'none' };
            if (cmd.description) options.description = cmd.description;
            if (cmd.location) options.location = cmd.location;
            if (cmd.end_time) {
                const end = new Date(cmd.end_time);
                if (Number.isNaN(end.getTime())) {
                    throw new CommandError('invalid_event', `invalid end_time: ${cmd.end_time}`);
                }
                options.endTime = end;
            }
            const chatId = await resolveChatId(cmd);
            const sent = await client.sendMessage(chatId, new ScheduledEvent(cmd.name, start, options));
            log.log(`Sent event to ${chatId}`);
            return { chat_id: chatId, message_id: sent?.id?._serialized ?? null };
        },

        async get_groups(cmd, reply) {
            try {
                requireReady();
                const chats = await client.getChats();
                const groups = chats
                    .filter((chat) => chat.isGroup)
                    .map((chat) => ({ id: chat.id._serialized, name: chat.name }));
                reply({ type: 'get_groups_response', data: groups });
                return groups;
            } catch (err) {
                reply({ type: 'get_groups_response', data: [], error: err.message });
                throw err;
            }
        },

        async set_group_subject(cmd, reply) {
            return withGroup(cmd, 'set_group_subject_response', reply, async (chat) => {
                if (!cmd.subject) throw new CommandError('invalid_request', 'subject is required');
                return chat.setSubject(cmd.subject);
            });
        },

        async set_group_picture(cmd, reply) {
            return withGroup(cmd, 'set_group_picture_response', reply, async (chat) => {
                const media = toMedia(cmd.media);
                if (!media) throw new CommandError('invalid_request', 'media is required');
                return chat.setPicture(media);
            });
        },
    };

    async function withGroup(cmd, responseType, reply, action) {
        try {
            requireReady();
            if (!cmd.group_id) throw new CommandError('invalid_request', 'group_id is required');
            const chat = await client.getChatById(groupJid(cmd.group_id));
            if (!chat.isGroup) throw new CommandError('not_a_group', 'Chat is not a group');
            const success = await action(chat);
            reply({ type: responseType, success });
            if (!success) throw new CommandError('rejected', 'WhatsApp rejected the change (admin rights?)');
            return { success };
        } catch (err) {
            if (!(err instanceof CommandError && err.code === 'rejected')) {
                reply({ type: responseType, success: false, error: err.message });
            }
            throw err;
        }
    }

    return async function handle(cmd, reply) {
        const handler = handlers[cmd.type];
        if (!handler) throw new CommandError('unknown_command', `unknown command: ${cmd.type}`);
        return handler(cmd, reply);
    };
}

module.exports = { createCommandHandler };
