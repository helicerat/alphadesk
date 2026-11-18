"""Turning a signal into portfolios: deciles, long-short, turnover, costs."""

from __future__ import annotations

import numpy as np


def decile_weights(signal_row: np.ndarray, q: int = 10, weights_by: np.ndarray | None = None):
    """Long the top quantile, short the bottom. Equal weight unless ``weights_by``."""
    w = np.zeros_like(signal_row, dtype=float)
    m = np.isfinite(signal_row)
    if weights_by is not None:
        m &= np.isfinite(weights_by) & (weights_by > 0)
    n = m.sum()
    if n < 2 * q:
        return w
    idx = np.where(m)[0]
    order = idx[np.argsort(signal_row[m], kind="mergesort")]
    k = n // q
    lo, hi = order[:k], order[-k:]
    if weights_by is None:
        w[hi] = 1.0 / k
        w[lo] = -1.0 / k
    else:
        w[hi] = weights_by[hi] / weights_by[hi].sum()
        w[lo] = -weights_by[lo] / weights_by[lo].sum()
    return w


def long_short(signal: np.ndarray, ret: np.ndarray, hold: int = 1, cost_bps: float = 0.0,
               q: int = 10, weights_by: np.ndarray | None = None, start: int = 0) -> dict:
    """Daily long-short returns. The signal at close t sets weights that earn
    the return of t + 1. Rebalanced every ``hold`` rows. ``cost_bps`` is
    charged per side on traded weight."""
    T, N = signal.shape
    gross = np.full(T, np.nan)
    net = np.full(T, np.nan)
    turnover = np.full(T, np.nan)
    w = np.zeros(N)
    long_leg = np.full(T, np.nan)
    short_leg = np.full(T, np.nan)
    for t in range(start, T - 1):
        if (t - start) % hold == 0:
            wb = None if weights_by is None else weights_by[t]
            new = decile_weights(signal[t], q, wb)
            if not new.any():
                continue
            turnover[t] = np.abs(new - w).sum() / 2
            w = new
        r = np.nan_to_num(ret[t + 1])
        g = float(w @ r)
        traded = turnover[t] * 2 if np.isfinite(turnover[t]) else 0.0
        gross[t + 1] = g
        net[t + 1] = g - traded * cost_bps / 1e4
        long_leg[t + 1] = float(np.clip(w, 0, None) @ r)
        short_leg[t + 1] = float(-np.clip(w, None, 0) @ r)
    return {"gross": gross, "net": net, "turnover": turnover, "long": long_leg, "short": short_leg}


def decile_returns(signal: np.ndarray, ret: np.ndarray, q: int = 10, start: int = 0, end: int | None = None,
                   periods_per_year: int = 252) -> list:
    """Average annualized return of each quantile bucket (equal weight, daily rebalance)."""
    T = signal.shape[0] if end is None else end
    sums = np.zeros(q)
    cnt = 0
    for t in range(start, T - 1):
        s, r = signal[t], ret[t + 1]
        m = np.isfinite(s) & np.isfinite(r)
        if m.sum() < 2 * q:
            continue
        order = np.argsort(s[m], kind="mergesort")
        rr = r[m][order]
        for b, chunk in enumerate(np.array_split(rr, q)):
            sums[b] += chunk.mean()
        cnt += 1
    if cnt == 0:
        return [float("nan")] * q
    return [float(x) for x in sums / cnt * periods_per_year]


def breakeven_cost_bps(gross: np.ndarray, turnover: np.ndarray) -> float:
    """Cost per side (bps) at which mean net return is zero."""
    g = np.nanmean(gross)
    tr = np.nanmean(np.nan_to_num(turnover)) * 2  # traded weight per row
    if tr <= 0:
        return float("inf")
    return float(g / tr * 1e4)
