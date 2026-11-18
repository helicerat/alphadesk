"""A desk folder: config, data choice, trial log, campaign.

``desk/config.json`` decides which data the evaluator loads. Agents never
read this folder: a plugin hook blocks it, and the MCP wall is their only
way in.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .evaluator import Desk
from .triallog import TrialLog

DEFAULT = {"data": "synthetic", "campaign": "c001", "seed": 7,
           "synthetic": {"n_assets": 500, "n_days": 2520},
           "binance": {"since": "2023-01", "max_symbols": None},
           "alpaca": {"symbols_file": "universe.txt", "start": "2016-01-01"},
           "model_cutoff": "2026-06-01"}

CRYPTO_FACTORS = {
    "Mom30": "cs_rank(delay(log(close), 1) - delay(log(close), 30))",
    "Rev1": "cs_rank(-ret)",
    "Liquidity": "cs_rank(size)",
    "Carry": "cs_rank(-ts_mean(funding, 7))",
}


@dataclass
class Workspace:
    root: Path
    config: dict
    panel: object
    desk: Desk

    @property
    def campaign(self) -> str:
        return self.config.get("campaign", "c001")


def init(root: str | Path, data: str = "synthetic", **over) -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(json.dumps(DEFAULT))
    cfg["data"] = data
    cfg.update(over)
    (root / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return root / "config.json"


def load_config(root: Path) -> dict:
    p = Path(root) / "config.json"
    if not p.exists():
        init(root)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    return {**DEFAULT, **cfg}


def open_desk(root: str | Path) -> Workspace:
    root = Path(root)
    cfg = load_config(root)
    src = cfg["data"]
    external = None
    if src == "synthetic":
        from . import synth
        s = cfg.get("synthetic", {})
        panel = synth.make_market(n_assets=s.get("n_assets", 500), n_days=s.get("n_days", 2520),
                                  seed=cfg.get("seed", 7))
        library = synth.KNOWN_FACTORS
    elif src == "binance":
        from .data import binance
        b = cfg.get("binance", {})
        panel = binance.load(since=b.get("since", "2023-01"), max_symbols=b.get("max_symbols"))
        panel.meta["cutoff"] = cfg.get("model_cutoff", panel.meta["cutoff"])
        library = CRYPTO_FACTORS
    elif src == "alpaca":
        from .data import alpaca, french
        a = cfg.get("alpaca", {})
        syms = [s.strip() for s in (root / a.get("symbols_file", "universe.txt")).read_text().split() if s.strip()]
        panel = alpaca.load(syms, start=a.get("start", "2016-01-01"), cutoff=cfg.get("model_cutoff", "2026-06-01"))
        library = {"Mom12m": "cs_rank(delay(log(close), 21) - delay(log(close), 252))",
                   "STreversal": "cs_rank(-pct_change(close, 21))"}
        external = [french.factors().drop(columns=["RF"])]   # daily Fama-French 5 + momentum
        try:
            from .data import osap
            external.append(osap.ls_returns())                # monthly, 212 published predictors
        except Exception as e:  # offline: the daily factors still run
            print(f"Open Source Asset Pricing not loaded ({e}); novelty uses Fama-French only")
    else:
        raise ValueError(f"unknown data source {src}")
    desk = Desk(panel, TrialLog(root / "trials"), library=library, external=external, seed=cfg.get("seed", 7))
    return Workspace(root=root, config=cfg, panel=panel, desk=desk)


def graveyard(ws: Workspace, campaign: str) -> list:
    from .evaluator import CHECK_NAMES
    out = []
    for e in ws.desk.log.entries(campaign, kind="verdict"):
        d = e.get("died_at")
        out.append({"card": e.get("card"), "family": e.get("family"), "formula": e.get("formula"),
                    "died_at": d, "check": "survived" if e.get("survived") else CHECK_NAMES.get(d, "?"),
                    "why": e.get("summary")})
    return out
