'use strict';

const { withTimeout } = require('./status');

const isLid = (id) => typeof id === 'string' && id.endsWith('@lid');
const isPhone = (id) => typeof id === 'string' && id.endsWith('@c.us');
const isGroup = (id) => typeof id === 'string' && id.endsWith('@g.us');

// Strip the device suffix: "4917...:12@c.us" -> "4917...@c.us".
function bareId(id) {
    if (typeof id !== 'string') return null;
    const [user, server] = id.split('@');
    return server ? `${user.split(':')[0]}@${server}` : id;
}

// Serialize a whatsapp-web.js id (string or {_serialized} / {$1}).
function serialize(id) {
    if (!id) return null;
    if (typeof id === 'string') return id;
    return id._serialized || id.$1 || null;
}

// Maps WhatsApp LIDs (…@lid, hidden numbers) to phone numbers (…@c.us)
// through client.getContactLidAndPhone. Results are cached: hits for a day,
// misses for 10 minutes (the lookup may ask the WhatsApp server). A failure
// or timeout gives null, never an exception.
function createLidResolver({
    lookup,
    now = () => Date.now(),
    ttlMs = 24 * 60 * 60 * 1000,
    missTtlMs = 10 * 60 * 1000,
    maxEntries = 5000,
    timeoutMs = 5000,
    log = console,
}) {
    const cache = new Map(); // lid -> {phone, lid, expires}

    function remember(key, value, ttl) {
        cache.delete(key);
        cache.set(key, { ...value, expires: now() + ttl });
        while (cache.size > maxEntries) cache.delete(cache.keys().next().value);
    }

    async function resolve(id) {
        const key = bareId(id);
        const hit = cache.get(key);
        if (hit && hit.expires > now()) return hit;
        try {
            const [result] = await withTimeout(Promise.resolve().then(() => lookup([key])), timeoutMs);
            const value = {
                phone: isPhone(result?.pn) ? bareId(result.pn) : null,
                lid: isLid(result?.lid) ? bareId(result.lid) : null,
            };
            remember(key, value, value.phone || value.lid ? ttlMs : missTtlMs);
            return value;
        } catch (err) {
            log.warn?.(`LID lookup for ${key} failed: ${err.message}`);
            remember(key, { phone: null, lid: null }, missTtlMs);
            return { phone: null, lid: null };
        }
    }

    // Phone number (…@c.us) of a user id, or null if unknown.
    async function phoneOf(id) {
        const key = bareId(id);
        if (isPhone(key)) return key;
        if (!isLid(key)) return null;
        return (await resolve(key)).phone;
    }

    // LID (…@lid) of a user id, or null if unknown.
    async function lidOf(id) {
        const key = bareId(id);
        if (isLid(key)) return key;
        if (!isPhone(key)) return null;
        return (await resolve(key)).lid;
    }

    return { phoneOf, lidOf, size: () => cache.size };
}

module.exports = { createLidResolver, bareId, serialize, isLid, isPhone, isGroup };
