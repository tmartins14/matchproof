import sys
from pathlib import Path

# --import-mode=importlib leaves the tests directory off sys.path; the helpers live beside the tests,
# and the finished-match helpers live with the MCP and intel tests.
here = Path(__file__).parent
sys.path.insert(0, str(here))
sys.path.insert(0, str(here.parents[1] / "mcp_match" / "tests"))
sys.path.insert(0, str(here.parents[1] / "intel" / "tests"))
