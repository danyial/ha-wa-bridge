'use strict';

const SUPERVISOR = 'http://supervisor';
const SERVICE = 'whatsapp';

// Announce the bridge to Home Assistant through Supervisor discovery, so the
// integration is offered with host, port and token already filled in.
// Only runs as an add-on (SUPERVISOR_TOKEN is set); /discovery and
// /addons/self/info need no extra API permission.
async function announce({ port, token, env = process.env, fetchImpl = fetch, log = console }) {
    const supervisorToken = env.SUPERVISOR_TOKEN;
    if (!supervisorToken) {
        log.log('Not running as an add-on, skipping discovery');
        return null;
    }
    const headers = {
        Authorization: `Bearer ${supervisorToken}`,
        'Content-Type': 'application/json',
    };

    const info = await fetchImpl(`${SUPERVISOR}/addons/self/info`, { headers });
    if (!info.ok) throw new Error(`Supervisor info failed: HTTP ${info.status}`);
    const { data } = await info.json();
    const host = data.hostname;

    const res = await fetchImpl(`${SUPERVISOR}/discovery`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ service: SERVICE, config: { host, port, token } }),
    });
    if (!res.ok) throw new Error(`Supervisor discovery failed: HTTP ${res.status}`);
    log.log(`Announced to Home Assistant as ${host}:${port}`);
    return { host, port };
}

module.exports = { announce, SERVICE };
