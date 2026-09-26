"""Shared official MCP stdio client for the bundled iMCP server."""

from .transport import (
    DEFAULT_SERVER_PATH,
    DEFAULT_SHUTDOWN_TIMEOUT,
    DEFAULT_STARTUP_TIMEOUT,
    MIN_SHUTDOWN_TIMEOUT,
    TransportConfigurationError,
    open_imcp_session,
)

__all__ = [
    "DEFAULT_SERVER_PATH",
    "DEFAULT_SHUTDOWN_TIMEOUT",
    "DEFAULT_STARTUP_TIMEOUT",
    "MIN_SHUTDOWN_TIMEOUT",
    "TransportConfigurationError",
    "open_imcp_session",
]
