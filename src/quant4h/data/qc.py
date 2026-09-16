"""Data quality control (Phase 1).

This module never *fixes* data silently. It produces a machine readable
report (JSON), a human readable report (markdown), a findings table (CSV)
and a verdict per asset. Cleaning is a separate, explicit, logged step in
``cleaning.py`` so that every mutation of raw data is auditable.

Severity levels
---------------
ERROR   blocks modelling. The dataset must not be used until resolved.
WARN    usable, but the limitation must appear in every downstream report.
INFO    descriptive.

Check families
--------------
1. schema / dtype / canonical columns
2. timestamps: UTC awareness, monotonicity, duplicates, grid alignment
3. missing bars vs the expected session calendar (24/7 vs exchange session)
4. OHLC integrity: high/low envelope, non-positive prices, stale bars
5. price continuity: MAD outlier detection on log returns and bar ranges
6. volume: all-zero detection, zero-volume ratio, negative volume,
   volume/range consistency, volume autocorrelation (session artefacts)
7. optional columns: NaN ratio
8. resampled-data audit: source coverage per target bar, envelope
   consistency between the native and the resampled frame
9. freshness: last complete bar age (partial-bar / look-ahead guard)
10. cross-asset overlap window (needed for portfolio and correlation limits)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import AssetSpec, CANONICAL_COLUMNS, OPTIONAL_COLUMNS, UTC
from . import schema
from .resample import timeframe_minutes

SEVERITIES = ("ERROR", "WARN", "INFO")


@dataclass
class Finding:
    check: str
    severity: str
    message: str
    metric: Optional[float] = None
    examples: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"check": self.check, "severity": self.severity,
                "message": self.message, "metric": self.metric,
                "examples": (self.examples or [])[:10]}


@dataclass
class AssetQCReport:
    asset_key: str
    symbol: str
    timeframe: str
    rows: int
    first_ts: Optional[str]
    last_ts: Optional[str]
    findings: List[Finding] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    verdict: str = "UNKNOWN"
    usable_for_modelling: bool = False
    enough_history: bool = False
    mode: str = "core"
    blockers: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    @property
    def n_error(self) -> int:
        return sum(1 for f in self.findings if f.severity == "ERROR")

    @property
    def n_warn(self) -> int:
        return sum(1 for f in self.findings if f.severity == "WARN")

    def add(self, check: str, severity: str, message: str,
            metric: Optional[float] = None,
            examples: Optional[Sequence[Any]] = None) -> None:
        ex = [str(e) for e in examples] if examples is not None else None
        self.findings.append(Finding(check, severity, message, metric, ex))

    def finalise(self, min_rows: int) -> None:
        self.blockers = [f.message for f in self.findings if f.severity == "ERROR"]
        self.caveats = [f.message for f in self.findings if f.severity == "WARN"]
        self.enough_history = bool(self.rows >= min_rows)
        self.usable_for_modelling = bool(not self.blockers and self.enough_history)
        if self.blockers:
            self.verdict = "RED"
        elif not self.enough_history:
            self.verdict = "AMBER (insufficient history)"
        elif self.caveats:
            self.verdict = "AMBER"
        else:
            self.verdict = "GREEN"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_key": self.asset_key, "symbol": self.symbol,
            "timeframe": self.timeframe, "rows": self.rows,
            "first_ts": self.first_ts, "last_ts": self.last_ts,
            "verdict": self.verdict,
            "usable_for_modelling": self.usable_for_modelling,
            "enough_history": self.enough_history,
            "mode": self.stats.get("mode", "core"),
            "n_error": self.n_error, "n_warn": self.n_warn,
            "blockers": self.blockers, "caveats": self.caveats,
            "stats": self.stats,
            "findings": [f.to_dict() for f in self.findings],
        }


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _mad_outliers(x: pd.Series, thresh: float = 8.0) -> pd.Series:
    """Median-absolute-deviation outlier mask (robust to fat tails)."""
    x = pd.to_numeric(x, errors="coerce")
    med = x.median()
    mad = (x - med).abs().median()
    if not np.isfinite(mad) or mad <= 0:
        return pd.Series(False, index=x.index)
    z = 0.6745 * (x - med) / mad
    return z.abs() > thresh


def _ts_str(ts: Any) -> Optional[str]:
    if ts is None or (isinstance(ts, float) and not np.isfinite(ts)):
        return None
    return pd.Timestamp(ts).tz_convert(UTC).isoformat() if getattr(pd.Timestamp(ts), "tz", None) else pd.Timestamp(ts).isoformat()


# --------------------------------------------------------------------------
# The check battery
# --------------------------------------------------------------------------

def qc_asset(df: pd.DataFrame, spec: AssetSpec, timeframe: str = "4h",
             source_df: Optional[pd.DataFrame] = None,
             min_rows: int = 1500,
             return_thresh: float = 0.20,
             zero_volume_warn_frac: float = 0.10,
             missing_bar_warn_frac: float = 0.02,
             missing_bar_error_frac: float = 0.10) -> AssetQCReport:
    """Run every check on one asset's canonical frame."""
    sym = str(df["symbol"].iloc[0]) if len(df) and "symbol" in df.columns else spec.symbol
    rep = AssetQCReport(asset_key=spec.key, symbol=sym, timeframe=timeframe,
                        rows=int(len(df)),
                        first_ts=_ts_str(df["timestamp_utc"].iloc[0]) if len(df) else None,
                        last_ts=_ts_str(df["timestamp_utc"].iloc[-1]) if len(df) else None)
    if df.empty:
        rep.add("schema", "ERROR", "empty dataset: no rows to validate")
        rep.finalise(min_rows)
        return rep

    ts = pd.to_datetime(df["timestamp_utc"], utc=True)
    tf_min = timeframe_minutes(timeframe)
    step = pd.Timedelta(minutes=tf_min)
    o, h, l, c = (pd.to_numeric(df[k], errors="coerce") for k in ("open", "high", "low", "close"))
    v = pd.to_numeric(df["volume"], errors="coerce")

    # ---- 1. schema -------------------------------------------------------
    missing_cols = [k for k in CANONICAL_COLUMNS if k not in df.columns]
    if missing_cols:
        rep.add("schema", "ERROR", f"missing canonical columns: {missing_cols}")
    else:
        rep.add("schema", "INFO", f"canonical schema OK; optional columns present: "
                                  f"{[k for k in OPTIONAL_COLUMNS if k in df.columns and df[k].notna().any()]}")
    nan_price = int(o.isna().sum() + h.isna().sum() + l.isna().sum() + c.isna().sum())
    if nan_price:
        rep.add("schema", "ERROR", f"{nan_price} NaN values inside OHLC columns",
                metric=float(nan_price))
    if not isinstance(ts.dtype, pd.DatetimeTZDtype) or str(ts.dt.tz) != "UTC":
        rep.add("schema", "ERROR", "timestamp_utc is not timezone-aware UTC")

    # ---- 2. timestamps ---------------------------------------------------
    dups = int(ts.duplicated().sum())
    if dups:
        rep.add("timestamp", "ERROR", f"{dups} duplicated timestamps", metric=float(dups),
                examples=[_ts_str(x) for x in ts[ts.duplicated(keep=False)].unique()[:5]])
    else:
        rep.add("timestamp", "INFO", "no duplicated timestamps")
    non_mono = int((ts.diff().dropna() <= pd.Timedelta(0)).sum())
    if non_mono:
        rep.add("timestamp", "ERROR", f"{non_mono} non-monotonic timestamp steps", metric=float(non_mono))
    else:
        rep.add("timestamp", "INFO", "timestamps strictly increasing")
    # Alignment is evaluated in the timezone the grid is anchored in. With
    # bar_anchor_mode="local" a UTC-based test would flag every single bar.
    origin = _origin_pd(spec)
    if spec.bar_anchor_mode == "local":
        probe = ts.dt.tz_convert(spec.native_session_tz)
        origin_probe = origin.tz_convert(spec.native_session_tz)
    else:
        probe = ts
        origin_probe = origin
    minutes = (np.asarray(probe.dt.hour, dtype="int64") * 60
               + np.asarray(probe.dt.minute, dtype="int64"))
    anchor_min = int(origin_probe.hour) * 60 + int(origin_probe.minute)
    on_grid = ((minutes - anchor_min) % tf_min) == 0
    off_grid = ts[~on_grid]
    rep.stats["grid_anchor_tz"] = (spec.native_session_tz if spec.bar_anchor_mode == "local" else UTC)
    rep.stats["grid_anchor_local"] = spec.bar_anchor_local
    rep.stats["distinct_utc_hours"] = sorted({int(x) for x in ts.dt.hour.unique()})
    if len(off_grid):
        rep.add("timestamp", "ERROR",
                f"{len(off_grid)} bars are NOT aligned to the {timeframe} grid anchored at "
                f"{spec.bar_anchor_local} ({spec.bar_anchor_mode} mode) - the resampler or the "
                f"feed is inconsistent",
                metric=float(len(off_grid)), examples=[_ts_str(x) for x in off_grid[:5]])
    else:
        rep.add("timestamp", "INFO",
                f"all bars aligned to the {timeframe} grid anchored at "
                f"{spec.bar_anchor_local} ({spec.bar_anchor_mode} mode, tz={rep.stats['grid_anchor_tz']}). "
                f"Distinct UTC hours: {rep.stats['distinct_utc_hours']}")

    # ---- 3. missing bars vs expected calendar ----------------------------
    gaps = ts.diff().dropna()
    expected_sessions = _session_calendar(ts, spec, tf_min)
    n_expected = expected_sessions * _bars_per_session(spec, tf_min, ts)
    if n_expected and n_expected > 0:
        miss_frac = max(0.0, (n_expected - len(df))) / n_expected
        rep.stats["expected_bars"] = float(n_expected)
        rep.stats["missing_bar_fraction"] = float(miss_frac)
        if miss_frac > missing_bar_error_frac:
            rep.add("completeness", "ERROR",
                    f"{miss_frac:.1%} of expected {timeframe} bars are missing "
                    f"({len(df)} present / {int(n_expected)} expected)", metric=miss_frac)
        elif miss_frac > missing_bar_warn_frac:
            rep.add("completeness", "WARN",
                    f"{miss_frac:.1%} of expected {timeframe} bars are missing", metric=miss_frac)
        else:
            rep.add("completeness", "INFO", f"bar completeness {1 - miss_frac:.2%}")
    # A gap is only suspicious if it is larger than what the session calendar
    # can explain: weekends and daily maintenance halts produce legitimate
    # multi-bar holes. Threshold = max(1 expected session, 4 bars) + 1.
    bps = _bars_per_session(spec, tf_min, ts, timeframe)
    # Bir bosluk ancak seans takviminin ACIKLAYAMAYACAGI kadar buyukse suphelidir.
    # Esik = 4 seans + 1 bar (uzun hafta sonu / cok gunlu resmi tatil normaldir),
    # 24/7 piyasalarda ise en az 8 bar.
    # Esik = 5 seans + 1 bar (en az 16 bar): uzun hafta sonu ve 3-4 gunluk
    # resmi/dini tatiller normaldir; daha uzunu gercek bir kesinti olabilir.
    # anomali toleransıyla TUTARLI olsun diye aynı seans-bazlı mantık:
    # ~8 seanslık kapanış + marj. Aksi hâlde iki kontrol birbirini yalanlar.
    gap_bars = max(16.0, float(np.ceil(bps * 8.0)) + 2.0)
    gap_threshold = pd.Timedelta(minutes=tf_min * gap_bars)
    big_gaps = gaps[gaps > gap_threshold]
    rep.stats["bars_per_session_observed"] = float(bps)
    rep.stats["gap_threshold_bars"] = float(gap_threshold / step)
    if len(big_gaps):
        rep.add("completeness", "WARN",
                f"{len(big_gaps)} gaps larger than {gap_threshold / step:.0f} bars "
                f"(max {gaps.max() / step:.0f} bars) - holidays/outages need review",
                metric=float(len(big_gaps)),
                examples=[f"{_ts_str(ts.iloc[i])} (+{gaps.iloc[i] / step:.0f} bars)"
                          for i in big_gaps.index[:5]])
    else:
        rep.add("completeness", "INFO",
                f"no gap larger than {gap_threshold / step:.0f} bars "
                f"(session-aware threshold, {bps:.1f} bars/session)")

    # ---- 4. OHLC integrity ----------------------------------------------
    bad_high = int((h < np.fmax(o, c) - 1e-9).sum())
    bad_low = int((l > np.fmin(o, c) + 1e-9).sum())
    bad_hl = int((h < l).sum())
    nonpos = int((o <= 0).sum() + (h <= 0).sum() + (l <= 0).sum() + (c <= 0).sum())
    for name, cnt, sev in (("high < max(open,close)", bad_high, "ERROR"),
                           ("low > min(open,close)", bad_low, "ERROR"),
                           ("high < low", bad_hl, "ERROR"),
                           ("non-positive price", nonpos, "ERROR")):
        if cnt:
            rep.add("ohlc", sev, f"{cnt} bars violate {name}", metric=float(cnt))
    if not (bad_high or bad_low or bad_hl or nonpos):
        rep.add("ohlc", "INFO", "OHLC envelope consistent on every bar")
    stale = int(((h == l) & (o == c)).sum())
    if stale:
        frac = stale / len(df)
        rep.add("ohlc", "WARN" if frac < 0.05 else "ERROR",
                f"{stale} zero-range bars (high==low==open==close): {frac:.2%} of data",
                metric=frac)
    zero_range = int((h == l).sum())
    rep.stats["zero_range_bars"] = float(zero_range)

    bps_for_gap = _bars_per_session(spec, tf_min, ts, timeframe)
    # ---- 5. price continuity: SEANS-BEKLENEN bosluk analizi --------------
    # Bir barin getirisi ancak onceki barla ZAMANSAL olarak anlamli bicimde
    # bitisikse gercek getiridir. AMA "bitisik" kavrami seans takvimine gore
    # tanimlanmalidir: BIST30'da her gunun ilk bari bir onceki gunun son
    # barindan 4 bar uzaktadir ve bu NORMALDIR. Ham "gap > 1 bar" kurali
    # BIST30'da barlarin %33'unu yanlis sekilde 'veri kesintisi' sayar.
    #
    # Dogru kural: her (hafta gunu, lokal bar saati) slotu icin TIPIK (modal)
    # boslugu hesapla; tipik degeri 4 bardan fazla asan bosluklar GERCEK
    # kesinti/tatil uzantisi olarak isaretle.
    bar_gap_bars = (ts.diff() / step)
    local_ts = ts.dt.tz_convert(spec.native_session_tz)
    slot = pd.Series(list(zip(local_ts.dt.dayofweek.to_numpy(),
                              local_ts.dt.hour.to_numpy())), index=ts.index)
    modal_gap = bar_gap_bars.groupby(slot).transform(lambda g: g.mode().iloc[0]
                                                     if not g.mode().empty else 1.0)
    modal_gap = modal_gap.fillna(1.0)
    # Tolerans SEANS bazlidir, bar bazli degil: '~8 seanslik kapanis' hem
    # 6 bar/seans olan BTC/metallerde hem 2 bar/seans olan BIST'te ayni anlami
    # tasir (uzun hafta sonu + 4-5 gunluk resmî/dinî tatil). Sabit bar esigi
    # kullanilsaydi BIST'te her Bayram tatili 'kesinti' diye isaretlenirdi.
    # 25 bar tavan: 24/7 piyasalarda 8 gun cok gevsek olur, ~4 gunle sinirlanir.
    # Bu bir SEZGI kuralidir: exchange tatil takvimi KULLANILMIYOR, bu yuzden
    # tek basina ERROR uretmez (ERROR esigi ayrica %5'tir).
    bps = bps_for_gap
    tol_bars = _gap_tolerance_bars(spec, bps)
    rep.stats["gap_anomaly_tolerance_bars"] = tol_bars
    anomalous = (bar_gap_bars > modal_gap + tol_bars).fillna(False)
    n_anom = int(anomalous.sum())
    rep.stats["bars_crossing_data_gap"] = float(n_anom)
    rep.stats["bars_crossing_gap_frac"] = float(n_anom / len(df))
    rep.stats["gap_anomaly_rule"] = (
        f"gap > modal_gap(dayofweek, local_hour) + {tol_bars:.0f} bars "
        f"(seans bazlı: 24/7 ise 2 seans, değilse 8 seans; tavan 25 bar; bps={bps:.1f})")

    logret = np.log(c / c.shift(1))
    logret_clean = logret.where(~anomalous)
    rep.stats["abs_logret_max_raw_incl_gaps"] = float(logret.abs().max())

    if n_anom:
        worst = logret.abs().where(anomalous).dropna().sort_values(ascending=False)
        ex = [f"{_ts_str(ts.iloc[i])} r={float(logret.iloc[i]):+.3%} "
              f"(bosluk {bar_gap_bars.iloc[i]:.0f} bar, tipik {modal_gap.iloc[i]:.0f})"
              for i in worst.index[:5]]
        worst_ret = float(worst.iloc[0]) if len(worst) else 0.0
        frac = n_anom / len(df)
        # ERROR ancak feed SISTEMIK olarak bozuksa (barlarin %5'inden fazlasi
        # beklenmedik bosluk atliyorsa). Altindaki durumlar WARN'dur cunku
        # (a) tatil takvimi kullanilmadigi icin yanlis pozitif olabilir,
        # (b) etkilenen barlar isaretlenip getiri/label hesaplarindan
        #     haric tutularak DUZELTILEBILIR. Barlar asla silinmez.
        sev = "ERROR" if frac > 0.05 else "WARN"
        rep.add("continuity", sev,
                f"{n_anom} bar ({frac:.3%}) BEKLENMEDIK bir veri boslugunu atliyor "
                f"(kural: {rep.stats['gap_anomaly_rule']}). Bu barlarin getirisi GERCEK "
                f"GETIRI DEGILDIR: roll-gap/outlier tespiti, label uretimi ve backtest "
                f"P/L hesabinda HARIC TUTULMALIDIR. Barlar SILINMEZ, isaretlenir. "
                f"En buyuk sahte getiriler:",
                metric=float(n_anom), examples=ex)
        if worst_ret > 0.10:
            rep.add("continuity", "WARN",
                    f"Boslugu atlayan en buyuk getiri %{worst_ret * 100:.1f} - tek basina "
                    f"bir 'crash' gibi gorunur ama veri kesintisi artefaktidir. Bu tur "
                    f"barlar uzerinden hicbir istatistik/egitim yapilmamali.")
    else:
        rep.add("continuity", "INFO",
                "no bar crosses an UNEXPECTED data gap: her getiri ya bitisik ya da "
                "seans takviminin normal bir boslugu (hafta sonu / gece arasi)")

    # seans takviminin NORMAL bosluklari (bilgi amacli, hata degil)
    normal_gap = ((bar_gap_bars > 1) & ~anomalous).fillna(False)
    rep.stats["bars_after_normal_session_gap"] = float(int(normal_gap.sum()))

    # ---- 5b. outliers (sadece bitisik/getirisi gecerli barlarda) ---------
    bar_range = (h - l) / c
    out_ret = _mad_outliers(logret_clean.abs().dropna(), thresh=8.0)
    out_rng = _mad_outliers(bar_range.dropna(), thresh=8.0)
    rep.stats["abs_logret_median"] = float(logret_clean.abs().median())
    rep.stats["abs_logret_p99"] = float(logret_clean.abs().quantile(0.99))
    rep.stats["abs_logret_max"] = float(logret_clean.abs().max())
    rep.stats["outlier_return_count"] = float(int(out_ret.sum()))
    rep.stats["outlier_range_count"] = float(int(out_rng.sum()))
    extreme = (logret_clean.abs() > return_thresh).fillna(False)
    rep.stats["outlier_contiguous_count"] = float(int(extreme.sum()))
    if int(extreme.sum()):
        idxs = np.flatnonzero(extreme.to_numpy())[:6]
        rep.add("outlier", "WARN",
                f"{int(extreme.sum())} bar with |log return| > {return_thresh:.0%} on a "
                f"CONTIGUOUS pair (bad print, roll gap or genuine extreme move). "
                f"AYRICA incelenmeli, ASLA SILINMEMELI.",
                metric=float(int(extreme.sum())),
                examples=[f"{_ts_str(ts.iloc[i])} r={float(logret.iloc[i]):+.3f}" for i in idxs])
    else:
        rep.add("outlier", "INFO",
                f"no contiguous bar with |log return| > {return_thresh:.0%}")
    if int(out_ret.sum()):
        rep.add("outlier", "INFO",
                f"{int(out_ret.sum())} MAD(8) return outliers kept but flagged for review",
                metric=float(int(out_ret.sum())))

    # ---- 6. volume -------------------------------------------------------
    volume_required = bool(getattr(spec, "volume_required", True))
    if not spec.has_volume:
        if volume_required:
            rep.add("volume", "ERROR",
                    "spec declares this instrument has no volume data (index series) but "
                    "volume_required=True. Volume/OBV/MFI/liquidity features are unusable -> "
                    "switch to a tradable instrument or set volume_required=False.")
        else:
            rep.add("volume", "WARN",
                    "KULLANICI KARARI: bu varlikta hacim verisi yoktur ve hacim/onay bacagi "
                    "DEVRE DISIDIR (volume_required=False). Cift onay yalnizca trend + "
                    "momentum ile sinirlidir; bu kisit tum raporlarda caveat olarak tasinar.")
    all_zero = bool((v.fillna(0) == 0).all())
    zero_frac = float((v.fillna(0) == 0).mean())
    rep.stats["volume_zero_fraction"] = zero_frac
    rep.stats["volume_total"] = float(np.nansum(v.to_numpy()))
    if all_zero:
        rep.add("volume", "ERROR" if volume_required else "WARN",
                "volume is zero on every bar"
                + ("" if volume_required else
                   " (beklenen durum: endeks serisi, hacim bacagi zaten devre disi)"),
                metric=1.0)
    elif zero_frac > zero_volume_warn_frac:
        rep.add("volume", "WARN",
                f"{zero_frac:.1%} of bars have zero volume (illiquid sessions or feed gaps)",
                metric=zero_frac)
    else:
        rep.add("volume", "INFO", f"zero-volume bars: {zero_frac:.2%}")
    neg = int((v.fillna(0) < 0).sum())
    if neg:
        rep.add("volume", "ERROR", f"{neg} bars with negative volume", metric=float(neg))
    with np.errstate(invalid="ignore"):
        vol_corr = float(np.corrcoef(np.log1p(v.fillna(0))[2:], bar_range[2:])[0, 1]) \
            if len(v) > 10 and v.std() > 0 else np.nan
    rep.stats["volume_vs_range_corr"] = vol_corr
    if np.isfinite(vol_corr) and vol_corr < 0.05 and spec.has_volume and zero_frac < 0.5:
        rep.add("volume", "WARN",
                f"volume/range correlation is only {vol_corr:.3f}: the volume series may be "
                f"misaligned or non-representative -> do not trust volume confirmation",
                metric=vol_corr)
    elif np.isfinite(vol_corr):
        rep.add("volume", "INFO", f"volume vs bar-range correlation = {vol_corr:.3f}")

    # ---- 7. optional columns --------------------------------------------
    populated, partial, empty = [], [], []
    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            continue
        nan_frac = float(df[col].isna().mean())
        series = pd.to_numeric(df[col], errors="coerce")
        informative = bool(series.notna().any() and (series.dropna().abs() > 0).any())
        if nan_frac == 1.0 or not informative:
            empty.append(col)
        elif nan_frac > 0:
            partial.append(f"{col} ({nan_frac:.1%} NaN)")
        else:
            populated.append(col)
    rep.stats["optional_populated"] = populated
    rep.stats["optional_partial_nan"] = partial
    if partial:
        rep.add("optional", "WARN",
                f"optional columns with partial coverage (will create NaN features / "
                f"silent lookahead if ffilled wrongly): {partial}")
    if populated:
        rep.add("optional", "INFO", f"optional columns fully populated: {populated}")
    if empty:
        rep.add("optional", "INFO",
                f"optional columns present but entirely NaN (dropped from the feature set): {empty}")

    # ---- 8. resampling audit --------------------------------------------
    if source_df is not None and len(source_df) and "n_src_bars" in df.columns:
        n_src = pd.to_numeric(df["n_src_bars"], errors="coerce")
        src_tf = _guess_tf(source_df)
        ratio = tf_min / max(1, timeframe_minutes(src_tf)) if src_tf else np.nan
        thin = int((n_src < max(1, ratio * 0.75)).sum()) if np.isfinite(ratio) else 0
        rep.stats["resample_ratio_expected"] = float(ratio) if np.isfinite(ratio) else None
        rep.stats["resample_thin_bars"] = float(thin)
        thin_frac = thin / max(1, len(df))
        rep.stats["resample_thin_fraction"] = float(thin_frac)
        if thin and thin_frac <= 0.20:
            # Az sayida ince bar = yarim gun / tatil / bakim molasi. Normaldir.
            rep.add("resample", "WARN",
                    f"{thin} {timeframe} bar ({thin_frac:.1%}) was built from <75% of the "
                    f"expected {ratio:.0f} source bars (half days / holidays / maintenance halt)",
                    metric=float(thin))
        elif thin:
            # COK sayida ince bar = YAPISAL bir durum (ornegin BIST30'da her gunun
            # 06:00-10:00 bin'i yalnizca 09:30 acilis ani printini icerir). Veri
            # KAYBI olmamasi icin bilincli olarak tutulur, bu yuzden WARN degil INFO;
            # ama o barlarin istatistiksel agirligi digerleriyle AYNI DEGILDIR.
            rep.add("resample", "INFO",
                    f"{thin} {timeframe} bars ({thin_frac:.1%}) are structurally thin "
                    f"(<75% of the expected {ratio:.0f} source bars). They are KEPT "
                    f"deliberately (min_bars_fill=1) so no data is lost, but they cover a "
                    f"SHORTER exposure window than a full bar - do not treat them as "
                    f"equivalent, and check n_src_bars before using them for signals.",
                    metric=float(thin))
        else:
            rep.add("resample", "INFO",
                    f"every {timeframe} bar has the expected number of source bars (~{ratio:.0f})")
        # envelope audit: resampled high must be reachable from the source
        src = source_df.set_index(pd.to_datetime(source_df["timestamp_utc"], utc=True))
        j = df.set_index(ts)
        src_hi = src["high"].resample(f"{tf_min}min",
                                      origin=_origin_pd(spec)).max()
        chk = j["high"].to_frame().join(src_hi.rename("src_high"), how="left").dropna()
        if len(chk):
            viol = int((chk["high"] > chk["src_high"] + 1e-9).sum())
            if viol:
                rep.add("resample", "ERROR",
                        f"{viol} resampled bars have high > source high (resampler bug)",
                        metric=float(viol))
            else:
                rep.add("resample", "INFO", "resampled OHLC envelope matches the source")
    elif source_df is None:
        rep.add("resample", "INFO", "no source frame supplied: resampling audit skipped")

    # ---- 9. freshness / partial bar -------------------------------------
    now = pd.Timestamp.now(tz=UTC)
    last_close_time = ts.iloc[-1] + step
    age = (now - ts.iloc[-1]) / pd.Timedelta(hours=1)
    rep.stats["last_bar_age_hours"] = float(age)
    rep.stats["last_bar_is_complete"] = bool(last_close_time <= now)
    if last_close_time > now:
        rep.add("freshness", "WARN",
                f"the last bar ({_ts_str(ts.iloc[-1])}) is still forming -> it must be "
                f"excluded from any signal/backtest run (look-ahead guard)", metric=float(age))
    elif age > 24 * 7:
        rep.add("freshness", "WARN", f"data is stale: last bar is {age / 24:.1f} days old",
                metric=float(age))
    else:
        rep.add("freshness", "INFO", f"last complete bar {age:.1f}h old")

    # ---- 10. history length ---------------------------------------------
    years = float((ts.iloc[-1] - ts.iloc[0]) / pd.Timedelta(days=365.25))
    rep.stats["history_years"] = years
    rep.stats["bars"] = float(len(df))
    if len(df) < min_rows:
        # 'watch_only' modundaki bir varlikta yetersiz gecmis ERROR degildir:
        # kullanici bu varligi zaten portfoye zorla sokmama karari aldi.
        mode = str(getattr(spec, "mode", "core"))
        sev = "WARN" if mode != "core" else ("ERROR" if len(df) < min_rows * 0.4 else "WARN")
        rep.add("history", sev,
                f"only {len(df)} {timeframe} bars ({years:.2f} years). "
                f"Minimum for a trustworthy walk-forward study is {min_rows}. "
                f"Results on this asset will be statistically weak.",
                metric=float(len(df)))
    else:
        rep.add("history", "INFO", f"{len(df)} bars / {years:.2f} years of history")

    # ---- 11. session shape ------------------------------------------------
    from .resample import calendar_info
    src_tf = _guess_tf(source_df) if (source_df is not None and len(source_df) > 0) else None
    ci = calendar_info(df, spec, timeframe, src_tf=src_tf)
    rep.stats["sessions"] = ci.sessions_total
    rep.stats["bars_per_session_median"] = ci.bars_per_session_median
    rep.stats["bars_per_session_min"] = ci.bars_per_session_min
    rep.stats["bars_per_session_max"] = ci.bars_per_session_max
    for note in ci.notes:
        rep.add("session", "INFO", note)
    # ---- 12. kullanici kararina bagli ZORUNLU caveat'ler -------------------
    for text in tuple(getattr(spec, "caveats", ()) or ()):
        rep.add("mandated_caveat", "WARN", text)
    mode = str(getattr(spec, "mode", "core"))
    rep.stats["mode"] = mode
    if mode == "watch_only":
        rep.add("portfolio", "WARN",
                "KULLANICI KARARI: bu varlik 'watch_only' modundadir. Sinyal uretilir ve "
                "raporlanir ama backtest/PORTFOY performansina ZORLA SOKULMAZ. "
                "Cekirdek portfoy: BTC + GOLD + SILVER.")
    elif mode == "excluded":
        rep.add("portfolio", "WARN", "bu varlik 'excluded' modundadir: hic calistirilmaz.")

    # ---- 12b. intraday adjclose TRAP'i ----------------------------------
    # Yahoo'nun INTRADAY serilerinde adjclose == close olur; yani kurumsal
    # aksiyon duzeltmesi ICMERMEZ. Bunu bilmeden 'adj_ratio' uzerinden tespit
    # yapmaya calismak sessizce HICBIR sey bulmaz ve bolunmeler sahte fiyat
    # sicramasi olarak seriye girer. Bu yuzden acikca raporlanir.
    if "adjclose" in df.columns and pd.to_numeric(df["adjclose"], errors="coerce").notna().any():
        ac = pd.to_numeric(df["adjclose"], errors="coerce")
        cl = pd.to_numeric(df["close"], errors="coerce")
        same = float(np.isclose(ac, cl, rtol=1e-6, atol=1e-9, equal_nan=False).mean())
        rep.stats["adjclose_equals_close_frac"] = same
        if same > 0.99:
            rep.add("corporate_actions", "WARN",
                    f"adjclose, close ile %{same * 100:.1f} oraninda AYNI: bu seri kurumsal "
                    f"aksiyon duzeltmesi ICMERMIYOR (Yahoo intraday davranisi). Temettu/"
                    f"bolunme tespiti bu seriden YAPILAMAZ; GUNLUK serinin adjclose/close "
                    f"orani kullanilmalidir (adjust.corporate_actions_from_daily). Aksi halde "
                    f"bolunmeler SAHTE fiyat sicramasi olarak seriye girer.")
        else:
            rep.add("corporate_actions", "INFO",
                    f"adjclose/close ayni olma orani %{same * 100:.1f} -> seri kurumsal "
                    f"aksiyon duzeltmesi iceriyor gibi gorunuyor")

    # ---- 13. duzeltme kapisi (KARAR 2 ve 3) ------------------------------
    # On-ay vadeli seriler (GC=F / SI=F) adjust pipeline'i CALISTIRILMADAN
    # getirileri uzerinde model egitilemez. adjust.adjust_asset() calistiginda
    # frame.attrs icine kanit alanlari yazar; kapi bu kanitlari dogrular.
    attrs = getattr(df, "attrs", None) or {}
    adjusted = bool(attrs.get("roll_adjusted", False))
    outage_marked = bool(attrs.get("outage_marked", False))
    has_return_flag = "return_valid" in df.columns
    rep.stats["adjust_pipeline_ran"] = bool(adjusted and outage_marked and has_return_flag)
    # kanit alanlari HER varlik icin raporlanir (yoksa 0) ki tablolar karsilastirilabilsin
    rep.stats["roll_flagged_bars"] = int(attrs.get("roll_flagged_bars", 0) or 0)
    rep.stats["bad_print_flagged_bars"] = int(attrs.get("bad_print_flagged_bars", 0) or 0)
    rep.stats["non_tradable_bars"] = int(attrs.get("non_tradable_bars", 0) or 0)
    rep.stats["return_invalid_bars"] = int(attrs.get("return_invalid_bars", 0) or 0)
    rep.stats["outage_windows"] = len(attrs.get("outage_windows", []) or [])
    rep.stats["roll_correction_applied"] = bool(attrs.get("roll_correction_applied", False))
    if "non_tradable" in df.columns:
        rep.stats["non_tradable_frac"] = float(pd.to_numeric(
            df["non_tradable"], errors="coerce").fillna(False).astype(bool).mean())
    if "non_tradable_reason" in df.columns:
        vc = df.loc[df["non_tradable_reason"].astype(str) != "", "non_tradable_reason"] \
               .astype(str).value_counts().head(6)
        rep.stats["non_tradable_reasons"] = {str(k): int(v) for k, v in vc.items()}
    if bool(getattr(spec, "requires_adjustment", False)):
        if not rep.stats["adjust_pipeline_ran"]:
            rep.add("adjustment", "ERROR",
                    "KARAR 2/3: bu seri on-ay vadeli (front-month) ve adjust pipeline'i "
                    "HENUZ CALISTIRILMADI. Calistirilmadan bu varlikta getiri temelli "
                    "modelleme/backtest YAPILAMAZ. (python3 scripts/run_adjust.py)")
        else:
            n_roll = int(attrs.get("roll_flagged_bars", 0))
            applied = bool(attrs.get("roll_correction_applied", False))
            detectable = bool(attrs.get("roll_detectable", True))
            n_nontrad = int(attrs.get("non_tradable_bars", 0))
            n_retinv = int(attrs.get("return_invalid_bars", 0))
            rep.stats.update({"roll_correction_applied": applied})
            rep.add("adjustment", "INFO",
                    f"adjust pipeline CALISTI: {len(attrs.get('outage_windows', []))} kesinti "
                    f"penceresi isaretlendi, {n_nontrad} bar non-tradable, {n_retinv} getiri "
                    f"gecersiz sayildi, {n_roll} roll adayi ISARETLENDI "
                    f"(fiyat duzeltmesi uygulandi={applied}). Bar SILINMEDI, bar UYDURULMADI.")
            if detectable and n_roll and not applied:
                # DURUST SINIR: feed'de kontrat ayi kimligi yok, roll kesin tespit
                # edilemez. Bu yuzden fiyatlar DUZELTILMEZ, adaylar insan incelemesine
                # birakilir ve bu bir uyari olarak tasinar.
                rep.add("adjustment", "WARN",
                        f"{n_roll} roll ADAYI yalnizca ISARETLENDI, fiyat DUZELTILMEDI. Sebep: "
                        f"Yahoo on-ay serisinde KONTRAT AYI kimligi yoktur, bu yuzden roll ile "
                        f"gercek ekstrem hareket kesin olarak AYIRT EDILEMEZ. "
                        f"close_adjusted == close_raw. Roll adaylari reports/adjust_evidence.md "
                        f"icinde listelenir ve INSAN INCELEMESI bekler. Kesin cozum: kontrat ayi "
                        f"kimligi olan bir continuous future kaynagi saglamak.")
    elif adjusted:
        rep.add("adjustment", "INFO",
                f"adjust pipeline calisti (bu varlikta roll TANIM GEREGI imkansiz: "
                f"{int(attrs.get('roll_flagged_bars', 0))} roll). "
                f"{int(attrs.get('non_tradable_bars', 0))} bar non-tradable isaretlendi, "
                f"{int(attrs.get('return_invalid_bars', 0))} getiri gecersiz sayildi.")
    else:
        rep.add("adjustment", "WARN",
                "adjust pipeline henuz calistirilmadi. Bu varlikta roll riski yok ama "
                "kesinti/islem-disi bar isaretleri (non_tradable, return_valid) OLMADAN "
                "backtest yapilmamali.")

    rep.finalise(min_rows)
    return rep


def _origin_pd(spec: AssetSpec) -> pd.Timestamp:
    """Grid origin matching the (tz-aware UTC) index of the source frame."""
    from .resample import _origin_utc
    return _origin_utc(spec)


def _guess_tf(df: pd.DataFrame) -> Optional[str]:
    """Median bar spacing of a source frame, as a canonical timeframe string."""
    from .resample import _infer_source_minutes
    minutes = _infer_source_minutes(df)
    if minutes is None:
        return None
    for name, mins in (("1m", 1), ("5m", 5), ("15m", 15), ("30m", 30), ("1h", 60),
                       ("2h", 120), ("4h", 240), ("6h", 360), ("8h", 480),
                       ("12h", 720), ("1d", 1440)):
        if minutes == mins:
            return name
    return f"{minutes}m"


def _session_calendar(ts: pd.Series, spec: AssetSpec, tf_min: int) -> float:
    """Number of expected sessions between the first and last timestamp."""
    if spec.continuous_24h:
        days = (ts.iloc[-1] - ts.iloc[0]) / pd.Timedelta(days=1)
        return float(days) + 1.0
    from .resample import session_date
    local = pd.DatetimeIndex(ts.dt.tz_convert(spec.native_session_tz).dt.tz_localize(None))
    sess = pd.Series(session_date(local, spec), index=ts.index)
    all_days = pd.date_range(sess.min(), sess.max(), freq="D", tz=spec.native_session_tz)
    allowed = [d for d in all_days if d.dayofweek in spec.trading_days]
    return float(len(allowed))


def _gap_tolerance_bars(spec: AssetSpec, bps: float) -> float:
    """Beklenmedik boşluk toleransı, SEANS bazlı (bar bazlı değil).

    '~N seanslık kapanış' hem 6 bar/seans olan BTC/metallerde hem 2 bar/seans
    olan BIST'te aynı anlamı taşır. Sabit bar eşiği kullanılsaydı BIST'te her
    Bayram tatili 'kesinti' diye işaretlenirdi (H27).

    * 24/7 varlık (BTC): tatil kavramı yok -> 2 seans (2 gün) yeter.
    * seanslı varlık: hafta sonu + 4-5 günlük resmî/dinî tatil -> 8 seans.
    * tavan 25 bar: 24/7'de 8 gün çok gevşek olurdu.

    Bu bir SEZGİ kuralıdır; exchange tatil takvimi KULLANILMAZ, bu yüzden tek
    başına ERROR üretmez (ERROR eşiği ayrıca %5'tir).
    """
    sessions = 2.0 if bool(getattr(spec, "continuous_24h", False)) else 8.0
    return float(min(max(sessions * float(bps), 8.0) + 1.0, 25.0))


def _bars_per_session(spec: AssetSpec, tf_min: int, ts: pd.Series,
                      tf_label: str = "4h") -> float:
    if spec.continuous_24h:
        return 24 * 60 / tf_min
    from .resample import session_date
    local = pd.DatetimeIndex(ts.dt.tz_convert(spec.native_session_tz).dt.tz_localize(None))
    sess = session_date(local, spec, tf_label)
    per = pd.Series(np.ones(len(sess)), index=sess).groupby(level=0).sum()
    med = float(per.median())
    return med if med > 0 else 1.0


# --------------------------------------------------------------------------
# Portfolio-level checks
# --------------------------------------------------------------------------

def qc_portfolio(frames: Dict[str, pd.DataFrame],
                 min_overlap_bars: int = 500) -> Dict[str, Any]:
    """Cross-asset checks: common window, pairwise co-movement, correlation risk.

    Two correlation views are produced on purpose:

    * ``pairwise`` - on the raw 4H grids, pairwise-complete. Because the
      session calendars differ (BTC is 24/7, metals are ~23h NY, BIST is
      6.5h Istanbul) the overlap is only the bars where BOTH assets print.
      This is the honest intraday co-movement estimate, and the overlap count
      is reported next to every coefficient so a thin estimate is visible.
    * ``daily`` - log returns of daily closes on shared calendar dates. This
      is the number the correlation risk limit should actually use, because
      it is not distorted by session misalignment.
    """
    out: Dict[str, Any] = {}
    frames = {k: v for k, v in frames.items() if v is not None and len(v)}
    if len(frames) < 2:
        out["skipped"] = "fewer than two non-empty assets"
        return out

    idx = {k: pd.to_datetime(v["timestamp_utc"], utc=True) for k, v in frames.items()}
    spans = {k: (i.min(), i.max()) for k, i in idx.items()}
    start = max(a for a, _ in spans.values())
    end = min(b for _, b in spans.values())
    out["common_window"] = {"start": _ts_str(start), "end": _ts_str(end),
                            "per_asset": {k: {"start": _ts_str(a), "end": _ts_str(b)}
                                          for k, (a, b) in spans.items()}}

    rets = {}
    for k, v in frames.items():
        s = v.set_index(idx[k])["close"].astype("float64")
        s = s[(s.index >= start) & (s.index <= end)].sort_index()
        rets[k] = np.log(s).diff()
    R = pd.DataFrame(rets)
    out["common_window_bars"] = {k: int(R[k].notna().sum()) for k in R.columns}
    out["overlap_sufficient"] = bool(min(out["common_window_bars"].values()) >= min_overlap_bars)

    keys = sorted(R.columns)          # kanonik anahtar: alfabetik kucuk|buyuk
    pair: Dict[str, Dict[str, Any]] = {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            both = R[[a, b]].dropna()
            if len(both) < 30 or both[a].std() == 0 or both[b].std() == 0:
                pair[f"{a}|{b}"] = {"corr": None, "n": int(len(both))}
                continue
            pair[f"{a}|{b}"] = {"corr": round(float(both[a].corr(both[b])), 4),
                                "n": int(len(both))}
    out["pairwise"] = pair
    out["pairwise_min_overlap"] = min((v["n"] for v in pair.values()), default=0)
    strong = [f"{k} = {v['corr']:+.3f} (n={v['n']})"
              for k, v in pair.items() if v["corr"] is not None and abs(v["corr"]) > 0.70]
    out["correlation_warning"] = strong
    if pair:
        best = max(((abs(v["corr"]), k, v["corr"]) for k, v in pair.items()
                    if v["corr"] is not None), default=(0, None, None))
        out["max_abs_correlation"] = {"pair": best[1], "corr": best[2], "abs": round(best[0], 4)}

    daily = {}
    for k, v in frames.items():
        s = v.set_index(idx[k])["close"].astype("float64")
        s = s[(s.index >= start) & (s.index <= end)].sort_index()
        daily[k] = s.groupby(s.index.tz_convert(UTC).date).last()
    D = pd.DataFrame(daily)
    Rd = np.log(D).diff().dropna(how="all")
    if len(Rd) > 30:
        cd = Rd.corr()
        dcols = sorted(cd.columns)
        out["daily"] = {
            "rows": int(len(Rd)),
            "corr": {f"{a}|{b}": (None if pd.isna(cd.loc[a, b]) else round(float(cd.loc[a, b]), 4))
                     for a in dcols for b in dcols if a < b},
            "overlap_days": {k: int(Rd[k].notna().sum()) for k in Rd.columns},
        }
        out["daily_correlation_warning"] = [
            f"{a}|{b} = {cd.loc[a, b]:+.3f}"
            for a in dcols for b in dcols
            if a < b and pd.notna(cd.loc[a, b]) and abs(cd.loc[a, b]) > 0.70]
    return out


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def reports_to_markdown(reports: List[AssetQCReport], portfolio: Dict[str, Any],
                        generated_at: Optional[str] = None) -> str:
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    L: List[str] = []
    L.append("# Faz 1 - Veri Kalitesi Raporu (Data Quality Report)")
    L.append("")
    L.append(f"*Uretim zamani: {ts}*  ")
    L.append("*Bu rapor ham veriyi degistirmez; sadece tespit eder. Temizlik ayri ve loglanan bir adimdir.*")
    L.append("")
    L.append("## Ozet")
    L.append("")
    L.append("| Varlik | Sembol | Mod | TF | Bar | Ilk bar | Son bar | Karar | ERROR | WARN | Gecmis yeterli | Model icin uygun |")
    L.append("|---|---|---|---|---:|---|---|---|---:|---:|---|---|")
    for r in reports:
        mode = r.stats.get("mode", "core")
        L.append(f"| {r.asset_key} | `{r.symbol}` | **{mode}** | {r.timeframe} | {r.rows} | "
                 f"{(r.first_ts or '-')[:10]} | {(r.last_ts or '-')[:10]} | "
                 f"**{r.verdict}** | {r.n_error} | {r.n_warn} | "
                 f"{'EVET' if r.enough_history else 'HAYIR'} | "
                 f"{'EVET' if r.usable_for_modelling else 'HAYIR'} |")
    L.append("")
    core = [r.asset_key for r in reports if r.stats.get("mode", "core") == "core"]
    watch = [r.asset_key for r in reports if r.stats.get("mode") == "watch_only"]
    L.append(f"**Cekirdek backtest portfoyu:** {', '.join(core) or '-'}  ")
    L.append(f"**Izleme modu (portfoye zorla sokulmaz):** {', '.join(watch) or '-'}")
    L.append("")
    # KARAR 1/2/3/4: her raporda AYNEN basilmasi zorunlu caveat blogu
    mandated = [(r.asset_key, f.message) for r in reports
                for f in r.findings if f.check == "mandated_caveat"]
    if mandated:
        L.append("## ZORUNLU CAVEAT'LER (kullanici karari - her raporda aynen tasinir)")
        L.append("")
        cur = None
        for asset, msg in mandated:
            if asset != cur:
                L.append(f"**{asset}**")
                L.append("")
                cur = asset
            L.append(f"- :warning: {msg}")
        L.append("")
    for r in reports:
        L.append(f"## {r.asset_key} (`{r.symbol}`) - {r.timeframe}")
        L.append("")
        L.append(f"**Karar: {r.verdict}** | mod: **{r.stats.get('mode', 'core')}** | "
                 f"bar: {r.rows} | aralik: {r.first_ts} -> {r.last_ts}")
        L.append("")
        if r.stats:
            L.append("### Metrikler")
            L.append("")
            L.append("| Metrik | Deger |")
            L.append("|---|---|")
            for k, v in r.stats.items():
                if isinstance(v, float):
                    L.append(f"| `{k}` | {v:.6g} |")
                else:
                    L.append(f"| `{k}` | {v} |")
            L.append("")
        if r.blockers:
            L.append("### BLOCKER (modelleme yapilamaz)")
            L.append("")
            for b in r.blockers:
                L.append(f"- :no_entry: {b}")
            L.append("")
        if r.caveats:
            L.append("### Uyari (sonuclara yazilmali)")
            L.append("")
            for b in r.caveats:
                L.append(f"- :warning: {b}")
            L.append("")
        L.append("### Tum bulgular")
        L.append("")
        L.append("| Check | Seviye | Bulgu | Metrik |")
        L.append("|---|---|---|---|")
        for f in r.findings:
            metric = f"{f.metric:.4g}" if isinstance(f.metric, float) else ("-" if f.metric is None else f.metric)
            msg = f.message.replace("|", "\\|")
            ex = ("  \n" + "ornek: " + "; ".join(f.examples or [])) if f.examples else ""
            L.append(f"| {f.check} | {f.severity} | {msg}{ex} | {metric} |")
        L.append("")
    if portfolio:
        L.append("## Portfoy duzeyi kontroller")
        L.append("")
        cw = portfolio.get("common_window", {})
        L.append(f"- Ortak pencere: **{str(cw.get('start'))[:16]} -> {str(cw.get('end'))[:16]} UTC**")
        L.append(f"- Ortak pencerede bar sayilari: {portfolio.get('common_window_bars')}")
        L.append(f"- Ortak pencere yeterli mi (>=500 bar): **{portfolio.get('overlap_sufficient')}**")
        L.append(f"- En yuksek |korelasyon| (4H, ortak saatler): {portfolio.get('max_abs_correlation')}")
        L.append("")
        pw = portfolio.get("pairwise") or {}
        if pw:
            L.append("### 4H log-getiri korelasyonu (pairwise-complete, sadece ortak saatler)")
            L.append("")
            L.append("| Cift | korelasyon | n (ortak bar) |")
            L.append("|---|---|---:|")
            for k, v in pw.items():
                L.append(f"| {k} | {v['corr']} | {v['n']} |")
            L.append("")
            L.append("*Not: BTC 24/7, metaller ~23h NY, BIST 6.5h Istanbul islem gordugu icin "
                     "ortak bar sayilari farklidir. Korelasyon limitleri asagidaki GUNLUK "
                     "korelasyona gore uygulanmalidir; 4H degeri sadece intraday es-zamanlilik "
                     "bilgisi verir.*")
        d = portfolio.get("daily") or {}
        if d.get("corr"):
            L.append("")
            L.append(f"### Gunluk log-getiri korelasyonu (ortak gun sayisi: {d.get('rows')})")
            L.append("")
            L.append("| Cift | korelasyon |")
            L.append("|---|---|")
            for k, v in d["corr"].items():
                L.append(f"| {k} | {v} |")
            L.append("")
            L.append(f"- Ortak gun sayilari: {d.get('overlap_days')}")
        L.append("")
        L.append("*Korelasyon limitleri GUNLUK korelasyona gore uygulanir. 4H degeri sadece "
                 "intraday es-zamanlilik bilgisidir; grid faz farki olan ciftlerde (orn. BIST30 "
                 "03/07/11 UTC vs BTC 00/04/08 UTC) 4H ortus bar sayisi 0 olabilir.*")
        warns = (portfolio.get("correlation_warning") or []) + (portfolio.get("daily_correlation_warning") or [])
        if warns:
            L.append("")
            L.append(f"- :warning: |korelasyon| > 0.70 olan ciftler (risk limiti devreye girer): {warns}")
        L.append("")
    return "\n".join(L)


def save_reports(reports: List[AssetQCReport], portfolio: Dict[str, Any], out_dir: str,
                 prefix: str = "qc") -> Dict[str, str]:
    import json
    import os
    os.makedirs(out_dir, exist_ok=True)
    paths: Dict[str, str] = {}
    p_json = os.path.join(out_dir, f"{prefix}_report.json")
    with open(p_json, "w", encoding="utf-8") as fh:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "assets": [r.to_dict() for r in reports],
                   "portfolio": portfolio}, fh, indent=2, default=str)
    paths["json"] = p_json
    rows: List[Dict[str, Any]] = []
    for r in reports:
        for f in r.findings:
            rows.append({"asset": r.asset_key, "symbol": r.symbol, "timeframe": r.timeframe,
                         **f.to_dict()})
    p_csv = os.path.join(out_dir, f"{prefix}_findings.csv")
    pd.DataFrame(rows).to_csv(p_csv, index=False)
    paths["csv"] = p_csv
    p_md = os.path.join(out_dir, f"{prefix}_report.md")
    with open(p_md, "w", encoding="utf-8") as fh:
        fh.write(reports_to_markdown(reports, portfolio))
    paths["markdown"] = p_md
    return paths


__all__ = ["Finding", "AssetQCReport", "qc_asset", "qc_portfolio",
           "reports_to_markdown", "save_reports"]
