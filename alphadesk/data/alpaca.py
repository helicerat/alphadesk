"""US stock daily bars from Alpaca's market data API (free Basic plan).

Free plan: history since 2016, consolidated (SIP) bars except the latest
15 minutes, 200 requests a minute. Keys come from the environment
(``APCA_API_KEY_ID``, ``APCA_API_SECRET_KEY``) and are never written to disk.

Prices are split and dividend adjusted (``adjustment=all``) so returns are
total returns. Delisted symbols stay in Alpaca's database, but there is no
historical list of what was listed when, so the universe here comes from a
list you pass in. Every report built on it carries a survivorship warning.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from . import cache
from ..panel import Field, Panel

URL = "https://data.alpaca.markets/v2/stocks/bars"


def _headers() -> dict:
    k, s = os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY")
    if not (k and s):
        raise RuntimeError("Alpaca needs a free key: set APCA_API_KEY_ID and APCA_API_SECRET_KEY")
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s, "Accept": "application/json"}


def bars(symbols: list[str], start: str = "2016-01-01", end: str | None = None,
         feed: str = "sip", chunk: int = 100, pause: float = 0.31) -> pd.DataFrame:
    """Long table: symbol, date, close, volume, vwap, trades."""
    rows = []
    for i in range(0, len(symbols), chunk):
        part = symbols[i : i + chunk]
        token = None
        while True:
            q = {"symbols": ",".join(part), "timeframe": "1Day", "start": start, "limit": 10000,
                 "adjustment": "all", "feed": feed}
            if end:
                q["end"] = end
            if token:
                q["page_token"] = token
            req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(q), headers=_headers())
            with urllib.request.urlopen(req, timeout=60) as r:
                j = json.loads(r.read())
            for sym, bs in (j.get("bars") or {}).items():
                for b in bs:
                    rows.append((sym, b["t"][:10], b["c"], b["v"], b.get("vw"), b.get("n")))
            token = j.get("next_page_token")
            time.sleep(pause)
            if not token:
                break
    df = pd.DataFrame(rows, columns=["symbol", "date", "close", "volume", "vwap", "trades"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def load(symbols: list[str], start: str = "2016-01-01", end: str | None = None,
         cutoff: str = "2026-06-01") -> Panel:
    key = f"alpaca_{start}_{end}_{len(symbols)}_{abs(hash(tuple(symbols))) % 10**8}"
    long = cache.load("panels", key)
    if long is None:
        long = bars(symbols, start, end)
        cache.save(long, "panels", key)
    close = long.pivot(index="date", columns="symbol", values="close").sort_index()
    vol = long.pivot(index="date", columns="symbol", values="volume").reindex(close.index)
    c = close.to_numpy()
    ret = np.full_like(c, np.nan)
    with np.errstate(all="ignore"):
        ret[1:] = c[1:] / c[:-1] - 1
    dollar = c * vol.to_numpy()
    T = len(close)
    raw = {"close": c, "ret": ret, "volume": vol.to_numpy(), "dollar_volume": dollar}
    p = Panel(dates=pd.DatetimeIndex(close.index), assets=list(close.columns), raw=raw,
              meta={"source": "alpaca-sip-daily", "survivorship_warning": True,
                    "valid_start": str(close.index[int(T * 0.6)].date()), "cutoff": cutoff,
                    "holdout_start": str(close.index[int(T * 0.95)].date())})
    for n in raw:
        p.add_field(Field(n, (lambda k: lambda r: r[k])(n), 0, f"{n}, known at the close"))
    p.add_field(Field("size", lambda r: np.log(np.clip(r["dollar_volume"], 1, None)), 0,
                      "log dollar volume (a liquidity proxy for size)"))
    return p
