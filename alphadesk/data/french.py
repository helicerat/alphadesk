"""Ken French data library: daily Fama-French 5 factors and momentum.

Used as the baseline in the novelty check: a candidate whose returns are
explained by these factors is not new.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile

import pandas as pd

from . import cache

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {"ff5": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
         "mom": "F-F_Momentum_Factor_daily_CSV.zip"}


def _read(name: str) -> pd.DataFrame:
    req = urllib.request.Request(BASE + FILES[name], headers={"User-Agent": "alphadesk (open-source research tool)"})
    raw = urllib.request.urlopen(req, timeout=60).read()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip()[:8].isdigit()) - 1
    rows = []
    for l in lines[start + 1:]:
        parts = [p.strip() for p in l.split(",")]
        if not parts[0].isdigit() or len(parts[0]) != 8:
            break
        rows.append(parts)
    header = [h.strip() for h in lines[start].split(",")]
    header[0] = "date"
    df = pd.DataFrame(rows, columns=header[: len(rows[0])])
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df = df.set_index("date").astype(float) / 100.0
    return df


def factors(refresh: bool = False) -> pd.DataFrame:
    """Daily returns of Mkt-RF, SMB, HML, RMW, CMA, Mom and RF, in decimals."""
    df = None if refresh else cache.load("french", "daily")
    if df is None:
        ff5 = _read("ff5")
        mom = _read("mom")
        mom.columns = ["Mom"]
        df = ff5.join(mom, how="left")
        cache.save(df, "french", "daily")
    return df
