'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { createLidResolver, bareId, serialize } = require('../lib/ids');

const quiet = { warn() {} };
const LID = '123456789012345@lid';
const PHONE = '491700000001@c.us';

test('bareId and serialize', () => {
    assert.equal(bareId('491700000001:12@c.us'), PHONE);
    assert.equal(bareId(LID), LID);
    assert.equal(bareId(null), null);
    assert.equal(serialize({ _serialized: PHONE }), PHONE);
    assert.equal(serialize({ $1: PHONE }), PHONE);
    assert.equal(serialize(PHONE), PHONE);
});

test('phoneOf: phone ids pass through without lookup, LIDs resolve and cache', async () => {
    const calls = [];
    const resolver = createLidResolver({
        lookup: async (ids) => {
            calls.push(ids);
            return [{ lid: LID, pn: PHONE }];
        },
        log: quiet,
    });
    assert.equal(await resolver.phoneOf('491700000001:3@c.us'), PHONE);
    assert.equal(calls.length, 0);
    assert.equal(await resolver.phoneOf(LID), PHONE);
    assert.equal(await resolver.phoneOf(LID), PHONE);
    assert.deepEqual(calls, [[LID]]);
    assert.equal(await resolver.phoneOf('1@g.us'), null);
});

test('lidOf resolves own number', async () => {
    const resolver = createLidResolver({ lookup: async () => [{ lid: LID, pn: PHONE }], log: quiet });
    assert.equal(await resolver.lidOf(PHONE), LID);
    assert.equal(await resolver.lidOf(LID), LID);
});

test('unknown, failing and hanging lookups give null and are retried later', async () => {
    let t = 0;
    let mode = 'unknown';
    let calls = 0;
    const resolver = createLidResolver({
        lookup: async () => {
            calls += 1;
            if (mode === 'unknown') return [{}];
            if (mode === 'fail') throw new Error('r: r');
            if (mode === 'hang') return new Promise(() => {});
            return [{ lid: LID, pn: PHONE }];
        },
        now: () => t,
        missTtlMs: 1000,
        timeoutMs: 20,
        log: quiet,
    });
    assert.equal(await resolver.phoneOf(LID), null);
    assert.equal(await resolver.phoneOf(LID), null);
    assert.equal(calls, 1, 'miss is cached');
    t = 2000;
    mode = 'fail';
    assert.equal(await resolver.phoneOf(LID), null);
    t = 4000;
    mode = 'hang';
    assert.equal(await resolver.phoneOf(LID), null);
    t = 6000;
    mode = 'ok';
    assert.equal(await resolver.phoneOf(LID), PHONE);
});

test('cache is bounded', async () => {
    let n = 0;
    const resolver = createLidResolver({
        lookup: async ([id]) => [{ lid: id, pn: `49${++n}@c.us` }],
        maxEntries: 3,
        log: quiet,
    });
    for (let i = 0; i < 5; i++) await resolver.phoneOf(`${i}@lid`);
    assert.equal(resolver.size(), 3);
});
