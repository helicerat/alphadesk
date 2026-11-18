"""SEC EDGAR fundamentals, stamped with the day each number became public.

``companyfacts`` gives every XBRL fact a company ever filed, with the filing
date. Two traps this loader handles:

* one 10-K carries several years of numbers, so the same (concept, period)
  appears in many filings. The point-in-time value is the one from the
  *first* filing; later restatements only become known when they are filed.
* ``fy`` is the fiscal year of the filing, not of the number. Periods are
  identified by their ``end`` date.

The SEC asks every client to identify itself. Set ``sec_user_agent`` in the
config or the ``SEC_USER_AGENT`` environment variable to "Name email".
Fair access is 10 requests per second; the loader stays well under it.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

import numpy as np
import pandas as pd

from . import cache

TICKERS = "https://www.sec.gov/files/company_tickers_exchange.json"
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


def _ua() -> str:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError("SEC EDGAR needs you to identify yourself: set SEC_USER_AGENT='Your Name you@example.com' "
                           "or run `alphadesk config set sec.user_agent ...`")
    return ua


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _ua(), "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def tickers() -> pd.DataFrame:
    """Current SEC ticker list. Delisted companies are not in it: this is the
    survivorship gap the reports warn about."""
    df = cache.load("edgar", "tickers")
    if df is None:
        j = _get_json(TICKERS)
        df = pd.DataFrame(j["data"], columns=j["fields"])
        cache.save(df, "edgar", "tickers")
    return df


def company_facts(cik: int) -> dict:
    p = cache.path("edgar", "facts", f"{cik}.json")
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    time.sleep(0.15)
    j = _get_json(FACTS.format(cik=int(cik)))
    p.write_text(json.dumps(j), encoding="utf-8")
    return j


def first_filed(facts: dict, concept: str, taxonomy: str = "us-gaap", unit: str = "USD",
                forms=("10-K", "10-Q", "10-K/A", "10-Q/A")) -> pd.DataFrame:
    """One row per reporting period: the value from the first filing, and when it was filed."""
    try:
        rows = facts["facts"][taxonomy][concept]["units"][unit]
    except KeyError:
        return pd.DataFrame(columns=["end", "start", "val", "filed", "form"])
    df = pd.DataFrame(rows)
    df = df[df["form"].isin(forms)].copy()
    if df.empty:
        return pd.DataFrame(columns=["end", "start", "val", "filed", "form"])
    df["end"] = pd.to_datetime(df["end"])
    df["filed"] = pd.to_datetime(df["filed"])
    if "start" in df:
        df["start"] = pd.to_datetime(df["start"])
    else:
        df["start"] = pd.NaT
    df = df.sort_values("filed").drop_duplicates(["start", "end"], keep="first")
    return df[["end", "start", "val", "filed", "form"]].reset_index(drop=True)


def as_known_on(series: pd.DataFrame, dates: pd.DatetimeIndex, quarterly_only: bool = False) -> np.ndarray:
    """The latest period end known on each date, using only filings made on or
    before that date. Returns the value aligned to ``dates``."""
    s = series.copy()
    if quarterly_only and s["start"].notna().any():
        days = (s["end"] - s["start"]).dt.days
        s = s[(days > 80) & (days < 100)]
    out = np.full(len(dates), np.nan)
    if s.empty:
        return out
    s = s.sort_values(["filed", "end"])
    best_end = pd.Timestamp.min
    j = 0
    rows = list(s.itertuples())
    cur = np.nan
    for i, d in enumerate(dates):
        # a filing is usable from the next day: acceptance can come after the close
        while j < len(rows) and rows[j].filed < d:
            if rows[j].end >= best_end:
                best_end, cur = rows[j].end, rows[j].val
            j += 1
        out[i] = cur
    return out
