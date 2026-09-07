# iMCP metadata probe

This repository contains a read-only probe for the locally installed iMCP app.

## Create the Python 3.14 environment

From the repository root:

```sh
python3.14 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

The pinned requirements include the official MCP Python SDK and Bonjour
discovery support.

## Run tests

```sh
./.venv/bin/python -m pytest -v
```

The test suite uses only fake discovery/session objects. It does not start a
persistent bridge, connect to live iMCP, or invoke an MCP tool.

## Host bridge

`bridge/server.py` provides the authenticated, host-only HTTP bridge used by
later plugin setup. It defaults to `127.0.0.1:8766/bridge`; startup requires a
trusted bearer token file:

```sh
./.venv/bin/python bridge/server.py --token-file ~/.config/imcp-bridge.token
```

The bridge accepts JSON `POST` requests with `operation` set to `health`,
`list_tools`, or `call_tool` (the latter also supplies `name` and an object-valued
`arguments`). See [`bridge/README.md`](bridge/README.md) for the response
contract, allowlist file shape, bounds, and no-replay behavior. This command is
only documentation; no service is started by repository setup or tests.

## Manually approved live capture

First enable the desired iMCP services and complete macOS permission prompts.
Run the following command in the logged-in macOS user session:

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
