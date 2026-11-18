"""A small on-disk cache. Parquet when pyarrow is installed, pickle otherwise."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


def home() -> Path:
    p = Path(os.environ.get("ALPHADESK_HOME", Path.home() / ".alphadesk"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _has_pyarrow() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


def path(*parts: str) -> Path:
    p = home().joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def save(df: pd.DataFrame, *parts: str) -> Path:
    p = path(*parts)
    if _has_pyarrow():
        df.to_parquet(p.with_suffix(".parquet"))
        return p.with_suffix(".parquet")
    df.to_pickle(p.with_suffix(".pkl"))
    return p.with_suffix(".pkl")


def load(*parts: str) -> pd.DataFrame | None:
    p = path(*parts)
    if p.with_suffix(".parquet").exists() and _has_pyarrow():
        return pd.read_parquet(p.with_suffix(".parquet"))
    if p.with_suffix(".pkl").exists():
        return pd.read_pickle(p.with_suffix(".pkl"))
    return None
