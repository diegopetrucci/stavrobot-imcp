# iMCP bridge plugin for Stavrobot

Connects Stavrobot to [iMCP](https://github.com/mattt/iMCP), exposing macOS-native services to the assistant through a host-side authenticated bridge.

## Services

When enabled in iMCP (1.8.2+) and allowlisted on the bridge:

- Calendar (including `events_update`), Contacts, Reminders (update/delete, list create/rename/delete, recurrence)
- Messages (attachments, `chatId`, `messages_attachment_read`), Phone calls, Voicemail
- Mail (read-only search/read plus `mail_compose` draft), Notes, Voice Memos
- Music, Home (HomeKit; requires the self-signed iMCP Helper)
- Location, Maps, Weather, Shortcuts, Capture (camera, audio, screenshot), Utilities

Mail, Notes, Voice Memos, Voicemail, and Messages attachments need folder access granted in iMCP. The bridge caps responses at 256 KiB with a 10 s call timeout, so large binary results (audio, attachments, captures) may be truncated or fail; text and transcripts work.

## Prerequisites

- A Mac running iMCP **1.8.2 or newer**, with the bundled
  `Contents/MacOS/imcp-server` executable and the services you want enabled.
- The host iMCP bridge running and reachable from the Stavrobot plugin-runner (the operator prepares this on the host before installing the plugin).
- A bridge token and tool allowlist created on that host.

The host bridge uses the bundled stdio server; the plugin continues to use its
authenticated HTTP contract and does not connect to iMCP directly.

## Install

Tell Stavrobot to install `https://github.com/diegopetrucci/stavrobot-imcp-plugin`

## Configuration

### `bridge_url`

The HTTP URL of the host iMCP bridge.

Default: `http://host.docker.internal:8766/bridge`

Note: `127.0.0.1` inside the plugin-runner resolves to the container, not the host. Use `host.docker.internal` so the request reaches the Mac.

### `bridge_token`

The Bearer token the operator created for the bridge, stored in the host's protected token file.

Configure `bridge_token` through Stavrobot's web settings or the trusted host-side secret path, never by pasting it into agent chat.

The tools send the token only as a Bearer credential and never include it in output or error messages.

## Tools

### `imcp_list_tools`

Reports the tool names and input schemas the bridge currently exposes. The available tools depend on which iMCP services the operator enabled and which tools are on the bridge allowlist.

### `imcp_call`

Forwards a tool name and JSON arguments to the bridge and returns the bridge's structured MCP result, including `error` and `truncated` fields.
