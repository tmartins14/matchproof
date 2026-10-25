import asyncio
import json
import logging

import pytest
from api import vitals
from api.main import app
from fastapi.testclient import TestClient


def test_livez() -> None:
    response = TestClient(app).get("/livez")
    assert response.status_code == 200 and response.json() == {"ok": True}


def test_sample_logs_one_line_per_interval(caplog: pytest.LogCaptureFixture) -> None:
    async def run() -> None:
        task = asyncio.create_task(vitals.sample(lambda: 2, lambda: 3, interval_s=0.01))
        await asyncio.sleep(0.05)
        task.cancel()

    with caplog.at_level(logging.WARNING, logger="matchproof.vitals"):
        asyncio.run(run())
    lines = [json.loads(r.getMessage()) for r in caplog.records]
    assert lines and all(line["event"] == "vitals" for line in lines)
    assert lines[0]["streams"] == 2 and lines[0]["ledger_pending"] == 3
    assert lines[0]["loop_lag_ms"] >= 0 and lines[0]["threads"] >= 1


def test_startup_limits_name_the_process() -> None:
    limits = vitals.startup_limits()
    assert isinstance(limits["pid"], int) and str(limits["python"]).startswith("3.12")
