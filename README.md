# Stavrobot iMCP bridge and plugin

This repository contains the source for a host-side iMCP bridge and the
Stavrobot plugin that calls it. It is source and documentation only: preparing
this checkout does not install the plugin, create a token, start a bridge,
connect to live iMCP, or verify a Stavrobot deployment.

## Component layout

The integration has separate host, plugin, and operator boundaries:

```text
iMCP app (macOS permissions and manual client approval)
  -> Bonjour discovery and forced-loopback MCP transport
  -> bridge/server.py at 127.0.0.1:8766/bridge (authenticated host bridge)
  -> host.docker.internal:8766/bridge (plugin-runner route)
  -> plugin/imcp/ (Stavrobot plugin bundle)
  -> Stavrobot plugin tools and the approved agent
```

- `bridge/server.py` owns the authenticated HTTP boundary and keeps the
  discovered iMCP connection on loopback. See [`bridge/README.md`](bridge/README.md)
  for its request and response contract.
- `plugin/imcp/` contains the `imcp_list_tools` and `imcp_call` Stavrobot
  tools. **The contents of `plugin/imcp/` must be the standalone plugin root**:
  `manifest.json` must be at the root of the published or copied bundle. The
  monorepo root is not itself an installable plugin URL. See
  [`plugin/imcp/README.md`](plugin/imcp/README.md).
- The bridge token, host allowlist, and installed plugin configuration are
  separate operator-managed configuration. Keep credentials out of this
  repository, agent chat, command output, and logs.

## Python 3.14 setup and local verification

From the repository root, create the explicit Python 3.14 environment and
install the pinned dependencies:

```sh
python3.14 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

Run the local suite with:

```sh
./.venv/bin/python -m pytest -v
```

The suite includes [`tests/test_bridge_sdk.py`](tests/test_bridge_sdk.py),
which uses the official MCP Python SDK against a local newline-delimited
fixture. It verifies initialization and readiness cancellation, setup and
in-flight cancellation, reconnect after disconnect without replaying a call,
and idle/in-flight cleanup. These are local fixture checks only; they do not
start the installed iMCP app, invoke a live iMCP tool, or verify network access
from Stavrobot `plugin-runner`.

## Short operator path

For startup after login and automatic bridge crash recovery, prepare the token
and allowlist, then run:

```sh
./.venv/bin/python scripts/install_login_services.py
```

This installs a bridge LaunchAgent and an iMCP app login LaunchAgent. The
login-service prerequisite is an already-installed app at
`/Applications/iMCP.app`; this repository only opens it and does not install
or copy the app. The bridge restarts after exits with a 30-second throttle.
The tmux helper (`scripts/start-stavrobot-imcp-bridge`) and the bridge
LaunchAgent are mutually exclusive supervisors: running both on
`127.0.0.1:8766` causes port-conflict retries and log growth. Stop one
supervisor before starting the other. See the login-startup section in
`DEPLOY.md` for configuration checks and uninstall instructions. After a
reboot, the Mac must be unlocked and the user logged in; this is not a
pre-login daemon.

For an approved deployment, use this sequence rather than treating local tests
as deployment evidence:

1. Read [`DEPLOY.md`](DEPLOY.md), including its safety gates. Select only the
   required iMCP services and permissions, keep the bridge on
   `127.0.0.1:8766`, create the protected token and explicit tool allowlist in
   a trusted host terminal, start the host bridge as directed, and manually
   approve the first iMCP client connection. Start with an approved read-only
   operation.
2. Follow [`plugin/imcp/README.md`](plugin/imcp/README.md), then publish or
   copy **the contents of `plugin/imcp/` as the standalone plugin root**.
   Configure its `bridge_url` and `bridge_token` through Stavrobot's trusted
   settings path. The plugin URL uses `host.docker.internal:8766`;
   `127.0.0.1` inside `plugin-runner` is the container, not the host.
3. Follow [DEPLOY.md's plugin-runner reachability checks](DEPLOY.md#6-required-reachability-verification-from-plugin-runner).
   The authenticated check must run from the actual `plugin-runner` as the
   dedicated plugin user. Do not widen the host bind to `0.0.0.0` to work
   around a failed container check, and keep iMCP excluded from every
   `telegram-group-*` agent.

The operator sequence above is not evidence that installation or live
verification has occurred. The deployment runbook remains the source of truth
for manual approvals, secret handling, rollback, and live iMCP/Stavrobot
verification.

## Host bridge command (operator instruction)

The host bridge is authenticated and host-only. Once the manual prerequisites
in [`DEPLOY.md`](DEPLOY.md) are complete, run the repository helper from its
root:

```sh
scripts/start-stavrobot-imcp-bridge
```

The helper requires the protected token at `~/.config/imcp-bridge.token` and a
non-empty, owner-only allowlist at `~/.config/imcp-bridge-tools.json`. It passes
both paths with `--token-file` and `--allowlist-file`, and starts the bridge on
`127.0.0.1:8766/bridge` with the required `--call-timeout 10` setting. It accepts
JSON `POST` operations for `health`, `list_tools`, and `call_tool`. This command
is documentation only;
it was not run as part of authoring this README, and repository setup and tests
do not start a persistent bridge.

## Secondary feature: metadata probe

The original read-only metadata probe remains available as a secondary
feature, separate from the bridge/plugin deployment. After enabling only the
approved iMCP services and completing any macOS permission prompts, run it in
the logged-in macOS session:

```sh
./.venv/bin/python scripts/probe_imcp.py --timeout 300
```

When iMCP shows its Connection Request window, approve the client manually.
The probe performs the MCP handshake and requests only `tools/list`; it never
invokes an MCP tool. It uses the shared Bonjour-discovered loopback transport
and writes only tool names, descriptions, and input schemas to
`docs/imcp-tools.md`.

## Remove the local environment

To undo the local virtual-environment setup, run:

```sh
rm -rf .venv
```

This removes only the repository's ignored virtual environment. Re-run the
setup commands above to recreate it.
