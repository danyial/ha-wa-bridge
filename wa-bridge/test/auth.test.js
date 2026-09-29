'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { loadOrCreateToken, authorized, TOKEN_FILE } = require('../lib/auth');

function tmpdir() {
    return fs.mkdtempSync(path.join(os.tmpdir(), 'wa-auth-'));
}

test('generates, persists (0600) and reuses a token', () => {
    const dir = tmpdir();
    const first = loadOrCreateToken({ dir });
    assert.equal(first.source, 'generated');
    assert.match(first.token, /^[0-9a-f]{64}$/);
    const mode = fs.statSync(path.join(dir, TOKEN_FILE)).mode & 0o777;
    assert.equal(mode, 0o600);
    const second = loadOrCreateToken({ dir });
    assert.deepEqual(second, { token: first.token, source: 'file' });
    fs.rmSync(dir, { recursive: true });
});

test('configured token wins and is not written', () => {
    const dir = tmpdir();
    assert.deepEqual(loadOrCreateToken({ configured: ' secret ', dir }), {
        token: 'secret',
        source: 'configured',
    });
    assert.equal(fs.existsSync(path.join(dir, TOKEN_FILE)), false);
    fs.rmSync(dir, { recursive: true });
});

test('authorized', () => {
    assert.equal(authorized('Bearer abc', 'abc'), true);
    assert.equal(authorized('bearer abc', 'abc'), true);
    assert.equal(authorized('Bearer abd', 'abc'), false);
    assert.equal(authorized('Bearer ', 'abc'), false);
    assert.equal(authorized('abc', 'abc'), false);
    assert.equal(authorized(undefined, 'abc'), false);
    assert.equal(authorized('Bearer abc', ''), false);
});
