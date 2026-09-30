'use strict';

// Readable text for anything thrown: whatsapp-web.js throws plain strings
// ("auth timeout"), which have no .message.
function errorText(err) {
    if (err instanceof Error) return err.message || err.name;
    if (typeof err === 'string') return err;
    if (err === null || err === undefined) return String(err);
    try {
        return JSON.stringify(err) ?? String(err);
    } catch {
        return String(err);
    }
}

// whatsapp-web.js reads the WhatsApp Web page from a 'response' listener only
// to store it in a 'local' web version cache, which the bridge does not use.
// Reading the body of a cached or redirected response fails there, outside
// any await (Client.js initWebVersionCache). Harmless.
function isHarmlessRejection(err) {
    return err instanceof Error && /Network\.getResponseBody/.test(err.message);
}

module.exports = { errorText, isHarmlessRejection };
