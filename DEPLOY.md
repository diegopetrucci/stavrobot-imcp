# iMCP bridge and Stavrobot plugin deployment

This is a **manual operator runbook**. The repository contains source and
templates only. Preparing this checkout does not create a token, copy files
outside the repository, change chezmoi, install the plugin, load a LaunchAgent,
start a bridge, run Docker/OrbStack, or invoke an iMCP tool.

The bridge exposes an authenticated HTTP boundary for the iMCP services enabled
by the operator:

```text
iMCP app (macOS permissions and client approval)
  -> local MCP transport (Bonjour discovery, forced loopback)
  -> 127.0.0.1:8766/bridge (authenticated host bridge)
  -> host.docker.internal:8766/bridge (plugin-runner)
  -> Stavrobot imcp plugin
```

## Safety gates

1. Obtain explicit human approval for the services, tools, agents, and first
   read-only test operation. iMCP can expose personal calendar, contacts,
   messages, reminders, location, maps, and weather data; enable only the
   services that have been selected.
2. Keep the bridge bound to `127.0.0.1` and use the fixed HTTP bridge port
   `8766`. Do **not** change the bind to `0.0.0.0` automatically if the
   container check fails. Stop and diagnose the host-gateway path instead.
3. Keep the bridge token out of agent chat, shell output, logs, commits, and
   this repository. The host token file, the host allowlist, and the installed
   plugin `config.json` are separate configuration; the first and last may be
   secret-bearing, and none belongs in source.
4. Use a trusted host allowlist with explicit iMCP tool names. Although
   `bridge/server.py` defaults to `*` when no allowlist is supplied, deployment
   through the helper or LaunchAgent wrapper below requires
   `~/.config/imcp-bridge-tools.json` so least privilege is deliberate.
5. Keep the timeout ladder intact:
   `15s (bridge) < 20s (plugin client) < 30s (synchronous plugin-runner)`.
   The helper and LaunchAgent wrapper explicitly pin the bridge's 10-second
   `--call-timeout` default, which yields its 15-second outer deadline. Any
   override must keep the resulting bridge outer deadline strictly below the
   plugin's 20 seconds.
6. Use exactly one supervisor at a time: either the tmux start helper or the
   direct LaunchAgent template below. Running both causes a collision on
   `127.0.0.1:8766`.

## Prerequisites and virtual environment

In a trusted local terminal, prepare the checkout and its explicit Python
virtual environment. These commands are instructions for a later operator;
they were not run as part of authoring this runbook:

```sh
cd "$HOME/Developer/stavrobot-imcp"
python3.14 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

The start helper and plist intentionally invoke
`$HOME/Developer/stavrobot-imcp/.venv/bin/python`, not whichever `python3` an
interactive shell happens to select. If the checkout is elsewhere, render or
adapt the paths deliberately rather than adding a second, untracked runtime.

## 1. Manually prepare iMCP and macOS permissions

All prompts and approvals in this section are manual:

1. Open the installed iMCP app in the logged-in macOS user session.
2. Enable only the agreed iMCP services. Do not infer availability from an
   upstream source checkout or from an old tool list.
3. In **System Settings > Privacy & Security**, grant only the macOS access
   required by those services. Complete any iMCP-native permission flow. For
   Messages history, use the app's documented file-selection flow if it asks
   for access; this integration does not describe or test message sending.
4. Start the bridge once the app is ready. On the first MCP connection, iMCP
   may display a **Connection Request** window for the client named
   `stavrobot-imcp-bridge`. Review the client and approve it manually. Do not
   treat a missing prompt as proof that permissions or client trust are correct;
   check the app's remembered-client and service settings.
5. Use a disposable, read-only operation for the first end-to-end test. Do not
   use a write, delete, message, reminder, or calendar mutation as a health
   check.

A macOS permission prompt must not be left waiting inside a synchronous
Stavrobot tool call. Resolve the prompt before the plugin-runner verification.

## 2. Create the host token securely (operator action only)

Generate the token in a trusted local terminal, never in agent chat. The
checkout and an available Python 3 interpreter are prerequisites; the helper
uses only Python's standard library and creates the configuration directory if
needed:

```sh
cd "$HOME/Developer/stavrobot-imcp"
./scripts/create_token.sh
```

The helper writes `~/.config/imcp-bridge.token` without printing its contents,
uses mode `0600`, and refuses symlink, nonregular, empty, or invalid existing
token files. Repeating the command preserves an existing valid token and reapplies
owner-only permissions; it does not rotate or overwrite credentials. If this
command newly created the token and you need to undo only that creation, first
confirm it did not exist before the command, then remove it from the trusted
terminal:

```sh
rm "$HOME/.config/imcp-bridge.token"
```

Deleting the token file does not immediately revoke a credential from a
running bridge: the bridge retains its startup credential in memory until its
active supervisor is stopped. Stop the tmux supervisor or boot out the
LaunchAgent before deleting or replacing the token. If the token is deleted
first, the running bridge remains live; after it exits, the `KeepAlive`
LaunchAgent cannot pass preflight and retries every 30 seconds, causing
continued log growth until that job is booted out. Do not use deletion as a
rotation procedure; an approved rotation must stop the active supervisor,
update the host file and Stavrobot plugin configuration together, then start
one supervisor again. Never use `cat` on the token in a chat or log, and do not
put its value in the plist, `config.json.example`, a command transcript, or
Git.

Create the separate host allowlist in the same trusted terminal. Use a JSON
object with only the exact, approved iMCP tool names; never use `*` for a
least-privilege deployment. This example selects two read-only tools and is a
configuration example, not an instruction to enable services that were not
approved:

```sh
allowlist_file="$HOME/.config/imcp-bridge-tools.json"
if [ ! -s "$allowlist_file" ]; then
  ( umask 077
    mkdir -p "${allowlist_file%/*}"
    cat > "$allowlist_file" <<'JSON'
{"tools":["calendars_list","reminders_lists"]}
JSON
  )
fi
chmod 600 "$allowlist_file"
```

Replace those example names with the exact names selected by the operator
(for example, after reviewing the read-only `tools/list` metadata), keeping the
list explicit and excluding every unapproved read or write tool. The start
helper refuses a missing, empty, unreadable, or group/other-accessible allowlist
and enforces its owner-only mode; it passes this file with `--allowlist-file` to
the bridge. The direct plist invokes `scripts/run_launchd_bridge.py`, whose private
configuration preflight runs before it execs `bridge/server.py` and enforces
these file modes.
The allowlist contains no credential, but keep it owner-only so it cannot be
silently broadened by another account.

## 3. Start the host bridge

The in-repository helper is `scripts/start-stavrobot-imcp-bridge`. It sets the
non-interactive Homebrew/Python `PATH`, checks the explicit venv Python,
protected token file, and owner-only allowlist, uses the tmux session named
exactly `stavrobot-imcp-bridge`, and starts with `--call-timeout 10` and:

```text
127.0.0.1:8766/bridge
```

Run it manually from the checkout after the iMCP service and macOS permission
prerequisites are complete. Client approval is deliberately the next step in
§3.1, triggered by the authenticated host-side `list_tools` request:

```sh
cd "$HOME/Developer/stavrobot-imcp"
chmod +x scripts/start-stavrobot-imcp-bridge
scripts/start-stavrobot-imcp-bridge
```

The helper only manages its exact reserved tmux session. Repeating a successful
start converges on one session; it does not kill other tmux sessions or print
`lsof` details. If the fixed port is already owned by a process without that
session, it fails clearly and leaves the existing listener alone. Do not work
around that error by changing the bridge port or exposing another interface.
The helper passes `--allowlist-file ~/.config/imcp-bridge-tools.json` and
`--call-timeout 10`; do not remove either safety boundary. The dynamic port
used internally by iMCP is not a plugin or HTTP port and must not be added to
configuration or logs.

### 3.1 Trigger the first host-side MCP connection and approve it manually

After the bridge is listening, run this **on the macOS host**, not in
`plugin-runner`. It sends exactly one authenticated, read-only `list_tools`
POST to the fixed bridge endpoint. The repository helper reads the token file
internally, keeps it in memory, uses a direct no-proxy/no-redirect HTTP
connection, bounds the response read, and prints only generic status messages.
It therefore triggers iMCP's client request for `stavrobot-imcp-bridge` without
putting the token, response body, or tool metadata in a command argument or
output:

```sh
cd "$HOME/Developer/stavrobot-imcp"
./scripts/check_bridge.sh
```

The helper prints conditional approval guidance before waiting. Watch iMCP
while this command waits and approve the **Connection Request** only if iMCP
shows it. If no prompt appears, a successful listing needs no further approval.
The bridge's 15-second outer deadline is shorter than this client's 20-second
socket timeout. If the first read-only request expires at 15 seconds (or
reaches the 20-second client timeout), wait for the command to exit and rerun
`./scripts/check_bridge.sh` after resolving the approval. Rerunning this
read-only discovery request is safe; do not generalize that retry rule to a
`call_tool` whose outcome could be unknown. The helper never invokes an iMCP
tool and never retries automatically.

The unauthenticated GET in §6.1 is only a route/authentication check. It cannot
trigger iMCP client approval because the bridge rejects it before opening an
MCP session.

## 4. Copy or publish the plugin source bundle

The source bundle is the contents of `plugin/imcp/`, not the monorepo root. The
**preferred and supported installation is URL installation** from the public
standalone repository:
`https://github.com/diegopetrucci/stavrobot-imcp-plugin`. Its root must contain
`manifest.json`; the monorepo URL by itself is not an installable plugin URL.

For each release, maintainers must manually sync the reviewed contents of
`plugin/imcp/` to that standalone repository root and verify the root manifest
before publishing. Exclude local configuration, caches, and credentials; this
is publication guidance only and does not automate synchronization.

For a deliberately local installation, an operator may copy the source tree to
the Stavrobot checkout's plugin data directory. Do not copy the live
configuration from another installation and do not run this during repository
authoring:

```sh
STAVROBOT_ROOT="/path/to/stavrobot"
mkdir -p "$STAVROBOT_ROOT/data/plugins/imcp"
rsync -a \
  --exclude config.json \
  --exclude '.DS_Store' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$HOME/Developer/stavrobot-imcp/plugin/imcp/" \
  "$STAVROBOT_ROOT/data/plugins/imcp/"
```

A local copy is not complete when `rsync` finishes. It requires a **controlled
`plugin-runner` restart** so its startup migration creates the dedicated
`plug_imcp` user and chowns the bundle to that user. This restart is an
operator action that requires an intentionally available deployment:

```sh
cd /path/to/stavrobot
docker compose restart plugin-runner
```

After the restart, verify the actual mounted `/plugins` directory, the bundle
path, and ownership from inside `plugin-runner` before configuring or invoking
the tools. Do not print `config.json`:

```sh
docker compose exec -T plugin-runner sh -c '
  id plug_imcp
  test -d /plugins
  test -f /plugins/imcp/manifest.json
  stat -c "%U:%G %a %n" /plugins /plugins/imcp /plugins/imcp/manifest.json
'
```

If the runner reports a different bundle path, use that actual path for the
later smoke command and verify its files are owned by `plug_imcp`; do not
silently run the bundle as root. A supported URL install still requires the
same post-install `/plugins` and ownership check.

The resulting layout is:

```text
$STAVROBOT_ROOT/data/plugins/imcp/
├── manifest.json
├── config.json                 # created/configured after install; secret
├── _bridge.py
├── imcp_list_tools/
│   ├── manifest.json
│   └── run.py
└── imcp_call/
    ├── manifest.json
    └── run.py
```

`config.json.example` is documentation, not a live configuration. Keep the
installed `config.json` out of Git and do not return it through an agent tool.
If the plugin is installed through Stavrobot instead of copied, confirm that
the plugin runner created the same layout before proceeding.

## 5. Configure the plugin without exposing the token

Use Stavrobot's web settings or another trusted host-side secret/configuration
path. Do not paste `bridge_token` into an agent prompt or chat. The effective
configuration is equivalent to:

```json
{
  "bridge_url": "http://host.docker.internal:8766/bridge",
  "bridge_token": "<the protected host token>"
}
```

The URL must use `host.docker.internal` because the tool executes inside
`plugin-runner`; `127.0.0.1` and `localhost` there refer to the container, not
the macOS host. Keep the URL on the documented fixed bridge port `8766`.

### Plugin and agent permissions

After installation, use the Stavrobot web UI's plugin permissions control:

- Start with an explicit least-privilege list such as
  `["imcp_list_tools"]`.
- Add `"imcp_call"` only after the approved iMCP tools and first operation are
  known. The host bridge's own allowlist and the plugin permission list are
  separate layers.
- `[]` disables the plugin and `["*"]` permits every plugin tool; avoid `*`
  for a personal-data bridge unless that broad access has been explicitly
  approved.
- Grant the plugin only to the intended private/main agent through the
  agent-level allowed-plugin setting. **Exclude the iMCP plugin from every
  `telegram-group-*` agent.** Do not publish or rely on one machine-specific
  group-agent ID; inspect the actual agent IDs and each `allowed_plugins` value
  in the web UI before and after the change. Verify that every matching
  `telegram-group-*` agent remains excluded before testing any tool.

The `permissions` key is system-managed by Stavrobot's web UI; plugin tools do
not read it. Keep group routing and private-agent access as a separate review
from the host bridge's iMCP service selection, using the actual IDs and
`allowed_plugins` values shown by the web UI rather than display names alone.

## 6. Required reachability verification from `plugin-runner`

A host-only `curl` or a bridge process visible in tmux is not sufficient. The
following two checks must be run by an operator from the actual Stavrobot
`plugin-runner` container after its services are intentionally available.
These checks require an intentionally available deployment and are operator-run.

### 6.1 Check the host gateway and auth boundary

An unauthenticated GET should reach the bridge and return `401`; a connection
or DNS error is a failed gate:

```sh
cd /path/to/stavrobot
docker compose exec -T plugin-runner python3 - <<'PY'
import urllib.error
import urllib.request

request = urllib.request.Request(
    "http://host.docker.internal:8766/bridge",
    method="GET",
)
try:
    with urllib.request.urlopen(request, timeout=5) as response:
        status = response.status
except urllib.error.HTTPError as error:
    status = error.code
if status != 401:
    raise SystemExit(f"expected 401 from the unauthenticated bridge check, got {status}")
print(
    "plugin-runner reached host.docker.internal:8766 "
    "(unauthenticated request rejected)"
)
PY
```

This check intentionally sends no credential. It confirms the required
container-to-host route and that the bridge has not silently removed auth. It
cannot trigger iMCP client approval: authentication is rejected before the
bridge opens an MCP session.

### 6.2 Check authenticated plugin traffic through the same route

With `bridge_url` and `bridge_token` configured in the installed plugin, first
confirm the actual bundle path inside the running `plugin-runner`. Do not
assume that a host checkout path is the mounted path, and do not inspect
`config.json`:

```sh
cd /path/to/stavrobot
BUNDLE_PATH="$(docker compose exec -T plugin-runner sh -c '
  set -eu
  for candidate in /plugins/*; do
    if [ -f "$candidate/manifest.json" ] &&
       grep -q \
         "\"name\"[[:space:]]*:[[:space:]]*\"imcp\"" \
         "$candidate/manifest.json"; then
      printf "%s" "$candidate"
      exit 0
    fi
  done
  exit 1
')" || {
  echo "iMCP plugin bundle was not found in /plugins" >&2
  exit 1
}
case "$BUNDLE_PATH" in
  /plugins/*) ;;
  *) echo "plugin bundle path was outside /plugins" >&2; exit 1 ;;
esac
printf 'bundle path: %s\n' "$BUNDLE_PATH"

docker compose exec -T plugin-runner sh -c \
  'id plug_imcp && stat -c "%U:%G %a %n" /plugins'
docker compose exec -T plugin-runner stat -c '%U:%G %a %n' \
  "$BUNDLE_PATH" "$BUNDLE_PATH/manifest.json"
```

The inspection must show the dedicated `plug_imcp` user and the bundle owned
by that user (the `/plugins` mount itself may have a different mount owner).
If it does not, stop and repair the controlled install/restart before running
a tool. A supported URL install still requires this check.

Now run the read-only listing smoke as `plug_imcp`, not root. The non-login
`sh -c` is intentional. The installed tool reads the token internally; no
token is placed in this command or its output:

```sh
docker compose exec -T -u plug_imcp \
  -w "$BUNDLE_PATH/imcp_list_tools" plugin-runner \
  sh -c 'printf "{}\n" | ./run.py' \
  | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
if payload.get("ok") is not True:
    raise SystemExit("authenticated iMCP listing failed")
tools = payload.get("result", {}).get("tools")
if not isinstance(tools, list):
    raise SystemExit("authenticated iMCP listing returned no tool list")
print(f"authenticated plugin-runner bridge check passed ({len(tools)} tools listed)")
'
```

This is the required verification **from `plugin-runner` via
`host.docker.internal:8766`**. Do not substitute a host-only test. After it
passes, perform only the approved read-only smoke operation and confirm that
permissions still exclude every `telegram-group-*` agent.

If either check fails, keep the host bind at `127.0.0.1`. **Do not widen it to
`0.0.0.0` automatically if it fails.** Stop, inspect the bridge logs without
printing credentials, check host-gateway/DNS and local firewall behavior, and
review the container networking design with an operator. A wider bind would
make authenticated personal-data tools reachable from unintended interfaces.

## Login startup and crash recovery

Run from the repository after preparing the private token and allowlist. The
login-service prerequisite is the already-installed app bundle at
`/Applications/iMCP.app`; the installer only opens it and does not install or
copy iMCP:

```sh
./.venv/bin/python scripts/install_login_services.py
```

The installer validates configuration and port availability, renders the templates,
and loads two per-user LaunchAgents:

- `com.stavrobot.imcp-app` opens iMCP at GUI login. Quitting iMCP deliberately
  leaves it closed until it is reopened or the next login.
- `com.stavrobot.imcp` runs the bridge through a private-configuration preflight.
  `KeepAlive=true` restores it after an exit; `ThrottleInterval=30` bounds
  repeated restarts. Missing/invalid configuration or port conflicts fail with
  a generic diagnostic; no conflicting process is killed. Because `KeepAlive`
  remains enabled, a persistent preflight failure is retried every 30 seconds;
  use `launchctl bootout` to stop the retry loop and prevent continued log
  growth while repairing the configuration.

These services start after login, not before login or FileVault unlock. iMCP's
existing client trust and macOS permissions still apply. An app that has not
started yet is handled by the bridge's lazy connection on later requests.

The installer accepts matching rendered files and leaves already-active jobs
loaded; it refuses drift rather than overwriting an existing file. Stop an
existing tmux bridge explicitly before installation. To update installed login
services, boot out both labels and reconcile their rendered plists first:

```sh
launchctl bootout "gui/$(id -u)/com.stavrobot.imcp"
launchctl bootout "gui/$(id -u)/com.stavrobot.imcp-app"
```

Use one bridge supervisor, never tmux and launchd together.

Logs are in `~/Library/Logs/Stavrobot/imcp-bridge.{out,err}.log`. The launch job
uses umask 077. Treat logs as operational data and avoid publishing them.

Chezmoi may manage the two LaunchAgents using explicit `.plist.tmpl` source
names. The installer renders both templates with the home directory and checks
the resulting files before loading; if rendering manually, validate both with
`plutil -lint` first. Scope applies to those two files; do not apply unrelated
configuration drift. Keep the token and allowlist unmanaged. Runtime source
and its venv must remain available at `~/Developer/stavrobot-imcp`.

Check the authenticated connection with `./scripts/check_bridge.sh`. A
successful unauthenticated 401 establishes only HTTP reachability. A successful
authenticated listing establishes the iMCP session; actual tool access remains
controlled by the allowlist.

To stop automatic restarts, boot out the bridge job (killing its PID alone
causes launchd to restart it). Remove/disable both login jobs to undo startup:

```sh
launchctl bootout "gui/$(id -u)/com.stavrobot.imcp"
launchctl bootout "gui/$(id -u)/com.stavrobot.imcp-app"
```

Remove the corresponding managed LaunchAgent files only when uninstalling.
Keep private credentials unless intentionally removing or rotating them.

## Rollback and uninstall

Perform rollback in the reverse order, with explicit approval:

1. In the Stavrobot web UI, set the iMCP plugin permissions to `[]`, remove it
   from the intended agent, and remove the bridge URL/token from the installed
   plugin configuration. **Exclude it from every `telegram-group-*` agent.**
   Inspect the actual agent IDs and `allowed_plugins` values in the web UI to
   confirm no matching group agent retains access.
2. Stop only the supervisor that was used. For the manual helper, the reserved
   session is:

   ```sh
   tmux kill-session -t stavrobot-imcp-bridge
   ```

   For LaunchAgents, use the matching per-user `launchctl bootout` operation
   for both `com.stavrobot.imcp` and `com.stavrobot.imcp-app` before removing
   either rendered plist. This bootout is also required to stop a persistent
   preflight retry loop and its log growth. Do not kill an unrelated tmux
   session or listener.
3. Remove or quarantine only the deployed copy at
   `$STAVROBOT_ROOT/data/plugins/imcp/` after preserving any approved audit or
   configuration record. Do not remove `plugin/imcp/` from this source checkout
   as part of deployment rollback.
4. For chezmoi-managed LaunchAgents, review `chezmoi status` and
   `chezmoi diff`, then remove or reconcile the corresponding source entries
   through the deliberate chezmoi workflow before removing rendered files.
   Do not delete only a managed rendered file, since chezmoi will recreate it;
   leave unrelated managed state untouched.
5. After all clients are disabled and the active bridge supervisor has been
   stopped, remove the host token file using the operator's secure-storage
   policy, or rotate/revoke it if any copy may remain. Stopping first matters:
   a running bridge retains its in-memory credential, while deleting first
   leaves it live until exit and makes a `KeepAlive` LaunchAgent enter
   preflight retry. Do not print either the old or replacement token.
6. Optionally disable the selected iMCP services and revoke remembered client
   approval/macOS permissions manually. Leave unrelated existing plugins and
   their credentials untouched.

After rollback, verify that no process is listening on the fixed bridge port
and that every `telegram-group-*` agent's actual `allowed_plugins` value
excludes iMCP. Keep the source bundle and this runbook if a later re-deployment
is approved.

## Temporary dynamic-port / forced-loopback workaround

The iMCP app's local MCP service advertises a Bonjour `_mcp._tcp.local.` service
with a dynamic internal port. The current transport uses Bonjour only to
identify the local service and extract that port; it discards all advertised
interface addresses and connects exclusively to `127.0.0.1:<discovered-port>`.
The Stavrobot-facing HTTP boundary is separately fixed at
`127.0.0.1:8766/bridge`. The discovered iMCP port is an internal implementation
detail: it is not a plugin URL, must not be hard-coded, and must not be printed
in operational output.

This forced-loopback/dynamic-port arrangement is a temporary compatibility
workaround while a stable, documented host/container transport is tracked:

- [stavrobot-imcp issue #1](https://github.com/diegopetrucci/stavrobot-imcp/issues/1)
- [upstream mattt/iMCP issue #142](https://github.com/mattt/iMCP/issues/142)

Do not remove the workaround merely because one live call succeeds. Remove or
replace it only after all of the following are true:

- a released iMCP version, including the version actually installed by the
  operator, documents a stable supported transport or configurable endpoint;
- the relevant upstream/project issue status and security implications have
  been reviewed;
- reconnect after an iMCP restart and a changed internal port is tested;
- authenticated reachability is reverified from `plugin-runner` through
  `host.docker.internal`, with the bridge still restricted to an intentional
  interface; and
- transport code, start/plist configuration, tests, and this runbook are
  updated together, retaining token protection and the no-LAN-exposure rule.

Until those criteria are met, keep Bonjour discovery and forced loopback. Never
respond to a failed container check by binding the bridge to `0.0.0.0` or by
exposing the discovered internal port.
