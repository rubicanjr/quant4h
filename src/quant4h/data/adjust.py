"""Roll-gap and data-outage adjustment (KARAR 2 & KARAR 3).

Hard rules imposed by the user, enforced by this module and by its tests:

1. **NO bar is ever deleted.** ``len(out) == len(df)`` always.
2. **NO bar is ever fabricated.** We do not interpolate, forward-fill or
   synthesise prices. Missing time stays missing; it is only *marked*.
3. The 75-hour outage (``2026-01-30 15:00 -> 2026-02-02 18:00 UTC`` on both
   GC=F and SI=F) is marked **non-tradable**, not repaired.
4. A return that *jumps across* an unexpected gap is NOT a real return. It is
   marked invalid (``return_valid=False``, ``close_to_close_return=NaN``) so it
   can never enter a label, a statistic or a P&L. The SILVER ``-22%`` bar of
   2026-02-02 stays in the data, permanently flagged.
5. Contract rolls are the ONLY thing we price-adjust, and we do it the
   conservative way: raw prices stay untouched and a separate
   ``close_adjusted`` column carries the multiplicative back-adjustment.
6. Every mutation is written to a ``CleaningLog``.

Why rolls and outages must be told apart
----------------------------------------
Both produce a price jump. A roll happens between **time-contiguous** bars
(the front month is swapped while the clock keeps ticking); an outage jump
spans a **hole in the calendar**. Treating an outage jump as a roll would
"correct" a fake move into the price history and invent performance. So the
classification order is: gap anomaly FIRST, roll SECOND.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import AssetSpec, UTC
from .cleaning import CleaningLog
from .resample import timeframe_minutes

# Columns that adjust_asset() itself adds. Everything else in the frame is
# left untouched.
ADDED_COLUMNS: Tuple[str, ...] = (
    "close_raw",              # pristine close, never modified
    "close_adjusted",         # roll back-adjusted close (== close_raw if no roll)
    "adjustment_factor",      # cumulative multiplicative factor applied to the past
    "gap_bars",               # bars of elapsed time since the previous bar
    "modal_gap_bars",         # typical gap for this (weekday, local hour) slot
    "gap_anomaly",            # unexpected calendar hole (outage / long holiday)
    "outage_window",          # a row that exists INSIDE an outage window.
                              # On a coarse grid (4H) this is normally 0 rows:
                              # the missing hours simply have NO bar at all. The
                              # window is still reported in attrs["outage_windows"]
                              # with exact bounds so the hole is auditable.
    "outage_resumption",      # first bar AFTER an outage: level may have jumped
    "non_tradable",           # do not open/close a position on this bar
    "non_tradable_reason",    # machine readable reason ("" if tradable)
    "return_valid",           # close-to-close return is usable
    "close_to_close_return",  # log return, NaN where return_valid is False
    "big_move_candidate",     # contiguous jump > roll_atr_multiple x ATR%
    "roll_candidate",         # same, named for futures; NOT a confirmed roll
    "bad_print_candidate",    # big move AND abnormally low volume (heuristic)
    "persistent_move",        # the move did not retract over N bars
    "roll_event",             # price-corrected (only when apply_roll_correction)
    "atr",                    # ATR(atr_period) in price units, no look-ahead
    "atr_pct",                # ATR / close, in percent
)

# Extra columns added by the EQUITY-only helpers (flag_corporate_actions /
# flag_price_limit_bars). adjust_asset() does NOT produce these, so they are
# deliberately kept out of the ADDED_COLUMNS invariant.
STOCK_COLUMNS: Tuple[str, ...] = (
    "adj_ratio",              # adjclose / close_raw
    "corporate_action_flag",  # adj_ratio stepped -> dividend or split took effect
    "corporate_action_type",  # "split" | "dividend_or_other" | ""
    "halt_or_limit_flag",     # price-limit / circuit-breaker heuristic
)


@dataclass
class AdjustReport:
    asset_key: str
    rows_in: int
    rows_out: int
    bars_deleted: int
    bars_added: int
    outage_windows: List[Dict[str, Any]]
    n_gap_anomaly: int
    n_non_tradable: int
    n_thin_non_tradable: int
    n_return_invalid: int
    n_roll_event: int
    n_roll_candidate: int
    max_valid_abs_return: float
    max_raw_abs_return: float
    silver_minus22_flagged: Optional[bool] = None
    attrs: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items()}
        return d


def flag_corporate_actions(df: pd.DataFrame, tol: float = 1e-3,
                           split_log_return: float = 0.25,
                           mark_following_bars: int = 1) -> pd.DataFrame:
    """FLAG ONLY corporate-action detection (KARAR 5 / Aşama 1.5).

    Yahoo's ``adjclose`` already folds dividends and splits into the price.
    This project treats RAW prices as the source of truth and never applies an
    automatic adjustment, because re-stating history is itself a look-ahead
    risk. So we only DETECT and MARK:

    * ``adj_ratio = adjclose / close_raw`` is piecewise constant; a step change
      means a corporate action took effect on that bar.
    * a step WITH |log return| > ``split_log_return`` is classified ``split``
      (2:1, 3:1, 1:2 ...), otherwise ``dividend_or_other``.
    * the event bar and the next ``mark_following_bars`` bar(s) get
      ``return_valid = False`` and ``non_tradable = True``: a return that
      straddles an ex-date is not a tradable return.

    No price is ever modified. ``close_raw`` and ``adjclose`` are both kept.

    UYARI: bu fonksiyon yalnizca ``adjclose`` GERCEKTEN duzeltilmis olan
    serilerde ise yarar. Yahoo'nun 1h BIST serisinde ``adjclose == close``
    oldugu icin orada HICBIR sey bulamaz; hisse senetleri icin
    ``corporate_actions_from_daily`` + ``flag_corporate_actions_from_dates``
    kullanilmalidir.
    """
    out = df.copy()
    close = pd.to_numeric(out["close_raw"] if "close_raw" in out.columns else out["close"],
                          errors="coerce").astype("float64")
    if "adjclose" not in out.columns or not pd.to_numeric(out["adjclose"], errors="coerce").notna().any():
        out["adj_ratio"] = np.nan
        out["corporate_action_flag"] = False
        out["corporate_action_type"] = ""
        return out
    adj = pd.to_numeric(out["adjclose"], errors="coerce").astype("float64")
    ratio = (adj / close).replace([np.inf, -np.inf], np.nan)
    out["adj_ratio"] = ratio.to_numpy()

    step = (ratio / ratio.shift(1) - 1.0).abs()
    event = (step > tol) & step.notna()
    logret = np.log(close / close.shift(1)).abs()
    is_split = event & (logret > split_log_return)
    out["corporate_action_flag"] = event.to_numpy()
    out["corporate_action_type"] = np.where(is_split, "split",
                                    np.where(event, "dividend_or_other", ""))

    # olay bari + sonraki N bar: getiri gecersiz, islem disi
    mask = event.copy()
    for k in range(1, max(1, mark_following_bars) + 1):
        mask = mask | event.shift(k).fillna(False)
    if "return_valid" in out.columns:
        out["return_valid"] = (out["return_valid"].astype(bool) & ~mask).to_numpy()
        out.loc[mask, "close_to_close_return"] = np.nan
    else:
        out["return_valid"] = (~mask).to_numpy()
    if "non_tradable" in out.columns:
        reason = out["non_tradable_reason"].astype(str).where(
            out["non_tradable_reason"].astype(str) != "", "")
        out["non_tradable"] = (out["non_tradable"].astype(bool) | mask).to_numpy()
        out["non_tradable_reason"] = np.where(
            mask & (reason == ""), "corporate_action",
            np.where(mask, reason + "+corporate_action", reason))
    else:
        out["non_tradable"] = mask.to_numpy()
        out["non_tradable_reason"] = np.where(mask, "corporate_action", "")
    out.attrs["corporate_action_bars"] = n_event
    out.attrs["corporate_action_splits"] = int(is_split.sum())
    return out


def corporate_actions_from_daily(daily: pd.DataFrame, tol: float = 1e-3) -> pd.DataFrame:
    """Extract corporate-action EVENT DATES from a DAILY Yahoo frame.

    NEDEN GÜNLÜK SERİ (kritik bulgu, 2026-09-16):
    Yahoo'nun **1h** BIST serisinde ``adjclose == close`` (ölçüldü: %100).
    Yani intraday seri kurumsal aksiyon düzeltmesi İÇERMİYOR; ``adj_ratio``
    üzerinden tespit orada ÇALIŞMAZ ve bir bölünme intraday seride SAHTE bir
    fiyat sıçraması olarak görünür. Günlük seride ise ``adjclose/close`` oranı
    her temettü/bölünme ex-date'inde adım değiştirir (AKBNK 21, ISCTR 17,
    GUBRF 6, SASA 2 adım). Bu yüzden tespit GÜNLÜK seriden yapılır ve
    tarihler 4H barlara TAŞINIR.
    """
    out = pd.DataFrame({
        # pd.DatetimeIndex(datetime64[us, UTC]) tz bilgisini SESSIZCE dusurur;
        # pd.to_datetime(..., utc=True) ile tz-aware tutulmali (aksi halde
        # asagidaki isin() karsilastirmasi hep False doner).
        "date": pd.DatetimeIndex(pd.to_datetime(daily["timestamp_utc"], utc=True)).normalize(),
        "close": pd.to_numeric(daily["close"], errors="coerce").to_numpy(),
    })
    if "adjclose" in daily.columns:
        out["adjclose"] = pd.to_numeric(daily["adjclose"], errors="coerce").to_numpy()
    else:
        out["adjclose"] = out["close"]
    out = out.dropna(subset=["close", "adjclose"]).sort_values("date").reset_index(drop=True)
    out["adj_ratio"] = out["adjclose"] / out["close"]
    step = (out["adj_ratio"] / out["adj_ratio"].shift(1) - 1.0).abs()
    out["log_return"] = np.log(out["close"] / out["close"].shift(1))
    out["is_event"] = (step > tol) & step.notna()
    out["event_type"] = np.where(out["is_event"] & (out["log_return"].abs() > 0.25), "split",
                         np.where(out["is_event"], "dividend_or_other", ""))
    out["ratio_step"] = step
    return out[out["is_event"]].reset_index(drop=True)


def flag_corporate_actions_from_dates(df: pd.DataFrame, event_dates,
                                      mark_following_bars: int = 1,
                                      event_types: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """Mark 4H bars whose SESSION DATE is a corporate-action ex-date.

    FLAG ONLY: no price is written, no bar is deleted. The event bar and the
    next ``mark_following_bars`` bar(s) get ``return_valid=False`` and
    ``non_tradable=True`` because a return that straddles an ex-date is not a
    tradable return.
    """
    out = df.copy()
    dates = set(pd.DatetimeIndex(pd.to_datetime(list(event_dates), utc=True)).normalize())
    if "session_date" in out.columns:
        sess = pd.DatetimeIndex(
            pd.to_datetime(out["session_date"].astype(str), utc=True)).normalize()
    else:
        sess = pd.DatetimeIndex(
            pd.to_datetime(out["timestamp_utc"], utc=True)).tz_convert(UTC).normalize()
    # tz-aware <-> naive karsilastirmasi sessizce False uretir; bu yuzden iki
    # taraf da ayni tz'e zorlanir ve sonuc SAYI ile dogrulanir.
    event = pd.Series(sess.isin(dates), index=out.index)
    n_event = int(event.sum())
    mask = event.copy()
    for k in range(1, max(1, mark_following_bars) + 1):
        mask = mask | event.shift(k).fillna(False)
    if len(dates) and n_event == 0:
        # Sessiz basarisizlik olmasin diye AYRIM yap: ex-date'ler 4H penceresinin
        # DISINDA ise bu NORMALDIR (gunluk seri 25 yil, intraday seri 2.9 yil).
        # Pencere ICINDE tarih var ama eslesme yoksa o zaman gercek bir
        # tarih/tz uyusmazligi suphesi dogar.
        lo = sess.min() if len(sess) else None
        hi = sess.max() if len(sess) else None
        inside = [d for d in dates if lo is not None and lo <= d <= hi]
        if inside:
            out.attrs["corporate_action_warning"] = (
                f"{len(inside)} ex-date 4H penceresi ICINDE ({lo.date()}..{hi.date()}) "
                f"ama HICBIR bar eslesmedi -> tarih/tz uyusmazligi SUPHELI, "
                f"bayraklar bos birakildi. INCELENMELI.")
        else:
            out.attrs["corporate_action_note"] = (
                f"{len(dates)} ex-date bulundu ama TAMAMI 4H penceresi "
                f"({lo.date() if lo is not None else '?'}..{hi.date() if hi is not None else '?'}) "
                f"DISINDA (en yakin {min(dates).date()}). Bu NORMALDIR: gunluk seri "
                f"~25 yil, intraday seri ~2.9 yil. Bu pencerede kurumsal aksiyon YOK.")
    out["corporate_action_flag"] = event.to_numpy()
    if event_types:
        tmap = {pd.DatetimeIndex(pd.to_datetime([k], utc=True)).normalize()[0]: v
                for k, v in event_types.items()}
        out["corporate_action_type"] = [tmap.get(d, "") for d in sess]
    else:
        out["corporate_action_type"] = np.where(event, "dividend_or_other", "")
    if "adj_ratio" not in out.columns:
        out["adj_ratio"] = np.nan
    if "return_valid" in out.columns:
        out["return_valid"] = (out["return_valid"].astype(bool) & ~mask).to_numpy()
        out.loc[mask, "close_to_close_return"] = np.nan
    else:
        out["return_valid"] = (~mask).to_numpy()
    reason = out["non_tradable_reason"].astype(str) if "non_tradable_reason" in out.columns \
        else pd.Series("", index=out.index)
    if "non_tradable" in out.columns:
        out["non_tradable"] = (out["non_tradable"].astype(bool) | mask).to_numpy()
    else:
        out["non_tradable"] = mask.to_numpy()
    out["non_tradable_reason"] = np.where(mask & (reason == ""), "corporate_action",
                                  np.where(mask, reason + "+corporate_action", reason))
    out.attrs["corporate_action_bars"] = n_event
    out.attrs["corporate_action_marked_bars"] = int(mask.sum())
    out.attrs["corporate_action_events"] = len(dates)
    out.attrs["corporate_action_source"] = "daily adjclose/close ratio step"
    return out


def flag_price_limit_bars(df: pd.DataFrame, zero_range_is_limit: bool = True,
                          range_threshold_frac: float = 0.095) -> pd.DataFrame:
    """Heuristic flag for BIST price-limit / circuit-breaker bars.

    DURUST SINIR: gerçek bir "halt" ancak resmî seans verisiyle kesinleşir.
    Burada yalnızca İKİ sezgi kullanılır ve ikisi de sadece İŞARETLER:

    * ``zero_range_is_limit``: high == low olan bar (tek fiyattan geçmiş,
      tipik olarak marja yapışmış ya da devre kesicide donmuş).
    * bar aralığı ``(high-low)/open >= range_threshold_frac``: BIST günlük fiyat
      marjı ±%10 olduğu için ~%9.5 üstü bir TEK BAR aralığı marja koşmayı
      düşündürür.

    Bu bayraklar barı SİLMEZ ve getirisini geçersiz SAYMAZ; yalnızca "burada
    gerçekçi execution varsayma" uyarısıdır.
    """
    out = df.copy()
    o = pd.to_numeric(out["open"], errors="coerce")
    h = pd.to_numeric(out["high"], errors="coerce")
    l = pd.to_numeric(out["low"], errors="coerce")
    zero_range = (h == l) if zero_range_is_limit else pd.Series(False, index=out.index)
    wide = ((h - l) / o.replace(0, np.nan)) >= range_threshold_frac
    flag = (zero_range | wide.fillna(False)).fillna(False)
    out["halt_or_limit_flag"] = flag.to_numpy()
    out.attrs["halt_or_limit_bars"] = int(flag.sum())
    out.attrs["halt_zero_range_bars"] = int(zero_range.fillna(False).sum())
    return out


def _wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Wilder-smoothed ATR. Uses only past bars (shift(1)), so no look-ahead."""
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1)
    tr = tr.max(axis=1)
    # Wilder == EMA with alpha = 1/period
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _slot_modal_gap(ts: pd.Series, tz: str, step: pd.Timedelta) -> pd.Series:
    """Typical (modal) gap per (weekday, local hour) slot.

    Sessions make the naive "gap == 1 bar" assumption wrong: for BIST30 the
    first bar of every day is legitimately 4 bars away from the previous close.
    Using the modal gap per slot is what keeps normal overnight/weekend jumps
    from being reported as data outages (bug H6).
    """
    gap = (ts.diff() / step)
    local = ts.dt.tz_convert(tz)
    slot = pd.Series(list(zip(local.dt.dayofweek.to_numpy(), local.dt.hour.to_numpy())),
                     index=ts.index)
    modal = gap.groupby(slot).transform(lambda g: g.mode().iloc[0] if not g.mode().empty else 1.0)
    return modal.fillna(1.0)


def adjust_asset(df: pd.DataFrame, spec: AssetSpec, timeframe: str = "4h",
                 atr_period: int = 14, roll_atr_multiple: float = 3.0,
                 gap_tolerance_bars: float = 4.0,
                 roll_persistence_bars: int = 6, roll_persistence_frac: float = 0.5,
                 volume_median_window: int = 120, volume_bad_print_frac: float = 0.5,
                 apply_roll_correction: bool = False,
                 thin_src_ratio: float = 0.5, src_timeframe: str = "1h",
                 now: Optional[pd.Timestamp] = None) -> Tuple[pd.DataFrame, AdjustReport, CleaningLog]:
    """Mark outages, invalidate gap-jumping returns, back-adjust rolls.

    Returns ``(adjusted_frame, report, cleaning_log)``. The frame has the same
    number of rows as the input plus the ``ADDED_COLUMNS``.
    """
    log = CleaningLog()
    n0 = len(df)
    if n0 == 0:
        raise ValueError("adjust_asset: empty frame")

    out = df.copy()
    ts = pd.to_datetime(out["timestamp_utc"], utc=True).sort_values()
    if not ts.equals(pd.to_datetime(out["timestamp_utc"], utc=True)):
        out = out.sort_values("timestamp_utc").reset_index(drop=True)
        ts = pd.to_datetime(out["timestamp_utc"], utc=True)
    log.record("sort_and_index_reset", n0, len(out), "no row dropped")

    tf_min = timeframe_minutes(timeframe)
    step = pd.Timedelta(minutes=tf_min)
    close = pd.to_numeric(out["close"], errors="coerce").astype("float64")
    high = pd.to_numeric(out["high"], errors="coerce").astype("float64")
    low = pd.to_numeric(out["low"], errors="coerce").astype("float64")

    out["close_raw"] = close.to_numpy()

    # ---- 1. calendar gaps ------------------------------------------------
    gap_bars = (ts.diff() / step)
    modal = _slot_modal_gap(ts, spec.native_session_tz, step)
    gap_anomaly = (gap_bars > modal + gap_tolerance_bars).fillna(False)
    out["gap_bars"] = gap_bars.to_numpy()
    out["modal_gap_bars"] = modal.to_numpy()
    out["gap_anomaly"] = gap_anomaly.to_numpy()
    log.record("gap_classification", len(out), len(out),
               f"{int(gap_anomaly.sum())} anomalous gaps "
               f"(rule: gap > modal_gap(weekday,local_hour) + {gap_tolerance_bars})")

    # ---- 2. outage windows ----------------------------------------------
    # A window spans from the first bar after the previous real bar until the
    # last bar before the next real bar. Nothing inside it is tradable, and the
    # window itself is reported so a human can see exactly what is missing.
    anomaly_pos = np.flatnonzero(gap_anomaly.to_numpy())
    outage = np.zeros(len(out), dtype=bool)
    windows: List[Dict[str, Any]] = []
    ts_np = ts.to_numpy()
    for pos in anomaly_pos:
        prev_pos = pos - 1
        if prev_pos < 0:
            continue
        window_start = ts_np[prev_pos] + np.timedelta64(tf_min, "m")
        window_end = ts_np[pos] - np.timedelta64(tf_min, "m")
        inside = (ts_np >= window_start) & (ts_np <= window_end)
        outage |= inside          # 4H gridde genelde 0 satir: eksik bar zaten yok
        windows.append({
            "prev_bar_utc": str(pd.Timestamp(ts_np[prev_pos])),
            "resumed_bar_utc": str(pd.Timestamp(ts_np[pos])),
            "missing_from_utc": str(pd.Timestamp(window_start)),
            "missing_to_utc": str(pd.Timestamp(window_end)),
            "missing_hours": float((pd.Timestamp(ts_np[pos]) - pd.Timestamp(ts_np[prev_pos]))
                                   / pd.Timedelta(hours=1)),
            "gap_bars": float(gap_bars.iloc[pos]),
            "modal_gap_bars": float(modal.iloc[pos]),
            "bars_inside_window_marked": int(inside.sum()),
            "note": ("eksik saatlerin bari ZATEN YOK; bu pencere takvimde bosluk olarak "
                     "raporlanir, satir olarak degil"),
            "return_across_gap_pct": float(np.log(close.iloc[pos] / close.iloc[prev_pos]) * 100),
        })
    out["outage_window"] = outage
    log.record("outage_marking", len(out), len(out),
               f"{len(windows)} outage window(s) marked; {int(outage.sum())} bar(s) inside windows")

    # ---- 3. thin bars (structural, e.g. BIST30 opening snapshot) --------
    thin = np.zeros(len(out), dtype=bool)
    src_tf = src_timeframe or out.attrs.get("native_timeframe") or "1h"
    if "n_src_bars" in out.columns:
        src_tf_min = timeframe_minutes(str(src_tf))
        expected = tf_min / src_tf_min if src_tf_min else np.nan
        if np.isfinite(expected) and expected > 1:
            n_src = pd.to_numeric(out["n_src_bars"], errors="coerce")
            thin = (n_src < expected * thin_src_ratio).fillna(False).to_numpy()
    out.attrs["thin_bars"] = int(thin.sum())

    # ---- 4. non-tradable marking ----------------------------------------
    now_ts = (now or pd.Timestamp.now(tz=UTC))
    forming = (ts + step) > now_ts
    reasons: List[str] = []
    non_tradable = outage | thin | forming.to_numpy()
    # Kesintiyi takip eden ILK bar da guvenli degildir: fiyat seviyesi atlamis
    # olabilir, ustu bar eksiktir ve (vadeli serilerde) roll burada gerceklesir.
    # Bu yuzden 'outage_resumption' olarak ayrica isaretlenir.
    resumption = gap_anomaly.fillna(False).to_numpy()
    # 'no_volume_data' yalnizca varlik GERCEKTEN trade ediliyorsa bir engeldir.
    # BIST30 su an watch_only oldugu icin hacimsizlik onu non-tradable YAPMAZ;
    # sadece hacim/onay bacagi devre disi kalir (KARAR 1).
    if bool(getattr(spec, "tradable", True)) and not bool(getattr(spec, "has_volume", True)):
        vol_zero = np.ones(len(out), dtype=bool)
    else:
        vol_zero = np.zeros(len(out), dtype=bool)
    for o, r, t, f, vz in zip(outage, resumption, thin, forming.to_numpy(), vol_zero):
        parts = []
        if o:
            parts.append("outage_window")
        if r:
            parts.append("outage_resumption")
        if t:
            parts.append("thin_bar")
        if f:
            parts.append("still_forming")
        if vz:
            parts.append("no_volume_data")
        reasons.append("+".join(parts))
    non_tradable = non_tradable | resumption | vol_zero
    out["outage_resumption"] = resumption
    out["non_tradable"] = non_tradable
    out["non_tradable_reason"] = reasons
    log.record("non_tradable_marking", len(out), len(out),
               f"{int(non_tradable.sum())} non-tradable bars "
               f"(outage_window={int(outage.sum())}, outage_resumption={int(resumption.sum())}, "
               f"thin={int(thin.sum())}, forming={int(forming.sum())}, no_volume={int(vol_zero.sum())})")

    # ---- 5. returns: invalidate anything that jumps a calendar hole -----
    raw_ret = np.log(close / close.shift(1))
    valid = ~(gap_anomaly.fillna(False) | pd.Series(outage, index=out.index).shift(1).fillna(False))
    valid &= close.shift(1).notna() & close.notna()
    valid &= ~pd.Series(non_tradable, index=out.index)
    ret = raw_ret.where(valid)
    out["return_valid"] = valid.to_numpy()
    out["close_to_close_return"] = ret.to_numpy()
    log.record("return_invalidation", len(out), len(out),
               f"{int((~valid).sum())} returns invalidated "
               f"({int(gap_anomaly.fillna(False).sum())} cross an anomalous gap, "
               f"{int(outage.sum())} inside an outage window, "
               f"{int(thin.sum())} thin, {int(forming.sum())} still forming)")

    # ---- 6. ATR on valid bars only --------------------------------------
    atr = _wilder_atr(high, low, close, atr_period)
    out["atr"] = atr.to_numpy()
    out["atr_pct"] = (atr / close * 100.0).to_numpy()

    # ---- 7. buyuk hareket siniflandirmasi (DURUST SINIR) ----------------
    # Yahoo GC=F / SI=F ON-AY serisidir ve feed'de KONTRAT AYI kimligi YOKTUR.
    # Sonuc: bir roll ile (a) gercek bir ekstrem hareket ve (b) tek barlik bir
    # bad print, yalnizca FIYAT verisinden KESIN olarak AYIRT EDILEMEZ.
    #   * Kalicilik testi ise yaramaz: bad print de sonraki barlarda seviyeyi
    #     kaydirmis gorunur (open yeni seviyeden devam eder).
    #   * Gercek bir roll'un fiyati ~%0.1-0.3 oynatir; bu, ATR esiginin COK
    #     altindadir, yani tespit edilemez bile.
    # Bu yuzden sistem HICBIR SEYI otomatik olarak "roll" ilan etmez ve
    # varsayilan politika fiyatlara DOKUNMAZ. Yapilan tek sey: buyuk
    # hareketleri siniflandirip INSAN INCELEMESINE sunmak.
    #
    # Guvenilir ayirt edici: HACIM. Gercek bir hareket hacimle gelir; izole bir
    # bad print genellikle hacimsizdir. Bu bir SEZGIDIR, kanit degil.
    contiguous = (gap_bars <= modal + gap_tolerance_bars).fillna(True)
    atr_pct_prev = (atr / close).shift(1)
    threshold = roll_atr_multiple * atr_pct_prev
    big = ((raw_ret.abs() > threshold) & contiguous & (atr_pct_prev > 0)).fillna(False)
    big &= raw_ret.notna()

    if not bool(getattr(spec, "requires_adjustment", False)):
        # Spot (BTC) ve endeks (XU030) icin roll TANIM GEREGI imkansizdir.
        # Bu yuzden buyuk hareketler yalnizca 'extreme_move' olarak adlandirilir,
        # 'roll' kelimesi hic kullanilmaz. (Onceki surum BTC'de 118 sahte roll
        # uretiyordu - bu bir hataydi.)
        big = pd.Series(False, index=out.index)

    # Kalicilik: hareket sonraki roll_persistence_bars bar boyunca geri
    # DONMUYORSA kalicidir. Bu, roll/bad-print ayrimi DEGILDIR; yalnizca
    # incelemede oncelik siralamasi icin ek bir nottur.
    persisted = pd.Series(False, index=out.index)
    c = close.to_numpy()
    for pos in np.flatnonzero(big.to_numpy()):
        ahead = pos + roll_persistence_bars
        if ahead >= len(c) or pos < 1:
            continue
        move = abs(float(np.log(c[pos] / c[pos - 1])))
        retrace = abs(float(np.log(c[ahead] / c[pos - 1])))
        persisted.iloc[pos] = bool(retrace > move * roll_persistence_frac)

    # Hacim sezgisi: bar hacmi, kendi penceresinin medyaninin altindaysa
    # 'izole print' olasiligi yuksektir.
    vol = pd.to_numeric(out["volume"], errors="coerce").fillna(0.0)
    vol_med = vol.rolling(volume_median_window, min_periods=5).median()
    low_volume = (vol < volume_bad_print_frac * vol_med).fillna(False)

    out["big_move_candidate"] = big.to_numpy()
    out["roll_candidate"] = big.to_numpy()          # vadi serilerde anlamli isim
    out["bad_print_candidate"] = (big & low_volume).to_numpy()
    out["persistent_move"] = persisted.to_numpy()
    out["roll_event"] = (big & apply_roll_correction).to_numpy()
    log.record("big_move_classification", len(out), len(out),
               f"{int(big.sum())} big contiguous move(s) > {roll_atr_multiple} x ATR%({atr_period}); "
               f"{int(out['persistent_move'].sum())} persistent, "
               f"{int(out['bad_print_candidate'].sum())} low-volume (bad print sezgisi); "
               f"{int(out['roll_event'].sum())} price-corrected "
               f"(apply_roll_correction={apply_roll_correction}; "
               f"requires_adjustment={bool(getattr(spec, 'requires_adjustment', False))})")

    # ---- 8. multiplicative back-adjustment (yalnizca acik opt-in) -------
    # Semantik: roll p pozisyonundaysa, p ONCESI tum barlar ratio_p = c_p/c_{p-1}
    # ile carpilir. Boylece p-1 -> p arasindaki yapay siracrama kaybolur ve
    # EN YENI fiyatlar ham degerlerinde kalir (ileriye dokunulmaz).
    # Saf numpy: pandas index hizalamasindan kaynaklanan off-by-one riski yok.
    applied = out["roll_event"].to_numpy(dtype=bool)
    c_np = close.to_numpy(dtype="float64")
    ratio_np = np.ones(len(out), dtype="float64")
    if applied.any() and len(out) > 1:
        r = c_np[1:] / c_np[:-1]
        r = np.where(np.isfinite(r) & (r > 0), r, 1.0)
        # HATA KAYDI: onceki surum 'ratio_np[1:] = r' ile TUM getirileri yaziyordu;
        # bu durumda factor her barda degisiyor ve seri anlamsiz sekilde surukleniyordu.
        # Dogrusu: oran YALNIZCA roll pozisyonlarina yazilir, digerleri 1.0 kalir.
        ratio_np[1:][applied[1:]] = r[applied[1:]]
    # factor[t] = t SONRASINDAKI tum roll oranlarinin carpimi
    rev_cum = np.cumprod(ratio_np[::-1])[::-1]
    factor_np = np.empty(len(out), dtype="float64")
    factor_np[:-1] = rev_cum[1:]
    factor_np[-1] = 1.0
    factor_np[~np.isfinite(factor_np) | (factor_np <= 0)] = 1.0
    out["adjustment_factor"] = factor_np
    out["close_adjusted"] = c_np * factor_np
    log.record("back_adjustment", len(out), len(out),
               f"close_adjusted = close_raw x factor[t] (= t sonrasi roll oranlarinin carpimi); "
               f"factor range [{float(factor_np.min()):.6f}, {float(factor_np.max()):.6f}]; "
               f"applied={bool(applied.any())}")

    # ---- 9. invariants --------------------------------------------------
    assert len(out) == n0, "adjust_asset must never change the row count"
    assert np.allclose(pd.to_numeric(out["close_raw"], errors="coerce").to_numpy(),
                       close.to_numpy(), equal_nan=True), "close_raw must be pristine"
    assert set(ADDED_COLUMNS) <= set(out.columns)

    out.attrs.update({
        "roll_adjusted": True,
        "roll_adjustment_method": (
            f"outage = gap > modal_gap(weekday,local_hour) + {gap_tolerance_bars} bars -> "
            f"non_tradable; gap-jumping returns -> return_valid=False; "
            f"roll candidate = contiguous AND |log ret| > {roll_atr_multiple} x ATR%({atr_period}) "
            f"AND persistent over {roll_persistence_bars} bars; "
            f"apply_roll_correction={apply_roll_correction} "
            f"({'back-adjusted close_adjusted' if apply_roll_correction else 'FLAGGED ONLY, prices untouched'}); "
            f"raw prices always preserved in close_raw"),
        "roll_correction_applied": bool(apply_roll_correction),
        "roll_flagged_bars": int(big.sum()),
        "bad_print_flagged_bars": int(out["bad_print_candidate"].sum()),
        "roll_detectable": bool(getattr(spec, "requires_adjustment", False)),
        "outage_windows": windows,
        "non_tradable_bars": int(non_tradable.sum()),
        "outage_marked": True,
        "outage_window_bars": int(outage.sum()),
        "outage_resumption_bars": int(resumption.sum()),
        "return_invalid_bars": int((~valid).sum()),
        "rows_in": n0,
        "rows_out": len(out),
        "bars_deleted": 0,
        "bars_added": 0,
    })

    report = AdjustReport(
        asset_key=spec.key, rows_in=n0, rows_out=len(out), bars_deleted=0, bars_added=0,
        outage_windows=windows, n_gap_anomaly=int(gap_anomaly.sum()),
        n_non_tradable=int(non_tradable.sum()), n_thin_non_tradable=int(thin.sum()),
        n_return_invalid=int((~valid).sum()),
        n_roll_event=int(out["roll_event"].sum()),
        n_roll_candidate=int(big.sum()),
        max_valid_abs_return=float(ret.abs().max()) if ret.notna().any() else 0.0,
        max_raw_abs_return=float(raw_ret.abs().max()) if raw_ret.notna().any() else 0.0,
        attrs=dict(out.attrs),
    )
    return out, report, log


__all__ = ["adjust_asset", "AdjustReport", "ADDED_COLUMNS", "STOCK_COLUMNS",
           "flag_corporate_actions", "flag_corporate_actions_from_dates",
           "corporate_actions_from_daily", "flag_price_limit_bars"]
