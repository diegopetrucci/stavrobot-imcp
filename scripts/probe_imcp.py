#!/usr/bin/env python3
"""Capture iMCP's read-only MCP tool metadata.

This probe initializes an MCP client over iMCP's shared Bonjour/loopback
transport and requests only ``tools/list``. It never calls an MCP tool, and
writes only each tool's name, description, and input schema to the output
document.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

# Keep direct execution (``python scripts/probe_imcp.py``) working without
# installing this repository as a package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mcp import types

from stavrobot_imcp import open_imcp_session


APP_PATH = Path("/Applications/iMCP.app")
APP_VERSION = "1.4.1"
CLIENT_NAME = "imcp-tools-probe"
CLIENT_VERSION = "1.0.0"
DEFAULT_TIMEOUT = 300.0


def _repo_root() -> Path:
    return REPO_ROOT


def _is_imcp_running() -> bool:
    result = subprocess.run(
        ["pgrep", "-x", "iMCP"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _launch_app_if_needed(app_path: Path) -> None:
    if _is_imcp_running():
        return
    if not app_path.is_dir():
        raise RuntimeError(f"iMCP app not found: {app_path}")

    try:
        subprocess.run(["open", str(app_path)], check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"could not open iMCP app: {app_path}") from exc

    # Give the menu-bar app a moment to register its local server before the
    # Bonjour discovery starts. Permission and approval prompts remain manual
    # UI actions; this probe does not interact with them.
    time.sleep(2)


def _metadata_for_tool(tool: types.Tool) -> dict[str, Any]:
    """Keep only the fields explicitly allowed in the capture."""

    return {
        "name": tool.name,
        "description": tool.description,
        # MCP SDK model fields use snake_case attributes while retaining the
        # protocol's inputSchema alias on the wire.
        "inputSchema": tool.input_schema,
    }


async def _list_all_tools() -> list[dict[str, Any]]:
    async with open_imcp_session(
        client_info=types.Implementation(
            name=CLIENT_NAME,
            version=CLIENT_VERSION,
        ),
    ) as session:
        await session.initialize()

        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()

        while True:
            params = (
                types.PaginatedRequestParams(cursor=cursor)
                if cursor is not None
                else None
            )
            page = await session.list_tools(params=params)
            tools.extend(_metadata_for_tool(tool) for tool in page.tools)

            # SDK model fields use snake_case attributes for protocol aliases.
            cursor = page.next_cursor
            if cursor is None:
                return tools
            if cursor in seen_cursors:
                raise RuntimeError("iMCP returned a repeated tools/list cursor")
            seen_cursors.add(cursor)


def _render_document(
    tools: list[dict[str, Any]],
    *,
    app_version: str,
    capture_date: str,
) -> str:
    payload = json.dumps(tools, indent=2, ensure_ascii=False, sort_keys=False)
    return f"""# iMCP tools

Captured from iMCP **{app_version}** on **{capture_date}** using a read-only MCP handshake and `tools/list`.

The generic full iMCP {app_version} tool surface when all services are enabled is documented below; this is not a record of the operator's Mac configuration.

Only tool names, descriptions, and input schemas are recorded below. No tool was invoked and no tool result or personal data was captured.

```json
{payload}
```
"""


def _parse_args() -> argparse.Namespace:
    root = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app",
        type=Path,
        default=APP_PATH,
        help="path to iMCP.app, launched if iMCP is not running",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "docs/imcp-tools.md",
        help="metadata document to write",
    )
    parser.add_argument(
        "--app-version",
        default=APP_VERSION,
        help="installed iMCP version to record",
    )
    parser.add_argument(
        "--capture-date",
        default=date.today().isoformat(),
        help="ISO capture date to record (defaults to today)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="seconds to wait for handshake and tools/list",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    _launch_app_if_needed(args.app)

    try:
        tools = await asyncio.wait_for(
            _list_all_tools(),
            timeout=args.timeout,
        )
    except asyncio.TimeoutError as exc:
        raise RuntimeError(
            "timed out during the read-only MCP handshake/tools/list; "
            "check iMCP's manual client approval prompt"
        ) from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        _render_document(
            tools,
            app_version=args.app_version,
            capture_date=args.capture_date,
        ),
        encoding="utf-8",
    )
    print(f"Wrote read-only iMCP tool metadata to {args.output}", file=sys.stderr)


def _friendly_error(exc: Exception) -> str:
    detail = " ".join(str(exc).split())
    return detail or type(exc).__name__


def main() -> int:
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except Exception as exc:
        # Exception deliberately excludes KeyboardInterrupt and SystemExit.
        print(f"probe failed: {_friendly_error(exc)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
