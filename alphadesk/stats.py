"""Statistics used by the evaluator.

Sources
-------
* Deflated Sharpe ratio, probabilistic Sharpe, minimum track record length:
  Bailey & Lopez de Prado (2012, 2014), "The Deflated Sharpe Ratio".
* Minimum backtest length: Bailey, Borwein, Lopez de Prado, Zhu (2014),
  "Pseudo-Mathematics and Financial Charlatanism", Notices of the AMS.
* Probability of backtest overfitting via CSCV: Bailey, Borwein,
  Lopez de Prado, Zhu (2017), Journal of Computational Finance.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
from scipy import stats as st

EULER = 0.5772156649015329


def _row_ranks(x: np.ndarray) -> np.ndarray:
    import pandas as pd
    return pd.DataFrame(x).rank(axis=1, method="average").to_numpy()


def rowwise_rank_ic(signal: np.ndarray, fwd: np.ndarray, min_names: int = 20) -> np.ndarray:
    """Spearman correlation across assets on every date (vectorized)."""
    m = np.isfinite(signal) & np.isfinite(fwd)
    s = np.where(m, signal, np.nan)
    f = np.where(m, fwd, np.nan)
    rs, rf = _row_ranks(s), _row_ranks(f)
    n = m.sum(axis=1)
    import warnings
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        rs = rs - np.nanmean(rs, axis=1, keepdims=True)
        rf = rf - np.nanmean(rf, axis=1, keepdims=True)
        num = np.nansum(rs * rf, axis=1)
        den = np.sqrt(np.nansum(rs**2, axis=1) * np.nansum(rf**2, axis=1))
        ic = num / den
    ic[(n < min_names) | ~np.isfinite(ic)] = np.nan
    return ic


def ic_summary(ic: np.ndarray, step: int = 1) -> dict:
    """Mean IC and a t-stat from non-overlapping observations (every ``step`` rows)."""
    x = ic[np.isfinite(ic)]
    xs = ic[::step]
    xs = xs[np.isfinite(xs)]
    if len(xs) < 3:
        return {"mean": float("nan"), "t": float("nan"), "ir": float("nan"), "pos": float("nan"), "n": int(len(xs))}
    mean = float(np.mean(x))
    sd = float(np.std(xs, ddof=1))
    t = float(np.mean(xs) / (sd / math.sqrt(len(xs)))) if sd > 0 else float("nan")
    return {"mean": mean, "t": t, "ir": float(np.mean(xs) / sd) if sd > 0 else float("nan"),
            "pos": float(np.mean(xs > 0)), "n": int(len(xs))}


def sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if len(r) < 3 or r.std(ddof=1) == 0:
        return float("nan")
    return float(r.mean() / r.std(ddof=1))


def annualize(sr_per_period: float, periods_per_year: float) -> float:
    return sr_per_period * math.sqrt(periods_per_year)


def expected_max_sr(n_trials: float, sr_var: float = 1.0) -> float:
    """Expected maximum of ``n_trials`` independent Sharpe estimates with zero true Sharpe."""
    n = max(float(n_trials), 1.0)
    if n <= 1:
        return 0.0
    z1 = st.norm.ppf(1 - 1 / n)
    z2 = st.norm.ppf(1 - 1 / (n * math.e))
    return math.sqrt(sr_var) * ((1 - EULER) * z1 + EULER * z2)


def probabilistic_sr(sr: float, sr_bench: float, T: int, skew: float, kurt: float) -> float:
    """Probability that the true Sharpe exceeds ``sr_bench`` (per-period units)."""
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr**2
    if T < 3 or denom <= 0:
        return float("nan")
    return float(st.norm.cdf((sr - sr_bench) * math.sqrt(T - 1) / math.sqrt(denom)))


def deflated_sr(returns: np.ndarray, n_trials: float, sr_var_trials: float | None = None) -> dict:
    """Deflated Sharpe ratio of one return series selected out of ``n_trials``."""
    r = returns[np.isfinite(returns)]
    T = len(r)
    sr = sharpe(r)
    skew = float(st.skew(r)) if T > 3 else 0.0
    kurt = float(st.kurtosis(r, fisher=False)) if T > 3 else 3.0
    if sr_var_trials is None or not np.isfinite(sr_var_trials) or sr_var_trials <= 0:
        # variance of a Sharpe estimate under the null, per period
        sr_var_trials = (1 + 0.5 * sr**2) / max(T - 1, 1)
    sr0 = expected_max_sr(n_trials, sr_var_trials)
    return {"sr": sr, "sr0": sr0, "T": T, "skew": skew, "kurt": kurt,
            "dsr": probabilistic_sr(sr, sr0, T, skew, kurt), "n_trials": float(n_trials)}


def min_track_record(sr: float, sr_bench: float, skew: float, kurt: float, alpha: float = 0.05) -> float:
    """Periods needed before ``sr`` is distinguishable from ``sr_bench`` at level ``alpha``."""
    if not np.isfinite(sr) or sr <= sr_bench:
        return float("inf")
    z = st.norm.ppf(1 - alpha)
    return 1 + (1 - skew * sr + (kurt - 1) / 4 * sr**2) * (z / (sr - sr_bench)) ** 2


def min_backtest_length_years(n_trials: float, sr_annual: float) -> float:
    """Years of data below which the best of ``n_trials`` noise strategies is
    expected to reach ``sr_annual`` (MinBTL, Bailey et al. 2014)."""
    if sr_annual <= 0:
        return float("inf")
    return (expected_max_sr(n_trials, 1.0) / sr_annual) ** 2


def effective_n(returns_matrix: np.ndarray) -> float:
    """Effective number of independent trials: participation ratio of the
    eigenvalues of the correlation matrix of trial returns (T x K)."""
    M = returns_matrix
    K = M.shape[1]
    if K <= 1:
        return float(K)
    ok = np.isfinite(M).all(axis=1)
    M = M[ok]
    if M.shape[0] < 10:
        return float(K)
    sd = M.std(axis=0)
    M = M[:, sd > 0]
    if M.shape[1] <= 1:
        return float(M.shape[1])
    C = np.corrcoef(M, rowvar=False)
    ev = np.clip(np.linalg.eigvalsh(C), 0, None)
    return float(ev.sum() ** 2 / (ev**2).sum())


def pbo_cscv(returns_matrix: np.ndarray, n_blocks: int = 16) -> dict:
    """Probability of backtest overfitting by combinatorially symmetric
    cross-validation. ``returns_matrix`` is T x K (K variants)."""
    M = returns_matrix[np.isfinite(returns_matrix).all(axis=1)]
    T, K = M.shape
    if K < 2 or T < n_blocks * 4:
        return {"pbo": float("nan"), "n_combos": 0}
    blocks = np.array_split(np.arange(T), n_blocks)
    s1 = np.array([M[b].sum(axis=0) for b in blocks])        # S x K
    s2 = np.array([(M[b] ** 2).sum(axis=0) for b in blocks])
    n = np.array([len(b) for b in blocks])
    logits = []
    for combo in itertools.combinations(range(n_blocks), n_blocks // 2):
        is_mask = np.zeros(n_blocks, bool)
        is_mask[list(combo)] = True
        def sr(mask):
            nn = n[mask].sum()
            mu = s1[mask].sum(axis=0) / nn
            var = s2[mask].sum(axis=0) / nn - mu**2
            return mu / np.sqrt(np.maximum(var, 1e-18))
        sr_is, sr_oos = sr(is_mask), sr(~is_mask)
        best = int(np.argmax(sr_is))
        rank = st.rankdata(sr_oos)[best] / (K + 1)
        logits.append(math.log(rank / (1 - rank)))
    logits = np.array(logits)
    return {"pbo": float(np.mean(logits <= 0)), "n_combos": int(len(logits))}


def ols_alpha(y: np.ndarray, X: np.ndarray) -> dict:
    """OLS of y on X with intercept. Returns alpha, its t-stat, betas and t-stats."""
    m = np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X = y[m], X[m]
    n, k = X.shape
    if n <= k + 5:
        return {"alpha": float("nan"), "t_alpha": float("nan"), "beta": [], "t_beta": []}
    A = np.column_stack([np.ones(n), X])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ coef
    s2 = resid @ resid / (n - k - 1)
    cov = s2 * np.linalg.pinv(A.T @ A)
    se = np.sqrt(np.diag(cov))
    t = coef / se
    return {"alpha": float(coef[0]), "t_alpha": float(t[0]),
            "beta": coef[1:].tolist(), "t_beta": t[1:].tolist(), "n": int(n)}
