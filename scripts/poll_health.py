"""Poll /livez and /health every 2 s and log timestamped latencies; print a summary on Ctrl-C.

API_URL=https://... python3 scripts/poll_health.py | tee poll.log
"""

import os
import statistics
import time
import urllib.error
import urllib.request

PATHS = ("/livez", "/health")
PERIOD_S = 2.0
TIMEOUT_S = 30.0


def probe(base: str, path: str) -> tuple[float, str]:
    start = time.monotonic()
    try:
        with urllib.request.urlopen(base + path, timeout=TIMEOUT_S) as response:
            status = str(response.status)
    except (urllib.error.URLError, TimeoutError) as exc:
        status = type(exc).__name__
    return time.monotonic() - start, status


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def main() -> None:
    base = os.environ["API_URL"].rstrip("/")
    seen: dict[str, list[float]] = {path: [] for path in PATHS}
    failures: dict[str, int] = {path: 0 for path in PATHS}
    try:
        while True:
            tick = time.monotonic()
            for path in PATHS:
                seconds, status = probe(base, path)
                seen[path].append(seconds)
                failures[path] += status != "200"
                print(
                    f"{time.time():.3f} {path} {status} {seconds:.3f}",
                    flush=True,
                )
            time.sleep(max(0.0, PERIOD_S - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        for path, values in seen.items():
            if values:
                print(
                    f"{path}: n={len(values)} p50={statistics.median(values):.3f}s "
                    f"p95={percentile(values, 0.95):.3f}s max={max(values):.3f}s "
                    f"non200={failures[path]}"
                )


if __name__ == "__main__":
    main()
