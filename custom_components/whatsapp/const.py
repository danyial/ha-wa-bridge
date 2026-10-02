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

# Options
CONF_OWN_MESSAGES = "own_messages"
OWN_MESSAGES_OFF = "off"
OWN_MESSAGES_SELF = "self"
OWN_MESSAGES_ALL = "all"
OWN_MESSAGES_MODES = [OWN_MESSAGES_OFF, OWN_MESSAGES_SELF, OWN_MESSAGES_ALL]
CONF_DEFAULT_CHAT = "default_chat"
CONF_MAX_AGE = "max_age_minutes"
CONF_ALLOW_HISTORY = "allow_message_history"
HISTORY_MAX_LIMIT = 50
