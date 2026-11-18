"""Open Source Asset Pricing (Chen & Zimmermann): 212 published predictors.

The Librarian regresses every candidate on their long-short returns: if 212
published anomalies explain a candidate, it is not new. Files come from the
project's Hugging Face dataset, no account needed. The data is downloaded
directly rather than through the ``openassetpricing`` package, which is GPL.
"""

from __future__ import annotations

import urllib.parse
import urllib.request

import pandas as pd

from . import cache

REPO = "https://huggingface.co/datasets/OpenSourceAP/CrossSection/resolve/{rev}/"
LS_WIDE = "Portfolios/Full Sets OP/PredictorLSretWide.parquet"


def ls_returns(revision: str = "Data-Release-2026.10", refresh: bool = False) -> pd.DataFrame:
    """Monthly long-short returns of every predictor (decimals), index = month end."""
    df = None if refresh else cache.load("osap", f"ls_{revision}")
    if df is None:
        url = REPO.format(rev=urllib.parse.quote(revision)) + urllib.parse.quote(LS_WIDE)
        p = cache.path("osap", f"ls_{revision}.download.parquet")
        req = urllib.request.Request(url, headers={"User-Agent": "alphadesk (open-source research tool)"})
        p.write_bytes(urllib.request.urlopen(req, timeout=120).read())
        df = pd.read_parquet(p)
        date_col = next(c for c in df.columns if c.lower() in ("date", "yyyymm"))
        idx = pd.to_datetime(df[date_col].astype(str).str[:7].str.replace("-", ""), format="%Y%m") + pd.offsets.MonthEnd(0)
        df = df.drop(columns=[date_col]).set_index(idx).sort_index()
        df = df.apply(pd.to_numeric, errors="coerce")
        if df.abs().median().median() > 0.5:   # percent, not decimals
            df = df / 100.0
        cache.save(df, "osap", f"ls_{revision}")
    return df
