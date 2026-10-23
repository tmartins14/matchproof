import sys
from pathlib import Path

# --import-mode=importlib leaves the tests directory off sys.path; the fakes live beside the tests.
sys.path.insert(0, str(Path(__file__).parent))


import pytest
from api.matchdata import store
from mcp_match import FileArchive


@pytest.fixture(autouse=True)
def archive_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FileArchive:
    """Matches that reach full time in a test are archived under tmp, never under data/."""
    archive = FileArchive(tmp_path / "archive")
    monkeypatch.setattr(store, "archive", archive)
    return archive
