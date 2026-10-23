"""Where runtime files (voice rules, model config, calibration targets) live.

In the repo they sit beside the packages. In the container image the packages are installed
non-editable into a venv, so a path built from `__file__` leads nowhere; the image copies the files
under MATCHPROOF_ROOT instead.
"""

import os
from pathlib import Path

ROOT_ENV = "MATCHPROOF_ROOT"


def runtime_root() -> Path:
    """MATCHPROOF_ROOT if set, else the repo root (local development and CI)."""
    configured = os.environ.get(ROOT_ENV)
    return Path(configured) if configured else Path(__file__).resolve().parents[4]
