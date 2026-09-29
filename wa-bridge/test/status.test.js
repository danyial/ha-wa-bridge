'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { createStatusTracker, createHealthMonitor, withTimeout } = require('../lib/status');

test('tracker emits changes only', () => {
    const frames = [];
    let t = 1000;
    const tracker = createStatusTracker({ emit: (f) => frames.push(f), now: () => t });
    assert.equal(tracker.status, 'initializing');
    assert.equal(tracker.set('qr'), true);
    assert.equal(tracker.set('qr'), false);
    t = 2000;
    tracker.set('ready', { phone: '4917' });
    tracker.set('ready', { wa_state: 'CONNECTED' });
    tracker.set('ready', { wa_state: 'CONNECTED' });
    assert.deepEqual(
        frames.map((f) => [f.status, f.phone, f.wa_state]),
        [
            ['qr', undefined, undefined],
            ['ready', '4917', undefined],
            ['ready', '4917', 'CONNECTED'],
        ],
    );
    assert.equal(frames.at(-1).since, 2000);
    assert.throws(() => tracker.set('bogus'));
});

test('withTimeout', async () => {
    assert.equal(await withTimeout(Promise.resolve(1), 50), 1);
    await assert.rejects(withTimeout(new Promise(() => {}), 20), /no answer within 20 ms/);
});

function monitor(probe, extra = {}) {
    const events = [];
    const m = createHealthMonitor({
        probe,
        timeoutMs: 20,
        failures: 2,
        onState: (s) => events.push(['state', s]),
        onUnresponsive: (err) => events.push(['unresponsive', err.message]),
        onRecovered: (s) => events.push(['recovered', s]),
        ...extra,
    });
    return { m, events };
}

test('two failed probes -> unresponsive once, success -> recovered', async () => {
    let mode = 'hang';
    const { m, events } = monitor(() =>
        mode === 'hang' ? new Promise(() => {}) : Promise.resolve('CONNECTED'),
    );
    await m.check();
    assert.deepEqual(events, []);
    await m.check();
    await m.check();
    assert.deepEqual(events, [['unresponsive', 'no answer within 20 ms']]);
    assert.equal(m.unresponsive, true);
    mode = 'ok';
    await m.check();
    assert.deepEqual(events.slice(1), [
        ['state', 'CONNECTED'],
        ['recovered', 'CONNECTED'],
    ]);
    assert.equal(m.unresponsive, false);
});

test('a success resets the failure count', async () => {
    const results = ['fail', 'ok', 'fail', 'ok'];
    const { m, events } = monitor(async () => {
        if (results.shift() === 'fail') throw new Error('closed');
        return 'CONNECTED';
    });
    for (let i = 0; i < 4; i++) await m.check();
    assert.equal(events.filter((e) => e[0] === 'unresponsive').length, 0);
});

test('probe exceptions count as failures', async () => {
    const { m, events } = monitor(() => {
        throw new Error('browser disconnected');
    });
    await m.check();
    await m.check();
    assert.deepEqual(events, [['unresponsive', 'browser disconnected']]);
});

test('start/stop run the interval', async () => {
    let calls = 0;
    const { m } = monitor(async () => {
        calls += 1;
        return 'CONNECTED';
    }, { intervalMs: 10 });
    m.start();
    await new Promise((r) => setTimeout(r, 60));
    m.stop();
    const seen = calls;
    assert.ok(seen >= 2, `expected >= 2 probes, got ${seen}`);
    await new Promise((r) => setTimeout(r, 40));
    assert.equal(calls, seen);
});
