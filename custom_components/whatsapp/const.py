"""Constants for the WhatsApp integration."""

DOMAIN = "whatsapp"
CONF_HOST = "host"
CONF_TOKEN = "token"

DEFAULT_HOST = "ws://localhost:3000"

# WebSocket protocol spoken with the wa-bridge add-on (hello frame).
PROTOCOL_VERSION = 2

# Largest media file fetched for sending (WhatsApp limits most media to 16 MB).
MAX_MEDIA_BYTES = 16 * 1024 * 1024
MEDIA_FETCH_TIMEOUT = 30

EVENT_MESSAGE_RECEIVED = "whatsapp_message_received"
EVENT_POLL_VOTE_RECEIVED = "whatsapp_poll_vote_received"
EVENT_GROUPS_RECEIVED = "whatsapp_groups_received"
