"""Session-aware OHLCV resampling.

Why this module exists
----------------------
The four assets do NOT share a session calendar, so "the 4H bar" is not a
single unambiguous object:

* **BTCUSDT** - 24/7, UTC. 4H bars at 00/04/08/12/16/20 UTC. Unambiguous.
* **GC=F / SI=F** - ~23h/day, Sun 18:00 -> Fri 17:00 America/New_York with a
  daily maintenance halt 17:00-18:00 local. Anchored in UTC so that one grid
  is valid all year (the price is USD and the rest of the book is USD); the
  price of that choice is that one bar per day straddles the halt and is
  built from 3 instead of 4 hourly bars. The QC module flags those bars.
* **XU030.IS** - 09:30-18:00 Europe/Istanbul, 6.5h session. Turkey does not
  observe DST (permanently UTC+3 since 2016), so anchoring the grid in
  *Istanbul local* time at 10:00 gives clean 10-14 / 14-18 / 18-22 bars that
  cover the session with only one thin bar, and the UTC bar times never shift.
  This is why BIST30 uses ``bar_anchor_mode="local"``.

Grid anchor
-----------
``bar_anchor_mode`` decides whether ``bar_anchor_local`` is read in the asset's
session timezone ("local") or in UTC ("utc"). Everything downstream (features,
labels, backtest) consumes UTC bar OPEN times only.

Bar semantics
-------------
``timestamp_utc`` is the bar OPEN time. The bar stamped T covers
[T, T + timeframe) and only becomes *known* at T + timeframe. Signals
computed on that bar are therefore executable at the open of T + timeframe.
The final, still-forming bar is dropped by default (``drop_partial=True``);
that single rule is what prevents the most common look-ahead bug in
hand-rolled pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import AssetSpec, UTC

_TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "2h": 120,
               "4h": 240, "6h": 360, "8h": 480, "12h": 720, "1d": 1440,
               "1w": 10080}

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum"}
_OPTIONAL_AGG = {"quote_volume": "sum", "trades": "sum",
                 "taker_buy_volume": "sum", "open_interest": "last",
                 "funding_rate": "last", "spread": "mean", "adjclose": "last"}


@dataclass
class CalendarInfo:
    asset_key: str
    target_timeframe: str
    anchor_tz: str
    anchor_local: str
    anchor_mode: str
    sessions_total: int
    bars_total: int
    bars_per_session_median: float
    bars_per_session_min: int
    bars_per_session_max: int
    thin_bars: int
    notes: List[str]


def timeframe_minutes(tf: str) -> int:
    if tf not in _TF_MINUTES:
        raise ValueError(f"unsupported timeframe '{tf}' (known: {sorted(_TF_MINUTES)})")
    return _TF_MINUTES[tf]


def _hhmm(text: str) -> tuple[int, int]:
    hh, mm = (int(x) for x in str(text).split(":"))
    return hh, mm


def _origin_utc(spec: AssetSpec) -> pd.Timestamp:
    """Bar-grid origin as a tz-aware UTC timestamp (2000-01-03 is a Monday)."""
    hh, mm = _hhmm(spec.bar_anchor_local)
    base = pd.Timestamp(year=2000, month=1, day=3, hour=hh, minute=mm)
    if spec.bar_anchor_mode == "local":
        return base.tz_localize(spec.native_session_tz,
                                nonexistent="shift_forward").tz_convert(UTC)
    if spec.bar_anchor_mode == "utc":
        return base.tz_localize(UTC)
    raise ValueError(f"bar_anchor_mode must be 'utc' or 'local', got {spec.bar_anchor_mode!r}")


def _origin_index_tz(spec: AssetSpec) -> pd.Timestamp:
    """Origin expressed in the timezone of the index we are about to resample."""
    return _origin_utc(spec).tz_convert(spec.native_session_tz).tz_localize(None)


def session_date(index_local_naive: pd.DatetimeIndex, spec: AssetSpec,
                 timeframe: str = "4h") -> pd.DatetimeIndex:
    """Attribute each bar (given in naive *local* time) to its session date.

    Rule (bug H4, second iteration):

    * ``continuous_24h`` assets (BTC) have no session concept - the session
      date is simply the bar's calendar date.
    * For exchange sessions the roll point is ``session_day_start_local``, a
      MANUAL session-calendar decision that is deliberately decoupled from the
      bar grid anchor. Metals use 17:30 (the 17:00-18:00 NY daily halt belongs
      to the outgoing session), BIST uses 05:00 (nothing trades before 09:30,
      so any early-morning bin is still the same trading day).

    History of this function: v1 rolled at the session open, v2 rolled at the
    grid anchor, both produced wrong bars-per-session counts for at least one
    asset. Decoupling the two concepts fixed it (bug H4).
    """
    idx = pd.DatetimeIndex(pd.to_datetime(index_local_naive))
    day = np.asarray(idx.normalize().to_numpy(), dtype="datetime64[ns]")
    if spec.continuous_24h:
        return pd.DatetimeIndex(day)
    sh, sm = _hhmm(getattr(spec, "session_day_start_local", "00:00"))
    minutes = (np.asarray(idx.hour, dtype="int64") * 60
               + np.asarray(idx.minute, dtype="int64"))
    rolls = minutes < (sh * 60 + sm)
    return pd.DatetimeIndex(np.where(rolls, day - np.timedelta64(1, "D"), day))


def resample_ohlcv(df: pd.DataFrame, target_tf: str, spec: AssetSpec,
                   min_bars_fill: Optional[int] = None, drop_partial: bool = True,
                   now: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """Aggregate a canonical frame to ``target_tf`` on the asset's own grid.

    ``min_bars_fill=None`` (varsayılan) -> ``spec.min_source_bars_per_target``
    kullanılır. Böylece "kaç kaynak bar gerekir" kararı ÇAĞRI YERİNDE değil
    VARLIK TANIMINDA yaşar; tek bir yerde değişir ve tutarsızlık olamaz.
    """
    from . import schema

    if df.empty:
        return schema.empty_frame()
    if min_bars_fill is None:
        min_bars_fill = int(getattr(spec, "min_source_bars_per_target", 1) or 1)
    tf_min = timeframe_minutes(target_tf)
    src_min = _infer_source_minutes(df)
    if src_min is not None and src_min > tf_min:
        raise ValueError(f"cannot resample {src_min}m bars into {tf_min}m bars")

    work = df.copy()
    work["timestamp_utc"] = pd.to_datetime(work["timestamp_utc"], utc=True)
    work = (work.sort_values("timestamp_utc")
                .drop_duplicates("timestamp_utc", keep="first"))

    local_ts = work["timestamp_utc"].dt.tz_convert(spec.native_session_tz).dt.tz_localize(None)
    body = work.drop(columns=["timestamp_utc"]).reset_index(drop=True)
    body.index = local_ts
    body.index.name = None

    agg_map = {k: v for k, v in {**_AGG, **_OPTIONAL_AGG}.items() if k in body.columns}
    grouped = body.resample(f"{tf_min}min", origin=_origin_index_tz(spec),
                            label="left", closed="left")
    out = grouped.agg(agg_map)
    out["n_src_bars"] = grouped["close"].count()
    out["session_date"] = session_date(out.index, spec)

    if min_bars_fill > 1:
        out = out[out["n_src_bars"] >= min_bars_fill]

    now_utc = (now or pd.Timestamp.now(tz=UTC))
    if drop_partial:
        bar_close_utc = (out.index.tz_localize(spec.native_session_tz, nonexistent="shift_forward")
                            .tz_convert(UTC) + pd.Timedelta(minutes=tf_min))
        out = out[bar_close_utc <= now_utc]

    out = out.dropna(subset=[c for c in ("open", "high", "low", "close") if c in out.columns])
    if "volume" not in out.columns:
        out["volume"] = 0.0
    out["volume"] = out["volume"].fillna(0.0)

    # ---- DST artifacts ---------------------------------------------------
    # Lokal-naive grid, DST gecislerinde gercekte HIC VAR OLMAYAN bir saat
    # uretir (orn. 2025-03-09 02:00 America/New_York). Boyle bir bin'de gercek
    # islem olamaz; shift_forward onu bir sonraki gecerli saate tasir ve bu da
    # AYNI UTC damgasina sahip ikinci bir bar yaratir. Iki adim:
    #   1) localize et, 2) UTC'ye cevir, 3) tekrarlanan UTC damgalarini dusur.
    utc_index = (out.index.tz_localize(spec.native_session_tz, ambiguous="NaT",
                                       nonexistent="shift_forward")
                    .tz_convert(UTC))
    n_before = len(out)
    out = out.assign(timestamp_utc=utc_index)
    out = out.drop_duplicates("timestamp_utc", keep="first")
    n_dst_dropped = n_before - len(out)
    if n_dst_dropped:
        out.attrs["dst_artifact_bars_dropped"] = n_dst_dropped
    out = out.sort_values("timestamp_utc").reset_index(drop=True)
    out["symbol"] = str(df["symbol"].iloc[0])
    out["session_date"] = pd.to_datetime(out["session_date"]).dt.strftime("%Y-%m-%d")
    res = schema.coerce(out)
    res.attrs["dst_artifact_bars_dropped"] = int(n_dst_dropped)
    res.attrs["native_timeframe"] = f"{src_min}m" if src_min else None
    return res


def _infer_source_minutes(df: pd.DataFrame) -> Optional[int]:
    ts = pd.to_datetime(df["timestamp_utc"], utc=True).sort_values()
    if len(ts) < 3:
        return None
    diffs = ts.diff().dropna().dt.total_seconds() / 60.0
    diffs = diffs[diffs > 0]
    if diffs.empty:
        return None
    mode = diffs.mode()
    return int(round(float(mode.iloc[0]))) if len(mode) else int(round(float(diffs.median())))


def expected_src_bars(spec: AssetSpec, src_tf: str, target_tf: str) -> float:
    return timeframe_minutes(target_tf) / max(1, timeframe_minutes(src_tf))


def calendar_info(df: pd.DataFrame, spec: AssetSpec, target_tf: str,
                  src_tf: Optional[str] = None) -> CalendarInfo:
    """Descriptive statistics about the produced bar grid (used by the QC report)."""
    notes: List[str] = []
    if df.empty:
        return CalendarInfo(spec.key, target_tf, spec.native_session_tz,
                            spec.bar_anchor_local, spec.bar_anchor_mode,
                            0, 0, 0.0, 0, 0, 0, ["empty frame"])
    ts = pd.to_datetime(df["timestamp_utc"], utc=True)
    local = ts.dt.tz_convert(spec.native_session_tz).dt.tz_localize(None)
    if "session_date" in df.columns:
        sess = pd.to_datetime(df["session_date"].astype(str))
    else:
        sess = pd.Series(session_date(pd.DatetimeIndex(local), spec, target_tf), index=df.index)
    per = (pd.Series(1, index=pd.DatetimeIndex(pd.to_datetime(np.asarray(sess, dtype="datetime64[ns]"))))
             .groupby(level=0).sum())
    thin = 0
    if src_tf:
        ratio = expected_src_bars(spec, src_tf, target_tf)
        if "n_src_bars" in df.columns:
            n_src = pd.to_numeric(df["n_src_bars"], errors="coerce")
            thin = int((n_src < ratio * 0.75).sum())
            notes.append(f"{thin} bars built from <75% of the expected {ratio:.0f} source bars")
        else:
            notes.append("n_src_bars column absent: thin-bar detection unavailable")
    notes.append(f"grid anchored {spec.bar_anchor_local} in mode '{spec.bar_anchor_mode}' "
                 f"({spec.native_session_tz})")
    distinct_hours = sorted(set(int(x) for x in ts.dt.hour.unique()))
    notes.append(f"distinct UTC hours used: {distinct_hours}")
    return CalendarInfo(
        asset_key=spec.key, target_timeframe=target_tf,
        anchor_tz=spec.native_session_tz, anchor_local=spec.bar_anchor_local,
        anchor_mode=spec.bar_anchor_mode, sessions_total=int(len(per)),
        bars_total=int(len(df)), bars_per_session_median=float(per.median()),
        bars_per_session_min=int(per.min()), bars_per_session_max=int(per.max()),
        thin_bars=thin, notes=notes,
    )


__all__ = ["resample_ohlcv", "calendar_info", "CalendarInfo", "timeframe_minutes",
           "session_date", "expected_src_bars", "_origin_utc", "_origin_index_tz"]
