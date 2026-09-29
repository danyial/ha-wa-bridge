'use strict';

// Bridge states reported to Home Assistant.
const STATES = Object.freeze([
    'initializing', // browser starting, WhatsApp Web loading
    'qr', // waiting for the QR code to be scanned
    'authenticated', // paired, WhatsApp Web still syncing
    'ready', // connected and answering
    'unresponsive', // claims ready, but the page does not answer
    'disconnected', // logged out or session lost; restarting
    'auth_failure', // stored session rejected
]);

// Tracks the bridge state and reports changes (not repeats) through `emit`.
function createStatusTracker({ emit, now = () => Date.now() }) {
    let current = { status: 'initializing', since: now() };

    function snapshot() {
        return { ...current };
    }

    function set(status, extra = {}) {
        if (!STATES.includes(status)) throw new Error(`unknown status ${status}`);
        const next = { ...current, ...extra, status };
        if (status !== current.status) next.since = now();
        const changed = JSON.stringify(next) !== JSON.stringify(current);
        current = next;
        if (changed) emit({ type: 'status', ...snapshot() });
        return changed;
    }

    return { set, snapshot, get status() {
        return current.status;
    } };
}

function withTimeout(promise, ms) {
    let timer;
    const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`no answer within ${ms} ms`)), ms);
    });
    return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

// Detects a hung WhatsApp Web page: whatsapp-web.js keeps reporting "ready"
// while page.evaluate calls never return (seen for an hour on OpenWA).
// `probe` resolves with the WhatsApp socket state or throws; each call gets
// `timeoutMs`. After `failures` consecutive failures `onUnresponsive(err)`
// fires once; the next success fires `onRecovered(state)`.
function createHealthMonitor({
    probe,
    onState = () => {},
    onUnresponsive,
    onRecovered,
    intervalMs = 30000,
    timeoutMs = 10000,
    failures = 2,
}) {
    let timer = null;
    let failed = 0;
    let unresponsive = false;
    let running = false;

    async function check() {
        if (running) return;
        running = true;
        try {
            const state = await withTimeout(Promise.resolve().then(probe), timeoutMs);
            failed = 0;
            onState(state);
            if (unresponsive) {
                unresponsive = false;
                onRecovered(state);
            }
        } catch (err) {
            failed += 1;
            if (!unresponsive && failed >= failures) {
                unresponsive = true;
                onUnresponsive(err);
            }
        } finally {
            running = false;
        }
    }

    function start() {
        stop();
        failed = 0;
        unresponsive = false;
        timer = setInterval(check, intervalMs);
        timer.unref?.();
    }

    function stop() {
        if (timer) clearInterval(timer);
        timer = null;
    }

    return { start, stop, check, get unresponsive() {
        return unresponsive;
    } };
}

module.exports = { STATES, createStatusTracker, createHealthMonitor, withTimeout };
