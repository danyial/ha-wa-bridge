'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { readOptions, loadConfig, webVersionOptions } = require('../lib/config');

test('defaults', () => {
    const c = loadConfig({}, {});
    assert.equal(c.detectOwnMessages, false);
    assert.equal(c.incomingMode, 'all');
    assert.equal(c.incomingLogLevel, 'FULL');
    assert.deepEqual(c.allowedGroups, []);
    assert.equal(c.allowedNumbersSet.size, 0);
});

test('add-on options take precedence over env', () => {
    const c = loadConfig(
        {
            detect_own_messages: true,
            incoming_messages_mode: 'groups_only',
            incoming_message_log_level: 'compact',
            allowed_groups: ['Familie', 'Haus'],
            allowed_numbers: ['491700000001'],
        },
        { INCOMING_MESSAGES_MODE: 'disabled', ALLOWED_GROUPS: 'Other' },
    );
    assert.equal(c.detectOwnMessages, true);
    assert.equal(c.incomingMode, 'groups_only');
    assert.equal(c.incomingLogLevel, 'COMPACT');
    assert.deepEqual(c.allowedGroupsLower, ['familie', 'haus']);
    assert.deepEqual([...c.allowedNumbersSet], ['491700000001@c.us']);
});

test('env vars with comma-separated lists', () => {
    const c = loadConfig({}, {
        DETECT_OWN_MESSAGES: 'true',
        ALLOWED_GROUPS: ' A , B ,',
        ALLOWED_NUMBERS: '491,492',
        INCOMING_MESSAGE_LOG_LEVEL: 'none',
    });
    assert.equal(c.detectOwnMessages, true);
    assert.deepEqual(c.allowedGroups, ['A', 'B']);
    assert.deepEqual([...c.allowedNumbersSet], ['491@c.us', '492@c.us']);
    assert.equal(c.incomingLogLevel, 'NONE');
});

test('readOptions: missing file gives {}', () => {
    assert.deepEqual(readOptions(path.join(os.tmpdir(), 'does-not-exist.json')), {});
});

test('readOptions: reads JSON', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wa-bridge-'));
    const file = path.join(dir, 'options.json');
    fs.writeFileSync(file, JSON.stringify({ incoming_messages_mode: 'disabled' }));
    assert.deepEqual(readOptions(file), { incoming_messages_mode: 'disabled' });
    fs.rmSync(dir, { recursive: true });
});

test('WhatsApp Web version: live by default', () => {
    const c = loadConfig({}, {});
    assert.equal(c.waWebVersion, '');
    assert.deepEqual(webVersionOptions(c), { webVersionCache: { type: 'none' } });
});

test('WhatsApp Web version: optional pin', () => {
    const c = loadConfig({ wa_web_version: ' 2.3000.1017054665 ' }, {});
    const o = webVersionOptions(c);
    assert.equal(o.webVersion, '2.3000.1017054665');
    assert.equal(o.webVersionCache.type, 'remote');
    assert.equal(o.webVersionCache.strict, true);
    assert.match(o.webVersionCache.remotePath, /\{version\}\.html$/);
    assert.equal(loadConfig({}, { WA_WEB_VERSION: '2.1' }).waWebVersion, '2.1');
});
