"""A synthetic stock market with signals of known strength.

Used by ``alphadesk demo`` and by the selftest. Every planted signal has a
known information coefficient, so the desk can be graded: it has to find what
is there and bury what is not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .panel import Field, Panel

PLANTED = {"quality": 0.03, "flow": 0.02, "drift": 0.01}  # daily IC


def _ar1(rng, T, N, phi):
    z = np.empty((T, N))
    z[0] = rng.standard_normal(N)
    e = rng.standard_normal((T, N)) * np.sqrt(1 - phi**2)
    for t in range(1, T):
        z[t] = phi * z[t - 1] + e[t]
    return z


def make_market(n_assets: int = 500, n_days: int = 2520, n_noise: int = 60,
                planted: dict | None = None, momentum_ic: float = 0.02,
                seed: int = 7, start: str = "2016-01-04",
                phi: float = 0.9) -> Panel:
    rng = np.random.default_rng(seed)
    planted = dict(PLANTED if planted is None else planted)
    T, N = n_days, n_assets
    dates = pd.bdate_range(start, periods=T)
    assets = [f"S{i:04d}" for i in range(N)]

    beta = rng.uniform(0.6, 1.4, N)
    vol = rng.uniform(0.012, 0.03, N)
    mkt = rng.normal(0.0003, 0.01, T)
    sector = np.tile(rng.integers(0, 10, N).astype(float), (T, 1))

    chars = {k: _ar1(rng, T, N, phi) for k in planted}
    noise = {f"noise_{j:02d}": _ar1(rng, T, N, phi) for j in range(n_noise)}

    ic_total = sum(v * v for v in planted.values()) + momentum_ic**2
    idio_scale = np.sqrt(max(1e-6, 1 - ic_total))

    ret = np.full((T, N), np.nan)
    ret[0] = beta * mkt[0] + vol * rng.standard_normal(N)
    logp = np.zeros((T, N))
    logp[0] = np.log(rng.uniform(10, 200, N))
    eps = rng.standard_normal((T, N))
    for t in range(1, T):
        pred = np.zeros(N)
        for k, ic in planted.items():
            pred += ic * chars[k][t - 1]
        if momentum_ic and t > 252:
            m = logp[t - 22] - logp[t - 253]
            mz = (m - m.mean()) / (m.std() + 1e-12)
            pred += momentum_ic * mz
        ret[t] = beta * mkt[t] + vol * (pred + idio_scale * eps[t])
        logp[t] = logp[t - 1] + np.log1p(ret[t])

    close = np.exp(logp)
    shares = rng.lognormal(18, 1.2, N)
    mcap = close * shares
    volume = shares * rng.lognormal(-4.5, 0.4, (T, N))

    raw = {"ret": ret, "close": close, "mcap": mcap, "volume": volume, "sector": sector}
    raw.update(chars)
    raw.update(noise)

    p = Panel(dates=dates, assets=assets, raw=raw,
              meta={"source": "synthetic", "seed": seed, "planted": planted,
                    "momentum_ic": momentum_ic,
                    "cutoff": str(dates[int(T * 0.8)].date()),
                    "valid_start": str(dates[int(T * 0.6)].date()),
                    "holdout_start": str(dates[int(T * 0.9)].date())})

    for name in ("ret", "close", "volume", "mcap"):
        p.add_field(Field(name, (lambda n: lambda r: r[n])(name), 0, f"{name}, known at the close"))
    p.add_field(Field("size", lambda r: np.log(r["mcap"]), 0, "log market cap"))
    p.add_field(Field("sector", lambda r: r["sector"], 0, "sector code", kind="group"))
    for name in list(planted) + list(noise):
        p.add_field(Field(name, (lambda n: lambda r: r[n])(name), 0, "characteristic"))
    return p


def add_leaky_field(p: Panel, name: str = "insight") -> Panel:
    """A field whose loader claims it is known at t but secretly reads t + 1.

    It is the 'leaking oracle': statistically it looks like a miracle, and
    only the shift test can tell that it is a bug.
    """
    def fn(r):
        x = np.full_like(r["ret"], np.nan)
        x[:-1] = r["ret"][1:]          # tomorrow's return, mislabeled as today
        return x
    p.add_field(Field(name, fn, 0, "analyst insight score"))
    return p


KNOWN_FACTORS = {
    "Mom12m": "cs_rank(delay(log(close), 21) - delay(log(close), 252))",
    "STreversal": "cs_rank(-pct_change(close, 5))",
    "Size": "cs_rank(-size)",
    "LowVol": "cs_rank(-ts_std(ret, 60))",
}
