"""Fail if generated models or types are out of date with schemas/."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "packages" / "contracts" / "src" / "contracts" / "models.py"
TYPES = ROOT / "apps" / "web" / "src" / "contracts" / "types.ts"


def run(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True)


def test_models_are_fresh(tmp_path: Path) -> None:
    out = tmp_path / "models.py"
    run([sys.executable, "scripts/gen_models.py", str(out)])
    assert out.read_text() == MODELS.read_text(), "run `make gen`: models.py is stale"


def test_types_are_fresh(tmp_path: Path) -> None:
    out = tmp_path / "types.ts"
    run(["node", "scripts/gen_types.mjs", str(out)])
    assert out.read_text() == TYPES.read_text(), "run `make gen`: types.ts is stale"
