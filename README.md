> **Disclaimer from underlying library [whatsapp-web.js](https://wwebjs.dev/)**
> This project is not affiliated, associated, authorized, endorsed by, or in any way officially connected with WhatsApp or any of its subsidiaries or its affiliates. The official WhatsApp website can be found at [whatsapp](https://www.whatsapp.com). "WhatsApp" as well as related names, marks, emblems and images are registered trademarks of their respective owners. Also it is not guaranteed you will not be blocked by using this method. WhatsApp does not allow bots or unofficial clients on their platform, so this shouldn't be considered totally safe. For any businesses looking to integrate with WhatsApp for critical applications, we highly recommend using officially supported methods, such as Twilio's solution or other alternatives. You might also consider the [official API](https://developers.facebook.com/documentation/business-messaging/whatsapp/overview).

# Home Assistant WhatsApp Integration

> **Fork** of [raulpetruta/ha-wa-bridge](https://github.com/raulpetruta/ha-wa-bridge) with a hardened add-on (authenticated WebSocket, no host port by default), current whatsapp-web.js, status entities and LID-aware sender handling. Work in progress towards 3.0.0.

A custom integration to send and receive WhatsApp messages in Home Assistant naturally. It uses a local [whatsapp-web.js](https://wwebjs.dev/) bridge running in Docker.

## Features
- **Send Messages**: Use the `whatsapp.send_message` service in HA.
- **Group Messaging**: Send messages to WhatsApp groups by name or by group ID.
- **Group ID Support**: Target groups by their stable ID instead of name — automations won't break when a group is renamed.
- **Get Groups**: Retrieve all WhatsApp groups with their IDs using the `whatsapp.get_groups` service.
- **Set Group Subject**: Dynamically update a group's name using the `whatsapp.set_group_subject` service — perfect for automating group names based on schedules or sensor values.
- **Set Group Picture**: Update a group's picture using the `whatsapp.set_group_picture` service.
- **Receive Messages**: Trigger automations when messages arrive (including WhatsApp Community channels).
- **Send Events**: Send WhatsApp calendar events with name, location, and time using the `whatsapp.send_event` service.
- **Receive Filtering**: Disable incoming messages entirely or restrict to specific groups to save resources.
- **Easy Auth**: Scan a QR code in Home Assistant to link your account.

## Usage

### Sending a Messsage
You can send messages to any number using the service:

```yaml
service: whatsapp.send_message
data:
  number: "40741234567" # Country code + Number (no "+" symbol) 
  message: "Hello from Home Assistant! 🏠"
```

### Sending to a Group
You can send messages to a group by its exact name:

```yaml
service: whatsapp.send_message
data:
  group: "Family Group" # Exact name of the group
  message: "Dinner is ready! 🍽️"
```

### Sending to a Group by ID
You can send messages to a group using its stable ID. This is recommended for automations since the ID doesn't change when the group is renamed. Use the `whatsapp.get_groups` service to find group IDs; or check the add on logs while sending / receiving a message for a group to get the ID

```yaml
service: whatsapp.send_message
data:
  group_id: "120363012345678901" # Group ID (use get_groups to find this)
  message: "Dinner is ready! 🍽️"
```

### Retrieving Group IDs
Use the `whatsapp.get_groups` service to retrieve all your WhatsApp groups with their IDs. The results are fired as a `whatsapp_groups_received` event.

```yaml
service: whatsapp.get_groups
```

You can listen for the result with an automation:

```yaml
trigger:
  - platform: event
    event_type: whatsapp_groups_received
action:
  - service: persistent_notification.create
    data:
      title: "WhatsApp Groups"
      message: >
        {% for group in trigger.event.data.groups %}
        - {{ group.name }}: {{ group.id }}
        {% endfor %}
```

### Setting a Group Subject (Name)
You can dynamically update a group's name using the `whatsapp.set_group_subject` service. This is useful for automating group names based on schedules or template sensors. Requires admin permissions in the group.

```yaml
service: whatsapp.set_group_subject
data:
  group_id: "120363012345678901" # Group ID (use get_groups to find this)
  subject: "Weekly Meeting - Monday 7PM"
```

### Setting a Group Picture
You can update a group's picture using the `whatsapp.set_group_picture` service. Supports both URL and local path. Requires admin permissions in the group.

#### Using a URL
```yaml
service: whatsapp.set_group_picture
data:
  group_id: "120363012345678901" # Group ID (use get_groups to find this)
  media_url: "https://example.com/group-photo.jpg"
```

#### Using a Local File
```yaml
service: whatsapp.set_group_picture
data:
  group_id: "120363012345678901" # Group ID (use get_groups to find this)
  media_path: "www/group-photo.jpg"
```

## Sending Broadcast Messages
You can send messages to multiple targets using the service:

```yaml
service: whatsapp.send_broadcast
data:
  message: "Hello everyone! This is a broadcast."
  targets:
    - "Family Group"      # Group name
    - "40741234567"       # Phone number
```

### Sending Polls
You can send polls using the `whatsapp.send_poll` service:

```yaml
service: whatsapp.send_poll
data:
  message: "What should we have for dinner?"
  options:
    - "Pizza"
    - "Sushi"
    - "Burgers"
  allow_multiple_answers: true
  number: "40741234567" # OR group: "Group Name" OR group_id: "120363012345678901"
```

### Sending Events
You can send WhatsApp calendar events using the `whatsapp.send_event` service. Events include a name, start time, and optional description, location, end time, and call link.

```yaml
service: whatsapp.send_event
data:
  number: "40741234567" # OR group: "Group Name" OR group_id: "120363012345678901"
  name: "Weekly Team Meeting"
  description: "Discuss project updates and next steps"
  location: "Conference Room A" # OR meeting link https://teams.microsoft.com/l/meetup-join/
  start_time: "2026-06-15T14:00:00"
  end_time: "2026-06-15T15:00:00"
  call_type: "video" # Optional: video, voice, or none
```

#### Minimal Example
Only `name` and `start_time` are required:

```yaml
service: whatsapp.send_event
data:
  number: "40741234567"
  name: "Dentist Appointment"
  start_time: "2026-06-20T10:30:00"
```

### Automation Trigger for Polls
Trigger actions when a user votes on a poll using the `whatsapp_poll_vote_received` event.

The event contains:
- `voter`: The phone number of the voter (e.g. `40741234567`)
- `selectedOptions`: An array of the options selected
- `group_id`: The ID of the group if the poll was in a group, otherwise null

```yaml
trigger:
  - platform: event
    event_type: whatsapp_poll_vote_received
    # Optional: trigger only for a specific voter
    # event_data:
    #   voter: "40741234567" 
action:
  - service: notify.persistent_notification
    data:
      message: "Received a vote from {{ trigger.event.data.voter }}! Selected options: {{ trigger.event.data.selectedOptions | map(attribute='name') | list | join(', ') }}"
```

### Sending Media
You can send images or files using either a URL (`media_url`) or a local path (`media_path`).

#### Using a URL
```yaml
service: whatsapp.send_message
data:
  number: "40741234567"
  message: "Check this out!"
  media_url: "https://www.home-assistant.io/images/favicon.ico"
```

#### Using a Local File
Ensure the path is accessible by Home Assistant (e.g., in `config/www`).
```yaml
service: whatsapp.send_broadcast
data:
  targets: ["Family Group", "40741234567"]
  message: "Security Snapshot"
  media_path: "/config/www/camera_snapshot.jpg"
```

### Automation Trigger
Trigger actions when a specific message is received:

```yaml
trigger:
  - platform: whatsapp
    from_number: "40741234567"
    contains_text: "Turn on lights" # Optional
action:
  - service: light.turn_on
    target:
      entity_id: light.living_room
```

`from_number` accepts international (`+49 170 1234567`, `0049…`, `49170…`) and national numbers (`0170 1234567`, using the country set in Home Assistant). It matches the person who wrote the message, also inside groups and also when WhatsApp hides the number behind a LID (the bridge resolves it; see *Senders and LIDs*).

The WhatsApp device also offers a device trigger **Message received** with an optional sender filter (*Settings → Automations → Device*).

### Senders and LIDs

WhatsApp increasingly identifies people by a *LID* (`…@lid`) instead of their number. The bridge resolves LIDs to phone numbers where WhatsApp knows them (cached; an unknown LID may cost one lookup at WhatsApp's server) and adds to every `whatsapp_message_received` event:

| Field | Meaning |
|---|---|
| `sender` | who wrote it: the group author, the direct sender, or yourself (`…@c.us` or `…@lid`) |
| `sender_phone` | that person's number `…@c.us`, also for LID senders; `null` if WhatsApp does not reveal it |
| `sender_lid` | the LID, if WhatsApp sent one |
| `chat_id` | the chat: group `…@g.us` or the other person |
| `is_group` | group chat |
| `device_id` | the WhatsApp device in Home Assistant |

The earlier fields (`from`, `to`, `author`, `body`, `chatName`, `isGroup`, `groupId`, …) are unchanged. In `whatsapp_poll_vote_received`, `voter` is now the voter's phone number (digits) when a LID can be resolved; `voter_id`, `voter_phone` and `chat_id` are new.

### Group Message Trigger
To trigger an automation from a group message, use `from_group` with the exact group name:

```yaml
trigger:
  - platform: whatsapp
    from_group: "Family Group"
    contains_text: "Dinner" # Optional
action:
  - service: notify.persistent_notification
    data:
      message: "Dinner time!"
```

### Group Message Trigger by ID
For more stable automations, use `from_group_id` instead of `from_group`. The group ID remains the same even if the group name changes:

```yaml
trigger:
  - platform: whatsapp
    from_group_id: "120363012345678901"
    contains_text: "Dinner" # Optional
    equals_text: "Dinner ready" # Optional
action:
  - service: notify.persistent_notification
    data:
      message: "Dinner time!"
```

### Channel Message Trigger
WhatsApp Community channels are treated as groups internally. You can trigger automations from channel messages using `from_group` or `from_group_id`, just like regular groups:

```yaml
trigger:
  - platform: whatsapp
    from_group: "Announcements" # Exact channel name
    contains_text: "update" # Optional
    equals_text: "update received" # Optional
action:
  - service: notify.persistent_notification
    data:
      message: "New channel update received!"
```

For more stable automations, use `from_group_id` with the channel's numeric ID (without `@g.us`). The ID remains the same even if the channel is renamed:

```yaml
trigger:
  - platform: whatsapp
    from_group_id: "120363428200052636" # Channel ID (use get_groups or check bridge logs)
    contains_text: "update" # Optional
action:
  - service: notify.persistent_notification
    data:
      message: "New channel update received!"
```

## Installation

### 1. Run the Bridge

#### Option A: Home Assistant Add-on (Recommended for HA OS)
1.  Go to **Settings > Add-ons > Add-on Store**.
2.  Click the **dots (top-right) > Repositories**.
3.  Add this repository URL: `https://github.com/danyial/ha-wa-bridge`
4.  Reload the store and install **WhatsApp Bridge**.
5.  Start the Add-on. Home Assistant then offers the **WhatsApp** integration under *Settings → Devices & services* (discovered, with address and access token filled in).

#### Option B: Docker (For Container/Core users)
This project requires a small bridge service. Create a `docker-compose.yaml` file with the following content:

```yaml
services:
  ha-wa-bridge:
    image: ghcr.io/danyial/ha-wa-bridge:latest
    container_name: ha-wa-bridge
    restart: unless-stopped
    ports:
      - "3000:3000"
    volumes:
      - ${CONFIG_DIR}/ha-wa-bridge/.wa_auth:/usr/src/app/.wwebjs_auth
    environment:
      # Access token for Home Assistant. Leave unset to have one generated and
      # stored in .wa_auth/auth_token (enter it when adding the integration).
      # - AUTH_TOKEN=change-me-to-a-long-random-string
      # - WA_WEB_VERSION=2.3000.1017054665 # Emergency pin only; empty = always the live WhatsApp Web version

      # Forward messages you send yourself (groups only)
      - DETECT_OWN_MESSAGES=false

      # Incoming message mode: all | disabled | groups_only | numbers_only
      # - all          → forward everything (default)
      # - disabled     → send-only mode, no incoming messages processed
      # - groups_only  → group chats only, ignore 1-to-1 messages
      # - numbers_only → direct messages from ALLOWED_NUMBERS only
      - INCOMING_MESSAGES_MODE=all

      # Logging level for incoming messages: COMPACT | FULL | NONE
      # - COMPACT → log only sender and message type (default)
      # - FULL    → log entire message payload, including its text
      # - NONE    → disable logging for incoming messages
      - INCOMING_MESSAGE_LOG_LEVEL=COMPACT

      # Comma-separated group names — only these groups are forwarded (optional)
      # - ALLOWED_GROUPS=Family Group,Work Team

      # Comma-separated phone numbers without '+' — only these numbers are forwarded (optional)
      # Required for numbers_only mode
      # - ALLOWED_NUMBERS=40741234567,49123456789
```

Then run:
```bash
docker-compose up -d
```

### 2. Install the Integration

#### Option A: HACS (Recommended)
1.  Make sure [HACS](https://hacs.xyz/) is installed.
2.  Go to HACS > Integrations > Top-right menu > **Custom repositories**.
3.  Add `https://github.com/danyial/ha-wa-bridge` as an **Integration**.
4.  Click **Download**.
5.  Restart Home Assistant.

#### Option B: Manual Installation
1.  Copy the `custom_components/whatsapp` folder to your Home Assistant `config/custom_components/` directory.
2.  Restart Home Assistant.

## Security

- **Access token.** Every WebSocket connection must send `Authorization: Bearer <token>`; without it the bridge answers `401` and nothing else. The add-on generates the token on first start (`/data/auth_token`, readable only by the add-on) and hands it to Home Assistant through Supervisor discovery. Set the option `auth_token` (Docker: `AUTH_TOKEN`) only to use a token of your own.
- **No host port.** The add-on does not publish port 3000 on the host; Home Assistant reaches it on the internal add-on network. Map a host port in the add-on's *Network* settings only for an external client, and keep the token secret.
- **Chromium** runs without `--disable-web-security` and `--ignore-certificate-errors`.
- **Logs** contain no message text by default (`COMPACT`), no media payloads and never the token.
- **Media URLs** may point anywhere reachable over http(s), including the LAN (cameras); downloads are limited to 16 MB and 30 s. Local files must be in `allowlist_external_dirs`.
- **Group names are ambiguous.** Sending to a group name fails if more than one group has that name (someone could create a group with the same name and add you); use `group_id` for anything important.
- The WhatsApp session (keys to your account) lives in the add-on's `/data` and is part of Home Assistant backups. Encrypt your backups.

## Configuration

### Add-on Configuration

- **`auth_token`** *(optional)*: Access token the bridge requires. Leave empty to use the generated one.

- **`restart_unresponsive_minutes`** *(optional)*: Restart WhatsApp Web after it has been unresponsive for this many minutes. Empty or `0`: only report it.
If you are using the Home Assistant Add-on, you can configure the following options in the add-on configuration tab:

- **`detect_own_messages`**: Set to `true` to forward messages sent by your own account (e.g., from WhatsApp Web or your phone). Works for group messages only. Default: `false`.

- **`incoming_messages_mode`**: Controls which incoming messages are forwarded to Home Assistant. Accepted values:
  - `all` *(default)* – all messages are forwarded, same as previous behaviour.
  - `disabled` – the message listener is **never registered**; the container uses minimal resources and is still fully capable of sending messages.
  - `groups_only` – only messages from group chats are forwarded; 1-to-1 conversations are ignored.
  - `numbers_only` – only direct messages from phone numbers listed in `allowed_numbers` are forwarded; group messages are ignored.

- **`incoming_message_log_level`**: Controls the amount of detail logged in the Add-on logs when receiving messages or poll votes. Accepted values:
  - `COMPACT` *(default)* – logs only basic info like sender identification and message type ("Message received from X"). Message bodies and selected options are omitted.
  - `FULL` – logs the entire raw message payload, including its text.
  - `NONE` – disables all logging for incoming messages. This is the most private option.

- **Filters combined:** with both `allowed_groups` and `allowed_numbers` set (mode `all`), a message passes if it comes from an allowed group **or** is a direct message from an allowed number. Before 3.0 that combination dropped every message. Filters fail closed: a message whose group name or sender number cannot be determined does not pass a list.

- **`allowed_groups`**: An optional list of group names. When set, **only** messages from groups whose name exactly matches one of the entries are forwarded. Useful if you only care about a single group. Example:
  ```yaml
  allowed_groups:
    - "Family Group"
    - "Work Team"
  ```
  Leave empty (default) to apply no group-name filter.

- **`allowed_numbers`**: An optional list of phone numbers in international format (`+49 170 …` or `49170…`). When set, **only** direct messages from those numbers are forwarded; senders hidden behind a LID match once their number is resolved. Required when using `numbers_only` mode; also works as an extra filter in `all` mode. Example:
  ```yaml
  allowed_numbers:
    - "40741234567"
    - "49123456789"
  ```
  Leave empty (default) to apply no number filter.

### Docker Compose Configuration
All options are also available as environment variables:
```yaml
    environment:
      - DETECT_OWN_MESSAGES=true
      # Options: all | disabled | groups_only | numbers_only
      - INCOMING_MESSAGES_MODE=disabled
      # Options: COMPACT | FULL | NONE
      - INCOMING_MESSAGE_LOG_LEVEL=COMPACT
      # Access token (optional; generated into the auth volume if unset)
      - AUTH_TOKEN=change-me-to-a-long-random-string
      # Comma-separated group names (optional)
      - ALLOWED_GROUPS=Family Group,Work Team
      # Comma-separated phone numbers without '+' (optional)
      - ALLOWED_NUMBERS=40741234567,49123456789
```

### Integration Setup

**With the add-on:** after starting it, Home Assistant shows a discovered **WhatsApp** integration under *Settings → Devices & services*. Click **Add** and confirm.

**Bridge elsewhere (Docker):** *Add integration → WhatsApp*, then enter the WebSocket URL (e.g. `ws://192.168.1.10:3000`) and the access token (`AUTH_TOKEN`, or the generated `auth_token` file in the bridge's data volume).

Then check your **notifications** (bell icon) for the QR code and scan it with WhatsApp on your phone (*Settings → Linked devices*).

**Upgrading from 2.x:** the bridge now requires a token. After updating add-on and integration, Home Assistant asks you to re-authenticate the integration; with the add-on, restarting it is enough (discovery supplies the token).

### Entities

The integration adds a **WhatsApp** device:

| Entity | Meaning |
|---|---|
| `sensor.whatsapp_status` | `initializing`, `qr` (waiting for scan), `authenticated` (syncing), `ready`, `unresponsive`, `disconnected`, `auth_failure`, `bridge_offline` (add-on not reachable). Attributes: linked `phone`, WhatsApp socket state `wa_state`, `reason`, bridge and whatsapp-web.js versions. |
| `binary_sensor.whatsapp_connected` | On when messages can be sent (`ready`). |
| `image.whatsapp_qr_code` | The QR code to link your account; available only while waiting for a scan. |
| `button.whatsapp_restart_whatsapp_web` | Restarts WhatsApp Web in the add-on (keeps the link). |
| `button.whatsapp_log_out_unlink_device` | Logs out and unlinks this device in WhatsApp; a new QR scan is needed. **Disabled by default.** |

**Unresponsive detection.** whatsapp-web.js can keep reporting "ready" while WhatsApp Web has hung. While ready, the bridge probes the page every 30 s (browser alive, WhatsApp socket state readable within 10 s); two failed probes in a row switch the status to `unresponsive` and log a warning. The add-on option `restart_unresponsive_minutes` restarts WhatsApp Web automatically after that many minutes (default: off). Example alert:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.whatsapp_connected
    to: "off"
    for: "00:10:00"
actions:
  - action: persistent_notification.create
    data:
      message: "WhatsApp: {{ states('sensor.whatsapp_status') }}"
```

### Service responses

`send_message`, `send_poll`, `send_event`, `send_broadcast` and `get_groups` can return data (`response_variable` in scripts), e.g. the sent message id or the group list. All services now fail with an error instead of silently doing nothing when the bridge is unreachable, WhatsApp is not linked, or a target is invalid.

## Development

```sh
uv venv -p 3.14 .venv && uv pip install -p .venv -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
(cd wa-bridge && npm test)
```

The Python tests run the integration against a scripted fake bridge (a real WebSocket server on loopback, `tests/conftest.py`). The bridge tests use `node --test` and do not need Chromium.

CI (GitLab) runs ruff, pytest, the bridge tests, hassfest, offline checks (`scripts/check_hacs.py`, `check_versions.py`, `check_addon.py`) and a test build of the add-on image. `hacs/action` needs GitHub and cannot run there.

Add-on, bridge and integration share one version: `wa-bridge/config.yaml`, `wa-bridge/package.json` and `custom_components/whatsapp/manifest.json` must match (checked in CI).

## Dependency updates

whatsapp-web.js breaks whenever WhatsApp changes WhatsApp Web, so it is pinned exactly (npm release, or a commit of `wwebjs/whatsapp-web.js` main as a tarball URL when a needed fix is not released yet) and locked in `wa-bridge/package-lock.json`. The WhatsApp Web version itself is not pinned: the bridge always loads the live one (add-on option `wa_web_version` is an emergency pin).

The CI job `wwebjs-update` (`scripts/wwebjs_update.py`) proposes updates as merge requests: a newer npm release, or, for a commit pin, a newer main head. Setup:

1. Project access token: Settings → Access tokens, role *Developer*, scopes `api` and `write_repository`.
2. CI/CD variable `WWEBJS_BOT_TOKEN` = that token, *masked* and *protected*.
3. Pipeline schedule on `main` (e.g. weekly) with the variable `WWEBJS_UPDATE=true`.

A green pipeline only proves the image builds. Check pairing, receiving and sending on a real session before merging an update.

## Releasing

Development happens in a GitLab repository; GitHub is a push mirror of `main` and of protected `v*` tags. HACS and the Home Assistant add-on store read from GitHub.

1. Bump the version in all three files with `python scripts/bump_version.py 3.0.0`, merge to `main`, wait for a green pipeline.
2. Create the tag and release on GitLab from `main`:
   ```sh
   glab release create v3.0.0 --ref main --name v3.0.0 --notes-file notes.md
   ```
   The tag must match the version with a `v` prefix.
3. Wait until the mirror has pushed the tag (usually seconds; if it hangs, trigger a sync with `glab api -X POST "projects/:id/remote_mirrors/<mirror-id>/sync"`):
   ```sh
   gh api repos/danyial/ha-wa-bridge/git/refs/tags/v3.0.0
   ```
4. The mirrored tag triggers the GitHub workflow `Builder`, which publishes `ghcr.io/danyial/ha-wa-bridge:<version>` (amd64, aarch64). Wait for it: `gh run watch -R danyial/ha-wa-bridge`. The add-on store installs exactly this image version.
5. Publish the same notes on GitHub; this is what HACS offers as an update:
   ```sh
   gh release create v3.0.0 --repo danyial/ha-wa-bridge --verify-tag --title v3.0.0 --notes-file notes.md
   ```

Commits made through the GitLab web UI (including merge commits) carry the author's GitLab commit email and are mirrored to the public GitHub repository.

## Credits 
Powered by [whatsapp-web.js](https://wwebjs.dev/).

## Support the project
- [Buy Me a Coffee](https://buymeacoffee.com/raulpetruta)
- [PayPal](https://www.paypal.me/raulpetruta98)

## Supporters 🙏

Thanks to these legends for buying me a [coffee](https://buymeacoffee.com/raulpetruta):

- Jblox6
- @louis_remi
- Pattio
- Ni3k

Thanks to these legends for their [PayPal](https://www.paypal.me/raulpetruta98) support:

- Enrique Alarcon

## Star History

<a href="https://www.star-history.com/?repos=raulpetruta%2Fha-wa-bridge&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=raulpetruta/ha-wa-bridge&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=raulpetruta/ha-wa-bridge&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=raulpetruta/ha-wa-bridge&type=date&legend=top-left" />
 </picture>
</a>

## License
[MIT](LICENSE)
