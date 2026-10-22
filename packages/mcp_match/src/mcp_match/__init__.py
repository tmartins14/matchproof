"""The match-data MCP server and the store behind it."""

from .server import HTTP_PATH, build_server
from .store import MAX_MATCHES, InMemoryMatchStore, MatchStore, UnknownMatch

__all__ = [
    "HTTP_PATH",
    "MAX_MATCHES",
    "InMemoryMatchStore",
    "MatchStore",
    "UnknownMatch",
    "build_server",
]
