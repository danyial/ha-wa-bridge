#!/bin/bash
set -e

# Detect environment
if [ -d "/data" ]; then
    echo "Running in Home Assistant Add-on environment"
    export WA_DATA_PATH=/data
else
    echo "Running in Standard Docker environment"
    export WA_DATA_PATH=./.wwebjs_auth
fi

# Clean up stale Chromium locks to prevent "Browser already running" errors
# after an unclean shutdown.
SESSION_DIR="${WA_DATA_PATH}/session"
echo "Cleaning up locks in ${SESSION_DIR}..."
rm -f "${SESSION_DIR}"/Singleton* "${SESSION_DIR}"/*/Singleton*

echo "Starting WhatsApp Bridge..."
exec node index.js
