'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const TOKEN_FILE = 'auth_token';

// The token clients must send as "Authorization: Bearer <token>".
// Priority: explicit option/env value, then the persisted token in `dir`,
// which is created on first start (0600). There is no unauthenticated mode.
function loadOrCreateToken({ configured = '', dir }) {
    const explicit = String(configured || '').trim();
    if (explicit) {
        return { token: explicit, source: 'configured' };
    }
    const file = path.join(dir, TOKEN_FILE);
    try {
        const stored = fs.readFileSync(file, 'utf8').trim();
        if (stored) {
            return { token: stored, source: 'file' };
        }
    } catch (err) {
        if (err.code !== 'ENOENT') throw err;
    }
    const token = crypto.randomBytes(32).toString('hex');
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(file, `${token}\n`, { mode: 0o600 });
    return { token, source: 'generated' };
}

function digest(value) {
    return crypto.createHash('sha256').update(String(value)).digest();
}

// Constant-time check of an Authorization header against the token.
// Hashing first gives equal-length buffers for timingSafeEqual.
function authorized(header, token) {
    if (typeof header !== 'string' || !token) return false;
    const match = /^Bearer\s+(\S+)\s*$/i.exec(header);
    if (!match) return false;
    return crypto.timingSafeEqual(digest(match[1]), digest(token));
}

module.exports = { loadOrCreateToken, authorized, TOKEN_FILE };
