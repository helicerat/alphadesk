"""Crypto perpetual futures from Binance's public archive (data.binance.vision).

No key, no account. The archive keeps symbols after they are delisted, so a
backtest on it is not limited to the coins that survived. Every zip comes
with a SHA-256 checksum, which the loader verifies.
"""

from __future__ import annotations

import hashlib
import io
import re
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd

from . import cache
from ..panel import Field, Panel

S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
FILES = "https://data.binance.vision"
UA = {"User-Agent": "alphadesk (open-source research tool)"}


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _list(prefix: str, delimiter: str | None = None) -> tuple[list, list]:
    keys, prefixes, marker = [], [], ""
    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    while True:
        url = f"{S3}?prefix={prefix}&max-keys=1000" + (f"&delimiter={delimiter}" if delimiter else "") + \
              (f"&marker={marker}" if marker else "")
        root = ET.fromstring(_get(url))
        keys += [k.text for k in root.iter(f"{ns}Key")]
        prefixes += [p.text for p in root.iter(f"{ns}Prefix") if p.text != prefix]
        if root.findtext(f"{ns}IsTruncated") != "true":
            return keys, prefixes
        marker = (keys or prefixes)[-1]


def symbols(quote: str = "USDT") -> list[str]:
    """Every USD-M perpetual the archive has ever listed, delisted ones included."""
    _, pre = _list("data/futures/um/monthly/klines/", "/")
    out = sorted({p.rstrip("/").split("/")[-1] for p in pre})
    return [s for s in out if s.endswith(quote) and re.fullmatch(r"[A-Z0-9]+", s)]


def _zip_csv(key: str) -> pd.DataFrame | None:
    local = cache.path("binance", key.replace("/", "_"))
    if local.exists():
        raw = local.read_bytes()
    else:
        try:
            raw = _get(f"{FILES}/{key}")
            chk = _get(f"{FILES}/{key}.CHECKSUM").decode().split()[0]
        except Exception:
            return None
        if hashlib.sha256(raw).hexdigest() != chk:
            raise IOError(f"checksum mismatch for {key}")
        local.write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        data = z.read(z.namelist()[0])
    first = data[:200].decode(errors="ignore")
    header = 0 if re.match(r"[a-z_]", first) else None
    return pd.read_csv(io.BytesIO(data), header=header)


KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
         "trades", "taker_base", "taker_quote", "ignore"]


def _symbol_daily(sym: str, since: str, until: str | None) -> pd.DataFrame | None:
    keys, _ = _list(f"data/futures/um/monthly/klines/{sym}/1d/")
    keys = [k for k in keys if k.endswith(".zip")]
    months = [k for k in keys if since <= k[-11:-4] and (until is None or k[-11:-4] <= until)]
    frames = []
    for k in months:
        df = _zip_csv(k)
        if df is None or df.empty:
            continue
        df = df.iloc[:, :12]
        df.columns = KCOLS
        frames.append(df)
    if not frames:
        return None
    k = pd.concat(frames)
    k["open_time"] = pd.to_numeric(k["open_time"], errors="coerce")
    k = k.dropna(subset=["open_time"])
    unit = "us" if k["open_time"].iloc[0] > 1e14 else "ms"
    k["date"] = pd.to_datetime(k["open_time"], unit=unit).dt.normalize()
    k = k.drop_duplicates("date").set_index("date").sort_index()
    out = k[["close", "quote_volume", "taker_quote"]].astype(float)

    fkeys, _ = _list(f"data/futures/um/monthly/fundingRate/{sym}/")
    fr = [_zip_csv(x) for x in fkeys if x.endswith(".zip") and since <= x[-11:-4]]
    fr = [f for f in fr if f is not None and not f.empty]
    if fr:
        f = pd.concat(fr).iloc[:, :3]
        f.columns = ["calc_time", "interval", "rate"]
        f["calc_time"] = pd.to_numeric(f["calc_time"], errors="coerce")
        f = f.dropna(subset=["calc_time"])
        f["date"] = pd.to_datetime(f["calc_time"], unit="ms").dt.normalize()
        out["funding"] = f.groupby("date")["rate"].sum().reindex(out.index)
    else:
        out["funding"] = np.nan
    return out


def load(since: str = "2022-01", until: str | None = None, universe: list | None = None,
         max_symbols: int | None = None, workers: int = 12, progress=None) -> Panel:
    """Daily panel of USDT perpetuals. Rows are UTC days; a row's close is
    known at 00:00 UTC of the next day, which is when the signal trades."""
    syms = universe or symbols()
    if max_symbols:
        syms = syms[:max_symbols]
    tag = f"{since}_{until}_{len(syms)}_{hashlib.sha1(','.join(syms).encode()).hexdigest()[:8]}"
    cached = cache.load("panels", f"binance_{tag}")
    if cached is None:
        with ThreadPoolExecutor(workers) as ex:
            parts = {}
            for i, (s, df) in enumerate(zip(syms, ex.map(lambda s: _symbol_daily(s, since, until), syms))):
                if df is not None and len(df) > 30:
                    parts[s] = df
                if progress:
                    progress(i + 1, len(syms), s)
        long = pd.concat(parts, names=["symbol", "date"]).reset_index()
        cache.save(long, "panels", f"binance_{tag}")
    else:
        long = cached
    return panel_from_long(long)


def panel_from_long(long: pd.DataFrame) -> Panel:
    wide = {c: long.pivot(index="date", columns="symbol", values=c).sort_index()
            for c in ("close", "quote_volume", "taker_quote", "funding")}
    dates = wide["close"].index
    assets = list(wide["close"].columns)
    close = wide["close"].to_numpy()
    ret = np.full_like(close, np.nan)
    with np.errstate(all="ignore"):
        ret[1:] = close[1:] / close[:-1] - 1
    raw = {"close": close, "ret": ret, "quote_volume": wide["quote_volume"].to_numpy(),
           "taker_quote": wide["taker_quote"].to_numpy(), "funding": wide["funding"].to_numpy()}
    T = len(dates)
    p = Panel(dates=pd.DatetimeIndex(dates), assets=assets, raw=raw,
              meta={"source": "binance-um-perp", "frequency": "1d",
                    "valid_start": str(dates[int(T * 0.55)].date()),
                    "cutoff": "2026-06-01" if dates[-1] > pd.Timestamp("2026-07-01") else str(dates[int(T * 0.8)].date()),
                    "holdout_start": str(dates[int(T * 0.93)].date())})
    for name in raw:
        p.add_field(Field(name, (lambda n: lambda r: r[n])(name), 0, f"{name}, known at the daily close"))
    p.add_field(Field("size", lambda r: np.log(r["quote_volume"].clip(min=1)), 0,
                      "log quote volume (crypto has no market cap here)"))
    p.add_field(Field("taker_ratio", lambda r: r["taker_quote"] / r["quote_volume"], 0,
                      "share of volume bought by takers"))
    return p
