"""The trial log. Every variant, parameter and validation query is written
here from the first run, so the number of tries behind a result is honest."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import numpy as np


class TrialLog:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "returns").mkdir(exist_ok=True)
        self.path = self.root / "trials.jsonl"

    def _all(self) -> list:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def entries(self, campaign: str | None = None, kind: str | None = None) -> list:
        out = self._all()
        if campaign is not None:
            out = [e for e in out if e.get("campaign") == campaign]
        if kind is not None:
            out = [e for e in out if e.get("kind") == kind]
        return out

    def next_id(self) -> int:
        return len(self._all()) + 1

    def write(self, entry: dict, returns: np.ndarray | None = None) -> dict:
        entry = dict(entry)
        entry.setdefault("id", self.next_id())
        entry.setdefault("time", dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        if returns is not None:
            p = self.root / "returns" / f"{entry['id']}.npy"
            np.save(p, returns.astype(np.float32))
            entry["returns_file"] = p.name
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=float) + "\n")
        return entry

    def returns_matrix(self, campaign: str | None = None, family: str | None = None) -> np.ndarray | None:
        cols = []
        for e in self.entries(campaign, kind="trial"):
            if family is not None and e.get("family") != family:
                continue
            f = e.get("returns_file")
            if f:
                cols.append(np.load(self.root / "returns" / f).astype(float))
        if not cols:
            return None
        L = min(len(c) for c in cols)
        return np.column_stack([c[:L] for c in cols])

    def count(self, campaign: str | None = None) -> dict:
        es = self.entries(campaign)
        return {"trials": sum(e.get("kind") == "trial" for e in es),
                "validation_queries": sum(e.get("kind") == "validation" for e in es),
                "holdout_opened": sum(e.get("kind") == "holdout" for e in es)}
