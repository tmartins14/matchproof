import sys
from pathlib import Path

# --import-mode=importlib leaves the tests directory off sys.path; the helpers live beside the tests,
# and the generated-match cache helpers live with the intel tests.
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "intel" / "tests"))
