"""The MCP wall.

A minimal Model Context Protocol server over stdio (JSON-RPC 2.0, one
message per line), written without dependencies. It is the only door between
the research agents and the evaluator. Through it an agent can read the
formula reference, submit a hypothesis card and read the verdict, and list
the graveyard. It cannot read data, metrics on the validation window beyond
the Thresholdout answer, or anything about the holdout.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

from . import __version__

PROTOCOL_DEFAULT = "2025-06-18"

TOOLS = [
    {"name": "dsl_reference",
     "description": "Fields you can use (with when each value becomes known), operators, and the hypothesis card format.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "submit",
     "description": ("Submit one hypothesis card. Returns the verdict only: survived, or the number and name of "
                     "the check that killed it and why. Every call is written to the trial log and counts "
                     "against the campaign's number of tries."),
     "inputSchema": {"type": "object", "required": ["card"], "properties": {
         "card": {"type": "object", "description": "id, formula, hold, reason{counterparty, edge_type, decay}, expect[{field|formula, sign}], family"},
         "campaign": {"type": "string"}}}},
    {"name": "graveyard",
     "description": "Every idea already tried in this campaign and the check that killed it. Read it before proposing.",
     "inputSchema": {"type": "object", "properties": {"campaign": {"type": "string"}}}},
    {"name": "status",
     "description": "Number of tries, validation queries and survivors in a campaign.",
     "inputSchema": {"type": "object", "properties": {"campaign": {"type": "string"}}}},
]

# checks whose numbers come from windows the agents must not tune on
_REDACT = {11: "post-cutoff window: {status}", 12: "holdout: sealed"}


class Server:
    def __init__(self, root: str | None = None):
        self.root = Path(root or os.environ.get("ALPHADESK_DESK", "desk"))
        self._desk = None

    # ------------------------------------------------------------- desk
    def desk(self):
        if self._desk is None:
            from .workspace import open_desk
            self._desk = open_desk(self.root)
        return self._desk

    def campaign(self, args):
        return args.get("campaign") or self.desk().campaign

    # ------------------------------------------------------------- tools
    def t_dsl_reference(self, args):
        from . import ops
        p = self.desk().panel
        fields = {n: {"known_at": f.known_at, "description": f.description, "kind": f.kind}
                  for n, f in p.fields.items()}
        opers = {n: {"series": a, "numbers": k} for n, (_, a, k) in ops.OPERATORS.items()}
        return {"fields": fields, "operators": opers,
                "rules": ["a value in row t may only use rows <= t; delay(x, k) needs k >= 0",
                          "the evaluator never shows you validation or holdout data",
                          "write the card's reason before you look at any result"],
                "card": {"id": "short_snake_case", "family": "group of variants of one idea",
                         "formula": "cs_rank(-delta(log(close), 5))", "hold": 5,
                         "reason": {"counterparty": "who is on the other side and why they lose",
                                    "edge_type": "risk_premium | structural | behavioral | informational | analytical",
                                    "decay": "what should make it fade"},
                         "expect": [{"field": "close", "sign": "-"}]}}

    def t_submit(self, args):
        card = args.get("card")
        if isinstance(card, str):
            card = json.loads(card)
        v = self.desk().desk.submit(card, campaign=self.campaign(args))
        checks = []
        for c in v["checks"]:
            if c["n"] in _REDACT:
                checks.append({"n": c["n"], "status": c["status"],
                               "detail": _REDACT[c["n"]].format(status=c["status"])})
            else:
                checks.append({"n": c["n"], "status": c["status"], "detail": c["detail"]})
        return {"survived": v["survived"], "died_at": v["died_at"],
                "check": checks[-1] if checks else None, "checks": checks,
                "note": "numbers above are from the development window only"}

    def t_graveyard(self, args):
        from .workspace import graveyard
        return graveyard(self.desk(), self.campaign(args))

    def t_status(self, args):
        d = self.desk()
        c = self.campaign(args)
        n = d.desk.log.count(c)
        return {"campaign": c, **n, "data": d.panel.meta.get("source")}

    # ------------------------------------------------------------- protocol
    def handle(self, msg):
        method, mid = msg.get("method"), msg.get("id")
        if method == "initialize":
            pv = (msg.get("params") or {}).get("protocolVersion", PROTOCOL_DEFAULT)
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": pv, "capabilities": {"tools": {}},
                "serverInfo": {"name": "alphadesk", "version": __version__},
                "instructions": "The evaluator behind the wall. Submit cards, read verdicts. No data crosses."}}
        if method == "notifications/initialized" or mid is None:
            return None
        if method == "ping":
            return {"jsonrpc": "2.0", "id": mid, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = msg.get("params") or {}
            name, args = params.get("name"), params.get("arguments") or {}
            fn = getattr(self, f"t_{name}", None)
            if fn is None:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
            try:
                out = fn(args)
                return {"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps(out, indent=1, default=float)}]}}
            except Exception as e:  # the agent gets the error, not a stack of our internals
                return {"jsonrpc": "2.0", "id": mid, "result": {
                    "isError": True, "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}]}}
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}

    def serve(self, stdin=None, stdout=None):
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                out = self.handle(msg)
            except Exception:
                traceback.print_exc(file=sys.stderr)
                out = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": "internal error"}}
            if out is not None:
                stdout.write(json.dumps(out) + "\n")
                stdout.flush()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    Server().serve()


if __name__ == "__main__":
    main()
