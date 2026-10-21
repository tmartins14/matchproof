import sys
from pathlib import Path

# --import-mode=importlib leaves the tests directory off sys.path; the helpers live beside the tests.
sys.path.insert(0, str(Path(__file__).parent))
