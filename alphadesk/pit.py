"""Point-in-time checks.

The shift test: compute a field or a signal on data cut at row t, compute it
on the full data, and compare everything before t. Any difference means the
value at some row used data from after that row.
"""

from __future__ import annotations

import numpy as np


def _same(a: np.ndarray, b: np.ndarray, atol: float = 1e-10) -> bool:
    both_nan = np.isnan(a) & np.isnan(b)
    close = np.isclose(a, b, rtol=1e-9, atol=atol)
    return bool(np.all(both_nan | close))


def shift_test_field(panel, name: str, cuts=(0.35, 0.6, 0.85)) -> dict:
    full = panel.get(name)
    T = full.shape[0]
    bad = []
    for c in cuts:
        t = int(T * c)
        part = panel.get(name, upto=t)
        if not _same(part[: t - 1], full[: t - 1]) or not _same(part[t - 1 : t], full[t - 1 : t]):
            bad.append(t)
    return {"field": name, "ok": not bad, "bad_rows": bad}


def shift_test_signal(signal, panel, cuts=(0.4, 0.75)) -> dict:
    full = signal.evaluate(panel)
    T = full.shape[0]
    bad = []
    for c in cuts:
        t = int(T * c)
        part = signal.evaluate(panel, upto=t)
        if not _same(part, full[:t]):
            bad.append(t)
    return {"ok": not bad, "bad_rows": bad}


def shift_test_operator(op_fn, n_arr: int, nums: tuple, seed: int = 0, T: int = 300, N: int = 40) -> bool:
    rng = np.random.default_rng(seed)
    xs = [rng.standard_normal((T, N)) for _ in range(n_arr)]
    full = op_fn(*xs, *nums)
    t = T // 2
    part = op_fn(*[x[:t] for x in xs], *nums)
    return _same(part, full[:t])
