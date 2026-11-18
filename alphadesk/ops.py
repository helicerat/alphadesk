"""Operators of the formula language.

Every operator takes and returns a 2-D float array shaped (time, asset).
Rows are dates in ascending order. A value in row t may only depend on
rows <= t. The shift test in ``alphadesk.pit`` checks this property for
every operator on every run of the selftest.
"""

from __future__ import annotations

import numpy as np

Array = np.ndarray


def _check_window(w) -> int:
    if not float(w).is_integer() or int(w) < 1:
        raise ValueError(f"window must be a positive integer, got {w}")
    return int(w)


def _rolling(x: Array, w: int, fn) -> Array:
    """Apply ``fn`` over a trailing window of ``w`` rows (inclusive of t)."""
    T = x.shape[0]
    out = np.full_like(x, np.nan, dtype=float)
    if w > T:
        return out
    # sliding_window_view gives windows ending at rows w-1 .. T-1
    view = np.lib.stride_tricks.sliding_window_view(x, w, axis=0)  # (T-w+1, N, w)
    import warnings
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # windows that are all NaN stay NaN
        out[w - 1 :] = fn(view)
    return out


# ---------------------------------------------------------------- time series

def delay(x: Array, k) -> Array:
    k = int(k)
    if k < 0:
        raise ValueError("delay must be >= 0: a negative delay reads the future")
    if k == 0:
        return x.copy()
    out = np.full_like(x, np.nan, dtype=float)
    out[k:] = x[:-k]
    return out


def delta(x: Array, k) -> Array:
    return x - delay(x, k)


def pct_change(x: Array, k) -> Array:
    with np.errstate(all="ignore"):
        return x / delay(x, k) - 1.0


def ts_mean(x: Array, w) -> Array:
    w = _check_window(w)
    return _rolling(x, w, lambda v: np.nanmean(v, axis=-1))


def ts_sum(x: Array, w) -> Array:
    w = _check_window(w)
    return _rolling(x, w, lambda v: np.nansum(v, axis=-1))


def ts_std(x: Array, w) -> Array:
    w = _check_window(w)
    return _rolling(x, w, lambda v: np.nanstd(v, axis=-1, ddof=1))


def ts_min(x: Array, w) -> Array:
    w = _check_window(w)
    return _rolling(x, w, lambda v: np.nanmin(v, axis=-1))


def ts_max(x: Array, w) -> Array:
    w = _check_window(w)
    return _rolling(x, w, lambda v: np.nanmax(v, axis=-1))


def ts_rank(x: Array, w) -> Array:
    """Percentile of today's value inside its own trailing window."""
    w = _check_window(w)

    def fn(v):
        last = v[..., -1:]
        valid = np.isfinite(v)
        below = np.sum((v < last) & valid, axis=-1)
        n = np.sum(valid, axis=-1)
        with np.errstate(all="ignore"):
            r = below / np.maximum(n - 1, 1)
        r[~np.isfinite(v[..., -1])] = np.nan
        return r

    return _rolling(x, w, fn)


def ts_zscore(x: Array, w) -> Array:
    with np.errstate(all="ignore"):
        return (x - ts_mean(x, w)) / ts_std(x, w)


def ts_corr(x: Array, y: Array, w) -> Array:
    w = _check_window(w)
    mx, my = ts_mean(x, w), ts_mean(y, w)
    mxy = ts_mean(x * y, w)
    sx, sy = ts_std(x, w), ts_std(y, w)
    with np.errstate(all="ignore"):
        cov = (mxy - mx * my) * w / (w - 1)
        return cov / (sx * sy)


def ewm(x: Array, halflife) -> Array:
    h = float(halflife)
    if h <= 0:
        raise ValueError("halflife must be positive")
    a = 1 - 0.5 ** (1 / h)
    out = np.full_like(x, np.nan, dtype=float)
    prev = np.full(x.shape[1], np.nan)
    for t in range(x.shape[0]):
        cur = x[t]
        prev = np.where(np.isfinite(prev), np.where(np.isfinite(cur), a * cur + (1 - a) * prev, prev), cur)
        out[t] = prev
    return out


# ---------------------------------------------------------- cross section

def cs_rank(x: Array) -> Array:
    """Rank across assets on each date, scaled to [0, 1], ties averaged."""
    import pandas as pd
    r = pd.DataFrame(x).rank(axis=1, method="average").to_numpy()
    n = np.isfinite(x).sum(axis=1, keepdims=True)
    with np.errstate(all="ignore"):
        out = (r - 1) / (n - 1)
    out[(n < 2).repeat(x.shape[1], axis=1)] = np.nan
    return out


def cs_zscore(x: Array) -> Array:
    with np.errstate(all="ignore"):
        mu = np.nanmean(x, axis=1, keepdims=True)
        sd = np.nanstd(x, axis=1, keepdims=True)
        return (x - mu) / sd


def cs_demean(x: Array) -> Array:
    with np.errstate(all="ignore"):
        return x - np.nanmean(x, axis=1, keepdims=True)


def neutralize(x: Array, group: Array) -> Array:
    """Demean ``x`` inside each group (for example a sector code) on each date."""
    out = np.full_like(x, np.nan, dtype=float)
    for t in range(x.shape[0]):
        row, g = x[t], group[t]
        m = np.isfinite(row) & np.isfinite(g)
        if not m.any():
            continue
        gs = g[m].astype(int)
        uniq, inv = np.unique(gs, return_inverse=True)
        means = np.bincount(inv, weights=row[m]) / np.bincount(inv)
        o = np.full(row.shape, np.nan)
        o[m] = row[m] - means[inv]
        out[t] = o
    return out


def winsorize(x: Array, q=0.01) -> Array:
    q = float(q)
    with np.errstate(all="ignore"):
        lo = np.nanquantile(x, q, axis=1, keepdims=True)
        hi = np.nanquantile(x, 1 - q, axis=1, keepdims=True)
    return np.clip(x, lo, hi)


# ---------------------------------------------------------------- elementwise

def abs_(x: Array) -> Array:
    return np.abs(x)


def log(x: Array) -> Array:
    with np.errstate(all="ignore"):
        return np.where(x > 0, np.log(x), np.nan)


def sign(x: Array) -> Array:
    return np.sign(x)


def sqrt(x: Array) -> Array:
    with np.errstate(all="ignore"):
        return np.where(x >= 0, np.sqrt(x), np.nan)


def clip(x: Array, lo, hi) -> Array:
    return np.clip(x, float(lo), float(hi))


def where_le(x: Array, y, a: Array, b) -> Array:
    """``a`` where ``x <= y``, else ``b``."""
    return np.where(x <= y, a, b)


# name -> (function, number of array arguments, number of numeric arguments)
OPERATORS = {
    "delay": (delay, 1, 1),
    "delta": (delta, 1, 1),
    "pct_change": (pct_change, 1, 1),
    "ts_mean": (ts_mean, 1, 1),
    "ts_sum": (ts_sum, 1, 1),
    "ts_std": (ts_std, 1, 1),
    "ts_min": (ts_min, 1, 1),
    "ts_max": (ts_max, 1, 1),
    "ts_rank": (ts_rank, 1, 1),
    "ts_zscore": (ts_zscore, 1, 1),
    "ts_corr": (ts_corr, 2, 1),
    "ewm": (ewm, 1, 1),
    "cs_rank": (cs_rank, 1, 0),
    "cs_zscore": (cs_zscore, 1, 0),
    "cs_demean": (cs_demean, 1, 0),
    "neutralize": (neutralize, 2, 0),
    "winsorize": (winsorize, 1, 1),
    "abs": (abs_, 1, 0),
    "log": (log, 1, 0),
    "sign": (sign, 1, 0),
    "sqrt": (sqrt, 1, 0),
    "clip": (clip, 1, 2),
}

# operators whose numeric argument is a look-back in rows
LOOKBACK_OPS = {"delay", "delta", "pct_change", "ts_mean", "ts_sum", "ts_std", "ts_min",
                "ts_max", "ts_rank", "ts_zscore", "ts_corr"}
