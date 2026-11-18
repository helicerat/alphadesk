"""Panel data: dates x assets, with every field stamped by when it becomes known.

A field is a function of the raw data. ``known_at`` says how many rows after
row t the value in row t becomes public:

* ``0``  the value in row t is known at the close of t (prices, volume,
         fundamentals already aligned to their first filing date)
* ``1``  the value in row t is only known at the close of t + 1
         (for example tomorrow's return). Using it at t needs ``delay(x, 1)``.

The formula compiler refuses any signal whose value at t would need data
known after t. The shift test re-runs the field function on data cut at t
and checks that nothing before t changes, which catches a loader that lies
about its own ``known_at``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd


@dataclass
class Field:
    name: str
    fn: Callable[[dict], np.ndarray]  # raw dict (each value T x N) -> T x N
    known_at: int = 0
    description: str = ""
    kind: str = "numeric"  # numeric | group


@dataclass
class Panel:
    dates: pd.DatetimeIndex
    assets: list
    raw: dict  # name -> np.ndarray (T x N)
    fields: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    _cache: dict = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------- fields
    def add_field(self, f: Field):
        self.fields[f.name] = f
        self._cache.pop(f.name, None)

    def get(self, name: str, upto: int | None = None) -> np.ndarray:
        """Field values. ``upto`` cuts the raw data at row ``upto`` (exclusive)
        before computing, which is what the shift test uses."""
        f = self.fields[name]
        if upto is None:
            if name not in self._cache:
                self._cache[name] = np.asarray(f.fn(self.raw), dtype=float)
            return self._cache[name]
        cut = {k: v[:upto] for k, v in self.raw.items()}
        return np.asarray(f.fn(cut), dtype=float)

    @property
    def T(self) -> int:
        return len(self.dates)

    @property
    def N(self) -> int:
        return len(self.assets)

    # ------------------------------------------------------------- returns
    def returns(self) -> np.ndarray:
        """Close-to-close simple returns, row t = return from t-1 to t."""
        return self.raw["ret"]

    def forward_returns(self, h: int = 1) -> np.ndarray:
        """Return from close t to close t+h, aligned to row t. Never a field."""
        r = self.raw["ret"]
        lr = np.log1p(r)
        T = r.shape[0]
        out = np.full_like(r, np.nan, dtype=float)
        csum = np.cumsum(np.nan_to_num(lr), axis=0)
        out[: T - h] = csum[h:] - csum[:-h]
        out = np.expm1(out)
        # an asset with no price at t+h has no forward return
        miss = np.zeros_like(r, dtype=bool)
        miss[: T - h] = np.isnan(r[h:])
        out[miss] = np.nan
        return out

    def row_of(self, date) -> int:
        return int(self.dates.searchsorted(pd.Timestamp(date)))

    # ------------------------------------------------------------- identity
    def data_hash(self) -> str:
        h = hashlib.sha256()
        h.update(str(self.dates[0]).encode() + str(self.dates[-1]).encode())
        h.update(str(len(self.assets)).encode())
        for k in sorted(self.raw):
            a = np.ascontiguousarray(self.raw[k])
            h.update(k.encode())
            h.update(a[:: max(1, a.shape[0] // 64)].tobytes())
        return h.hexdigest()[:12]
