"""Canonical OHLCV schema + validation.

The canonical 4H dataset used by every downstream module is a parquet/CSV
with exactly these columns:

    symbol         str      canonical instrument id, e.g. "BTCUSDT"
    timestamp_utc  datetime bar OPEN time, timezone-aware UTC
    open           float
    high           float
    low            float
    close          float
    volume         float    base-asset volume; 0 if the feed has no volume

Optional columns (all NaN-tolerant):
    funding_rate, open_interest, spread, quote_volume, trades,
    taker_buy_volume, dxy, usdtry, benchmark

Conventions
-----------
* ``timestamp_utc`` is the bar OPEN time (Binance convention). A 4H bar
  stamped 2024-01-01T00:00Z covers [00:00Z, 04:00Z) and is only *known*
  at 04:00Z. Every feature/label/backtest in this repo shifts accordingly;
  decisions for that bar are executed at the NEXT bar's open.
* Prices are raw (not adjusted). Any adjustment must be delivered as an
  extra column so the raw series stays auditable.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import CANONICAL_COLUMNS, OPTIONAL_COLUMNS, UTC

REQUIRED_DTYPES = {
    "symbol": "object",
    "timestamp_utc": "datetime64[ns, UTC]",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "float64",
}


def empty_frame(extra: Optional[Iterable[str]] = None) -> pd.DataFrame:
    df = pd.DataFrame(columns=list(CANONICAL_COLUMNS) + list(extra or []))
    return coerce(df)


def coerce(df: pd.DataFrame) -> pd.DataFrame:
    """Force the canonical dtypes / ordering without touching values."""
    missing = [c for c in CANONICAL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing canonical columns: {missing}")
    out = df.copy()
    for col in OPTIONAL_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan
    cols = list(CANONICAL_COLUMNS) + [c for c in OPTIONAL_COLUMNS if c in out.columns]
    cols += [c for c in out.columns if c not in cols]
    out = out[cols]
    out["timestamp_utc"] = pd.to_datetime(out["timestamp_utc"], utc=True, errors="coerce")
    out["symbol"] = out["symbol"].astype(str)
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    for col in OPTIONAL_COLUMNS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    return out.sort_values("timestamp_utc").reset_index(drop=True)


def split_by_symbol(df: pd.DataFrame) -> List[Tuple[str, pd.DataFrame]]:
    return [(str(sym), g.reset_index(drop=True)) for sym, g in df.groupby("symbol", sort=True)]


def to_wide(df: pd.DataFrame, field: str = "close") -> pd.DataFrame:
    """symbol x timestamp matrix, used for correlation / portfolio work."""
    return df.pivot(index="timestamp_utc", columns="symbol", values=field).sort_index()


def save_parquet(df: pd.DataFrame, path: str) -> None:
    coerce(df).to_parquet(path, index=False)


def load_parquet(path: str) -> pd.DataFrame:
    return coerce(pd.read_parquet(path))


__all__ = [
    "REQUIRED_DTYPES", "empty_frame", "coerce", "split_by_symbol",
    "to_wide", "save_parquet", "load_parquet", "CANONICAL_COLUMNS",
    "OPTIONAL_COLUMNS", "UTC",
]
