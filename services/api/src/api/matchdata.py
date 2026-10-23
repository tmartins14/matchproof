"""The match-data MCP server in the API: a public read-only mount and an internal read-write server.

The public server is served at /mcp over streamable HTTP, rate-limited per client address, and has
no write tool (ADR 0008). The internal server has `put_claims` and exists only as a Python object for
the agent workflow; nothing here routes to it.
"""

import time
from collections import deque
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp_match import InMemoryMatchStore, MatchStore, archive_from_env, build_server
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

MCP_RPM_PER_CLIENT = 60  # requests per minute per client address on the public endpoint
RATE_WINDOW_S = 60.0
MAX_TRACKED_CLIENTS = (
    10_000  # addresses remembered; beyond this the idle ones are dropped
)

store = InMemoryMatchStore(archive=archive_from_env())  # MATCH_ARCHIVE=file|blob


def get_internal_server(match_store: MatchStore) -> FastMCP:
    """The server with `put_claims`, for the agent workflow to use in process. Never mount it."""
    return build_server(match_store, writable=True)


class RateLimiter:
    """At most `limit` requests per `window_s` per key, counted over a sliding window."""

    def __init__(
        self,
        limit: int = MCP_RPM_PER_CLIENT,
        window_s: float = RATE_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._seen: dict[str, deque[float]] = {}

    def retry_after(self, key: str) -> int | None:
        """Count a request. None if it is allowed; otherwise whole seconds until one would be."""
        now = self._clock()
        hits = self._seen.setdefault(key, deque())
        while hits and hits[0] <= now - self._window_s:
            hits.popleft()
        if len(hits) >= self._limit:
            return max(1, int(hits[0] + self._window_s - now) + 1)
        hits.append(now)
        if len(self._seen) > MAX_TRACKED_CLIENTS:
            self._seen = {
                k: v
                for k, v in self._seen.items()
                if v and v[-1] > now - self._window_s
            }
        return None


class PublicMcp:
    """ASGI endpoint for /mcp. The API's lifespan starts the server and sets `server`."""

    def __init__(self, limiter: RateLimiter | None = None) -> None:
        self.limiter = limiter or RateLimiter()
        self.server: FastMCP | None = None

    def start(self, match_store: MatchStore) -> FastMCP:
        """Build a fresh read-only server; the caller runs its session manager."""
        self.server = build_server(match_store, writable=False)
        self.server.streamable_http_app()  # creates the session manager
        return self.server

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["method"] in ("GET", "DELETE"):
            # Stateless server: no stream to open and no session to end. Answering at once keeps
            # clients such as the MCP Inspector from stalling on a held-open GET.
            not_allowed = JSONResponse(
                {"error": "method not allowed; POST only"},
                status_code=405,
                headers={"Allow": "POST"},
            )
            await not_allowed(scope, receive, send)
            return
        client = scope.get("client")
        key = client[0] if client else "unknown"
        wait = self.limiter.retry_after(key)
        reply: Any = None
        if wait is not None:
            reply = JSONResponse(
                {"error": "rate limit: 60 requests per minute"},
                status_code=429,
                headers={"Retry-After": str(wait)},
            )
        elif self.server is None:
            reply = JSONResponse({"error": "mcp server not running"}, status_code=503)
        if reply is not None:
            await reply(scope, receive, send)
            return
        assert self.server is not None
        await self.server.session_manager.handle_request(scope, receive, send)
