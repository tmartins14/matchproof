"""Process vitals for diagnosing container restarts (prompt 13.1): startup limits, a line every
few seconds, and a record of SIGTERM."""

import asyncio
import faulthandler
import json
import logging
import os
import platform
import signal
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import FrameType

log = logging.getLogger("matchproof.vitals")

INTERVAL_S = 5.0
CGROUP = Path("/sys/fs/cgroup")


def read_text_file(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def rss_mib() -> float | None:
    text = read_text_file(Path("/proc/self/status"))
    if text is None:
        return None
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return None


def cgroup_mib(name: str) -> float | None:
    raw = read_text_file(CGROUP / name)
    return int(raw) / 2**20 if raw and raw.isdigit() else None


def startup_limits() -> dict[str, object]:
    return {
        "memory.max": read_text_file(CGROUP / "memory.max"),
        "cpu.max": read_text_file(CGROUP / "cpu.max"),
        "pid": os.getpid(),
        "python": platform.python_version(),
    }


def snapshot(
    streams: Callable[[], int], pending: Callable[[], int]
) -> dict[str, object]:
    return {
        "rss_mib": rss_mib(),
        "cg_current_mib": cgroup_mib("memory.current"),
        "cg_peak_mib": cgroup_mib("memory.peak"),
        "threads": threading.active_count(),
        "streams": streams(),
        "ledger_pending": pending(),
    }


def emit(event: str, fields: dict[str, object]) -> None:
    log.warning("%s", json.dumps({"event": event, **fields}, default=str))


async def sample(
    streams: Callable[[], int],
    pending: Callable[[], int],
    interval_s: float = INTERVAL_S,
) -> None:
    """Log one line per interval until cancelled: memory, CPU %, event-loop lag, load."""
    emit(
        "startup", startup_limits()
    )  # once, from the sampler: a line logged from install() never reached the console log
    last_cpu = time.process_time()
    last_wall = time.monotonic()
    while True:
        before = time.monotonic()
        await asyncio.sleep(interval_s)
        now = time.monotonic()
        lag_ms = max(0.0, (now - before - interval_s) * 1000)
        cpu = time.process_time()
        cpu_pct = 100 * (cpu - last_cpu) / max(now - last_wall, 1e-9)
        last_cpu, last_wall = cpu, now
        emit(
            "vitals",
            {
                "loop_lag_ms": round(lag_ms, 1),
                "cpu_pct": round(cpu_pct, 1),
                **snapshot(streams, pending),
            },
        )


def install(streams: Callable[[], int], pending: Callable[[], int]) -> None:
    """faulthandler for hard crashes and a SIGTERM record."""
    faulthandler.enable()
    if threading.current_thread() is not threading.main_thread():
        return  # signal handlers are main-thread only (test clients run the lifespan elsewhere)
    previous = signal.getsignal(signal.SIGTERM)

    def on_term(signum: int, frame: FrameType | None) -> None:
        emit("sigterm", snapshot(streams, pending))
        if callable(previous):
            previous(signum, frame)  # uvicorn's own handler: a normal shutdown
        else:
            raise SystemExit(0)

    signal.signal(signal.SIGTERM, on_term)
