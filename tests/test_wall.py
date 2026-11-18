import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

WALL = Path(__file__).parents[1] / "hooks" / "wall.py"


def run(tool, **inp):
    env = {**os.environ, "ALPHADESK_HOME": "C:/Users/x/.alphadesk"}
    out = subprocess.run([sys.executable, "-W", "error", str(WALL)], input=json.dumps({"tool_name": tool, "tool_input": inp, "cwd": str(Path(__file__).parent / "_wall_tmp")}),
                         capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] if out.stdout.strip() else "allow"


@pytest.mark.parametrize("tool,inp", [
    ("Bash", {"command": "alphadesk holdout c004"}),
    ("PowerShell", {"command": "python -m alphadesk holdout c004 --i-am-human-in-ci"}),
    ("Read", {"file_path": r"C:\Users\x\.alphadesk\panels\binance.parquet"}),
    ("Bash", {"command": "python -c \"import pandas as pd; pd.read_parquet('C:/Users/x/.alphadesk/panels/a.parquet')\""}),
    ("Grep", {"pattern": "close", "path": "desk/trials/trials.jsonl"}),
    ("Read", {"file_path": r"desk\trials\returns\12.npy"}),
])
def test_wall_blocks(tool, inp):
    assert run(tool, **inp) == "deny"


@pytest.mark.parametrize("tool,inp", [
    ("Bash", {"command": "alphadesk status"}),
    ("Read", {"file_path": "papers/accruals.pdf"}),
    ("Edit", {"file_path": "notes/hypotheses.md"}),
])
def test_wall_allows(tool, inp):
    assert run(tool, **inp) == "allow"


def teardown_module(_):
    import shutil
    shutil.rmtree(Path(__file__).parent / "_wall_tmp", ignore_errors=True)
