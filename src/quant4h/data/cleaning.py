"""Explicit, logged data cleaning. Nothing here runs implicitly.

Policy
------
* ``data/raw`` is immutable. Cleaning never writes back to it.
* Cleaning produces a NEW frame plus a ``CleaningLog`` audit record.
* **No row is ever dropped silently.** Every mutation is recorded with the
  row count before/after and a reason.
* Values are FLAGGED, not rewritten. The single exception is
  ``repair_ohlc_envelope`` which widens high/low so that
  ``low <= min(open, close)`` and ``high >= max(open, close)`` hold; it never
  moves a close price and never deletes a bar.

Preferred order of operations (``clean_pipeline``):
    dedupe_and_sort -> flag_invalid_ohlc -> drop_invalid_ohlc (only the rows
    that are unusable: NaN / non-positive) -> repair_ohlc_envelope
    -> winsorise_returns (flag only) -> drop_forming_last_bar
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from ..config import UTC


@dataclass
class CleaningLog:
    steps: List[Dict[str, Any]] = field(default_factory=list)

    def record(self, step: str, rows_before: int, rows_after: int, detail: str = "",
               **extra: Any) -> None:
        self.steps.append({"step": step, "rows_before": int(rows_before),
                           "rows_after": int(rows_after),
                           "rows_delta": int(rows_after) - int(rows_before),
                           "detail": detail, **extra})

    def to_dict(self) -> Dict[str, Any]:
        return {"steps": self.steps,
                "total_rows_in": self.steps[0]["rows_before"] if self.steps else 0,
                "total_rows_out": self.steps[-1]["rows_after"] if self.steps else 0,
                "rows_dropped_total": sum(abs(s["rows_delta"]) for s in self.steps)}

    @property
    def dropped(self) -> int:
        return sum(-s["rows_delta"] for s in self.steps if s["rows_delta"] < 0)


def dedupe_and_sort(df: pd.DataFrame, log: CleaningLog, keep: str = "first") -> pd.DataFrame:
    """Sort by timestamp and drop duplicate timestamps.

    "first"/"last" refer to ARRIVAL ORDER (the row order of the input frame),
    NOT to the sorted order - otherwise the result would silently depend on how
    the caller happened to concatenate the data. Arrival order is recorded in
    ``_arrival`` so the decision is reproducible and auditable.
    """
    n0 = len(df)
    if keep not in ("first", "last"):
        raise ValueError(f"keep must be 'first' or 'last', got {keep!r}")
    work = df.copy()
    work["_arrival"] = np.arange(len(work), dtype="int64")
    work = work.sort_values(["timestamp_utc", "_arrival"], kind="mergesort")
    dup_ts = work["timestamp_utc"].duplicated(keep=False)
    chosen = work.drop_duplicates("timestamp_utc", keep=keep)
    chosen = chosen.sort_values("timestamp_utc", kind="mergesort").reset_index(drop=True)
    n_dup = int(dup_ts.sum())
    log.record("dedupe_and_sort", n0, len(chosen),
               f"{n_dup} row(s) shared a duplicated timestamp; kept '{keep}' by ARRIVAL order",
               duplicated_rows=n_dup, keep=keep)
    return chosen.drop(columns=["_arrival"])


def flag_invalid_ohlc(df: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Add boolean flags describing every OHLC defect. Drops nothing."""
    n0 = len(df)
    o, h, l, c = (pd.to_numeric(df[k], errors="coerce") for k in ("open", "high", "low", "close"))
    out = df.copy()
    out["is_nan_ohlc"] = (o.isna() | h.isna() | l.isna() | c.isna()).to_numpy()
    out["is_nonpositive"] = ((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)).fillna(False).to_numpy()
    out["is_high_below_low"] = (h < l).fillna(False).to_numpy()
    out["is_envelope_broken"] = ((h < np.fmax(o, c)) | (l > np.fmin(o, c))).fillna(False).to_numpy()
    out["is_zero_range"] = ((h == l) & (o == c)).fillna(False).to_numpy()
    log.record("flag_invalid_ohlc", n0, len(out),
               f"nan={int(out['is_nan_ohlc'].sum())}, nonpos={int(out['is_nonpositive'].sum())}, "
               f"h<l={int(out['is_high_below_low'].sum())}, "
               f"envelope={int(out['is_envelope_broken'].sum())}, "
               f"zero_range={int(out['is_zero_range'].sum())}",
               rows_dropped=0)
    return out


def drop_invalid_ohlc(df: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Drop ONLY rows that are unusable: NaN or non-positive prices.

    Envelope violations (high < max(o,c)) are NOT dropped here - they are
    repaired, because the bar still carries real information.
    """
    n0 = len(df)
    if "is_nan_ohlc" not in df.columns:
        df = flag_invalid_ohlc(df, CleaningLog())
    keep = ~(df["is_nan_ohlc"] | df["is_nonpositive"])
    out = df[keep].reset_index(drop=True)
    log.record("drop_invalid_ohlc", n0, len(out),
               "dropped rows with NaN or non-positive OHLC only")
    return out


def repair_ohlc_envelope(df: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Widen high/low so the OHLC envelope holds. Never moves open/close."""
    n0 = len(df)
    out = df.copy()
    o, h, l, c = (pd.to_numeric(out[k], errors="coerce") for k in ("open", "high", "low", "close"))
    new_h = np.fmax(h, np.fmax(o, c))
    new_l = np.fmin(l, np.fmin(o, c))
    n_changed = int(((new_h != h) | (new_l != l)).sum())
    out["high"] = new_h
    out["low"] = new_l
    log.record("repair_ohlc_envelope", n0, len(out),
               f"widened high/low on {n_changed} bar(s); open/close untouched",
               bars_repaired=n_changed)
    return out


def winsorise_returns(df: pd.DataFrame, log: CleaningLog, z_thresh: float = 12.0,
                      valid: pd.Series | None = None) -> pd.DataFrame:
    """FLAG (never rewrite) MAD-z outliers in close-to-close log returns.

    ``valid`` optionally carries ``return_valid`` from the adjust pipeline so
    that returns which jump a data outage are not mistaken for fat tails.
    """
    n0 = len(df)
    lr = np.log(pd.to_numeric(df["close"], errors="coerce")
                / pd.to_numeric(df["close"], errors="coerce").shift(1)).abs()
    if valid is not None:
        lr = lr.where(pd.Series(np.asarray(valid, dtype=bool), index=df.index))
    med = lr.median()
    mad = (lr - med).abs().median()
    out = df.copy()
    if not np.isfinite(mad) or mad <= 0:
        out["return_mad_z"] = 0.0
        out["return_outlier_flag"] = False
        log.record("winsorise_returns", n0, len(out), "skipped: degenerate MAD",
                   flagged=0)
        return out
    z = 0.6745 * (lr - med) / mad
    out["return_mad_z"] = z.to_numpy()
    out["return_outlier_flag"] = (z.abs() > z_thresh).fillna(False).to_numpy()
    log.record("winsorise_returns", n0, len(out),
               f"flagged {int(out['return_outlier_flag'].sum())} bar(s) with "
               f"MAD-z > {z_thresh}; VALUES UNCHANGED",
               flagged=int(out["return_outlier_flag"].sum()))
    return out


def drop_forming_last_bar(df: pd.DataFrame, log: CleaningLog, timeframe: str = "4h",
                          now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Drop a bar whose close time is still in the future (look-ahead guard)."""
    from .resample import timeframe_minutes
    n0 = len(df)
    if n0 == 0:
        log.record("drop_forming_last_bar", n0, 0, "empty frame")
        return df
    step = pd.Timedelta(minutes=timeframe_minutes(timeframe))
    ts = pd.to_datetime(df["timestamp_utc"], utc=True)
    now_ts = now or pd.Timestamp.now(tz=UTC)
    keep = (ts + step) <= now_ts
    out = df[keep].reset_index(drop=True)
    log.record("drop_forming_last_bar", n0, len(out),
               f"timeframe={timeframe}, now={now_ts.isoformat()}")
    return out


def clean_pipeline(df: pd.DataFrame, timeframe: str = "4h",
                   now: pd.Timestamp | None = None,
                   z_thresh: float = 12.0) -> Tuple[pd.DataFrame, CleaningLog]:
    """Full, ordered, logged cleaning pass. Returns (frame, log)."""
    log = CleaningLog()
    out = dedupe_and_sort(df, log)
    out = flag_invalid_ohlc(out, log)
    out = drop_invalid_ohlc(out, log)
    out = repair_ohlc_envelope(out, log)
    valid = out["return_valid"] if "return_valid" in out.columns else None
    out = winsorise_returns(out, log, z_thresh=z_thresh, valid=valid)
    out = drop_forming_last_bar(out, log, timeframe, now=now)
    return out, log


__all__ = ["CleaningLog", "dedupe_and_sort", "flag_invalid_ohlc", "drop_invalid_ohlc",
           "repair_ohlc_envelope", "winsorise_returns", "drop_forming_last_bar",
           "clean_pipeline"]
