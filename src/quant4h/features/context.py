"""AŞAMA 2 — XU030 context filter (KARAR 4, 2026-09-16).

Rule (verbatim from the user decision)
--------------------------------------
BIST30 hisseleri **LONG-ONLY**'dir. Yeni bir long sinyali YALNIZCA
``XU030 4H kapanış > XU030 EMA200`` iken açılabilir. XU030 EMA200
altındayken sepete YENİ SİNYAL AÇILMAZ; **mevcut** pozisyonlar kendi
stoplarıyla yönetilir (zorla kapatma yoktur). Core varlıklar
(BTC / GOLD / SILVER) long+short kalır ve bu filtreye TABİ DEĞİLDİR.

Anti look-ahead contract
------------------------
A stock bar stamped ``T`` opens at ``T`` and can only be acted on at ``T``.
The XU030 bar stamped ``T`` is still FORMING at ``T`` (it closes at ``T+4h``).
Therefore the filter may only use XU030 bars stamped ``<= T - timeframe``,
i.e. bars that have already CLOSED. This module enforces that with an
as-of merge plus an explicit staleness grace window.

Fail-closed
-----------
If the context is unavailable (warm-up of EMA200, a data gap, or the nearest
closed XU030 bar is older than ``max_context_age``), longs are NOT allowed.
"Veri yok" asla "izin var" anlamına gelmez.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import UTC

CONTEXT_COLUMNS = ("ctx_close", "ctx_ema_trend", "ctx_above_ema",
                   "ctx_age_hours", "ctx_reason", "longs_allowed")

REASON_BELOW = "context_below_ema200"
REASON_WARMUP = "context_warmup"
REASON_MISSING = "context_missing"
REASON_STALE = "context_stale"
REASON_OK = "context_ok"


def xu030_signal(index_4h: pd.DataFrame, ema_period: int = 200) -> pd.DataFrame:
    """Build the XU030 context signal series (no lookahead: EMA is causal)."""
    out = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(index_4h["timestamp_utc"], utc=True).to_numpy(),
    })
    close = pd.to_numeric(index_4h["close"], errors="coerce").astype("float64").to_numpy()
    ema = (pd.Series(close).ewm(span=ema_period, adjust=False,
                                min_periods=ema_period).mean()).to_numpy()
    out["ctx_close"] = close
    out["ctx_ema_trend"] = ema
    # EMA hazir degilse (isinma) sinyal BELIRSIZDIR -> NaN, False degil.
    with np.errstate(invalid="ignore"):
        above = np.where(np.isnan(ema) | np.isnan(close), np.nan, (close > ema).astype(float))
    out["ctx_above_ema"] = above
    out["ctx_ready"] = ~np.isnan(ema)
    out = out.sort_values("timestamp_utc").reset_index(drop=True)
    # pandas merge_asof iki tarafta AYNI datetime cozunurlugunu ister; parquet
    # 'us', to_datetime 'ms'/'ns' uretebiliyor ve bu MergeError verir (H23).
    out["timestamp_utc"] = out["timestamp_utc"].astype("datetime64[ns, UTC]")
    return out


def longs_allowed(stock_4h: pd.DataFrame, index_4h: pd.DataFrame,
                  timeframe: str = "4h", ema_period: int = 200,
                  max_context_age: Optional[pd.Timedelta] = None,
                  long_only: bool = True) -> pd.DataFrame:
    """Attach the XU030 long-permission columns to a stock 4H frame.

    ``long_only=False`` (core assets) makes ``longs_allowed`` all-True: the
    context filter does not apply to BTC / GOLD / SILVER.
    """
    from .regime import REGIME_COLUMNS  # noqa: F401  (dokümantasyon bağı)
    tf = pd.Timedelta(timeframe) if timeframe.endswith("h") \
        else pd.Timedelta(timeframe)
    # Varsayılan tolerans 120 saat (5 gün): hafta sonu + resmî/dinî tatilleri
    # kapsar. Daha sıkı bir değer (ör. 3 bar) BIST'te kırılgandır çünkü ince
    # 03:00 UTC barının bağlam yaşı ZATEN 12 saattir (XU030'da 23:00 barı yok)
    # ve endekste tek bir eksik bar tüm günü 'stale' yapar.
    grace = max_context_age if max_context_age is not None else pd.Timedelta(hours=120)

    out = stock_4h.copy()
    out["timestamp_utc"] = pd.to_datetime(out["timestamp_utc"], utc=True)
    if not long_only:
        out["ctx_close"] = np.nan
        out["ctx_ema_trend"] = np.nan
        out["ctx_above_ema"] = np.nan
        out["ctx_age_hours"] = np.nan
        out["ctx_reason"] = "context_not_applicable"
        out["longs_allowed"] = True
        return out

    sig = xu030_signal(index_4h, ema_period)
    ts_ns = out["timestamp_utc"].astype("datetime64[ns, UTC]")
    left = pd.DataFrame({"timestamp_utc": ts_ns.to_numpy(),
                         "_decision_time": (ts_ns - tf).to_numpy()}).astype(
        {"_decision_time": "datetime64[ns, UTC]"})
    # as-of merge: karar aninda (bar acilisi - 1 bar) KAPANMIS olan son XU030 bari
    merged = pd.merge_asof(left.sort_values("_decision_time"),
                           sig.sort_values("timestamp_utc"),
                           left_on="_decision_time", right_on="timestamp_utc",
                           direction="backward", suffixes=("", "_ctx"))
    merged = merged.sort_values("timestamp_utc").reset_index(drop=True)

    ctx_ts = pd.to_datetime(merged["timestamp_utc_ctx"], utc=True)
    age = (merged["_decision_time"] - ctx_ts) / pd.Timedelta(hours=1)

    reason = np.full(len(merged), REASON_OK, dtype=object)
    ready = merged["ctx_ready"].fillna(False).to_numpy(dtype=bool)
    above = pd.to_numeric(merged["ctx_above_ema"], errors="coerce").to_numpy(dtype=float)
    missing = ctx_ts.isna().to_numpy()
    stale = (~missing) & (age.to_numpy() > grace / pd.Timedelta(hours=1))
    warm = (~missing) & (~stale) & (~ready)
    below = (~missing) & (~stale) & ready & (np.nan_to_num(above, nan=0.0) <= 0.0)

    reason[missing] = REASON_MISSING
    reason[stale] = REASON_STALE
    reason[warm] = REASON_WARMUP
    reason[below] = REASON_BELOW

    allowed = (reason == REASON_OK)
    out["ctx_close"] = merged["ctx_close"].to_numpy()
    out["ctx_ema_trend"] = merged["ctx_ema_trend"].to_numpy()
    out["ctx_above_ema"] = merged["ctx_above_ema"].to_numpy()
    out["ctx_age_hours"] = age.to_numpy()
    out["ctx_reason"] = reason
    out["longs_allowed"] = allowed
    out.attrs["context_filter"] = {
        "index": str(index_4h["symbol"].iloc[0]) if len(index_4h) and "symbol" in index_4h else "XU030",
        "ema_period": ema_period, "timeframe": timeframe,
        "max_context_age": str(grace), "long_only": True, "fail_closed": True,
        "rule": "yeni long yalnızca XU030 4H kapanış > EMA200 iken; mevcut pozisyonlar "
                "kendi stoplarıyla yönetilir (zorla kapatma YOK)",
    }
    return out


def context_summary(df: pd.DataFrame) -> Dict[str, Any]:
    if "ctx_reason" not in df.columns:
        return {"applied": False}
    vc = df["ctx_reason"].astype(str).value_counts()
    n = len(df)
    return {
        "applied": True,
        "bars": n,
        "longs_allowed_bars": int(df["longs_allowed"].sum()),
        "longs_allowed_frac": round(float(df["longs_allowed"].mean()), 4) if n else 0.0,
        "reasons": {str(k): int(v) for k, v in vc.items()},
        "reasons_pct": {str(k): round(float(v) / n * 100, 2) for k, v in vc.items()} if n else {},
        "median_context_age_hours": float(pd.to_numeric(df["ctx_age_hours"],
                                                        errors="coerce").median()),
        "max_context_age_hours": float(pd.to_numeric(df["ctx_age_hours"],
                                                     errors="coerce").max()),
    }


__all__ = ["xu030_signal", "longs_allowed", "context_summary", "CONTEXT_COLUMNS",
           "REASON_BELOW", "REASON_WARMUP", "REASON_MISSING", "REASON_STALE", "REASON_OK"]
