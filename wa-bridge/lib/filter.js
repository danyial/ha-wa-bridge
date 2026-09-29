'use strict';

// Decides which incoming messages and poll votes reach Home Assistant.
//
// - disabled:     nothing
// - groups_only:  group chats (limited to allowed_groups if set)
// - numbers_only: direct chats from allowed_numbers
// - all:          everything; with allowed_groups and/or allowed_numbers
//                 set, a message passes if its group is allowed OR it is a
//                 direct message from an allowed number.
//
// Fails closed: an unknown group name or an unresolved sender number does
// not match a list. Numbers are compared as resolved phone numbers, so
// senders hidden behind a LID match too.
function createFilter({ incomingMode, allowedGroupsLower, allowedNumbersSet }) {
    const groupList = allowedGroupsLower.length > 0;
    const numberList = allowedNumbersSet.size > 0;

    const groupAllowed = (chatName) =>
        typeof chatName === 'string' && allowedGroupsLower.includes(chatName.toLowerCase());
    const numberAllowed = (phone) => typeof phone === 'string' && allowedNumbersSet.has(phone);

    return function shouldForward({ isGroup, chatName, senderPhone }) {
        switch (incomingMode) {
            case 'disabled':
                return false;
            case 'groups_only':
                return isGroup && (!groupList || groupAllowed(chatName));
            case 'numbers_only':
                return !isGroup && numberAllowed(senderPhone);
            default:
                if (!groupList && !numberList) return true;
                if (isGroup) return groupList && groupAllowed(chatName);
                return numberList && numberAllowed(senderPhone);
        }
    };
}

module.exports = { createFilter };
