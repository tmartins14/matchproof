"""The match-data MCP server and the store behind it."""

from .persist import (
    ArchiveMissing,
    BlobArchive,
    FileArchive,
    MatchArchive,
    archive_from_env,
)
from .server import HTTP_PATH, build_server
from .store import MAX_MATCHES, InMemoryMatchStore, MatchStore, UnknownMatch

__all__ = [
    "HTTP_PATH",
    "MAX_MATCHES",
    "ArchiveMissing",
    "BlobArchive",
    "FileArchive",
    "InMemoryMatchStore",
    "MatchArchive",
    "MatchStore",
    "UnknownMatch",
    "archive_from_env",
    "build_server",
]
