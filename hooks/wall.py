"""PreToolUse hook: keeps Claude out of the data and away from the holdout.

Claude Code sends the tool call as JSON on stdin. If the call would read the
data folder, the trial log's raw returns, or open the holdout, the hook
denies it and records the attempt. Everything else passes untouched.
"""

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

def _norm(s: str) -> str:
    return s.replace("\\", "/").lower()


HOME = _norm(os.environ.get("ALPHADESK_HOME", str(Path.home() / ".alphadesk"))).rstrip("/")
BLOCKED = [
    (re.compile(r"alphadesk(\.exe)?\s+holdout|-m\s+alphadesk\s+holdout|cmd_holdout"),
     "The holdout opens only from your own terminal. Ask the user to run `alphadesk holdout <campaign>`."),
    (re.compile(re.escape(HOME) + r"|/\.alphadesk(/|$|\s|['\"])"),
     "The data folder is on the evaluator's side of the wall. Use the alphadesk MCP tools instead."),
    (re.compile(r"desk/+trials/+(returns|trials\.jsonl)"),
     "The trial log is the evaluator's. Use the `status` and `graveyard` MCP tools."),
]


def text_of(tool_input: dict) -> str:
    keys = ("command", "file_path", "path", "pattern", "notebook_path", "url")
    return " ".join(str(tool_input.get(k, "")) for k in keys)


def main():
    try:
        call = json.load(sys.stdin)
    except Exception:
        return 0
    txt = _norm(text_of(call.get("tool_input") or {}))
    for rx, why in BLOCKED:
        if rx.search(txt):
            try:
                log = Path(call.get("cwd") or ".") / "desk" / "blocked.jsonl"
                log.parent.mkdir(parents=True, exist_ok=True)
                with open(log, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                        "tool": call.get("tool_name"), "input": txt[:300], "why": why}) + "\n")
            except Exception:
                pass
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "permissionDecision": "deny",
                                                     "permissionDecisionReason": why}}))
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
