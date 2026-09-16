"""AŞAMA 2 — Market regime detection (SADELİK KURALI: yalnızca 2 ölçüm).

Bu modül bilinçli olarak KÜÇÜKTÜR. Kullanıcı kararıyla İPTAL edilen yöntemler
burada YOKTUR ve config'te de tutulmaz: ADX, Hurst exponent, HMM, Choppiness
Index, Bollinger Band width, Ichimoku, Supertrend, Keltner.

Gerekçe: kullanılmayan bir parametre ayarlanabilir bir parametredir;
ayarlanabilir her parametre overfitting yüzeyidir. İki ölçüm, altı durum.

Ölçüm 1 — TREND (grafikte TEK görsel öğe: EMA200)
    trend_up    close > EMA200  AND  EMA200 slope > +min_atr_units (ATR-normalized)
    trend_down  close < EMA200  AND  EMA200 slope < -min_atr_units
    range       otherwise (yön ile eğim uyuşmuyor ya da eğim çok zayıf)

Ölçüm 2 — VOLATİLİTE (ATR yüzdelik dilimi, geriye dönük pencere)
    vol_high    pct >= 0.75
    vol_low     pct <= 0.25
    vol_normal  aradaki

Look-ahead garantileri
----------------------
* EMA200 yalnızca geçmiş kapatışları kullanır (pandas ewm, adjust=False).
* Eğim ``ema[t] - ema[t-slope_window]``: yalnızca geçmiş.
* ATR yüzdeliği ``rolling(window).rank(pct=True)``: pencere t'de BİTER,
  gelecek barları içermez.
* İlk ``min_bars_for_regime`` barda rejim NaN'dır ve ``fail_closed=True``
  iken bu barlarda SİNYAL ÜRETİLMEZ. Isınma dönemi sessizce "range" sayılmaz;
  açıkça bilinmiyor olarak işaretlenir.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import DEFAULT_REGIME, RegimeConfig  # noqa: F401

TREND_STATES = ("trend_up", "trend_down", "range")
VOL_STATES = ("vol_high", "vol_normal", "vol_low")

REGIME_COLUMNS = (
    "ema_trend",          # EMA200 (tek trend filtresi)
    "ema_slope_atr",      # ATR'ye normalize edilmiş EMA200 eğimi
    "atr",                # Wilder ATR(period)
    "atr_pct",            # ATR / close x 100
    "atr_percentile",     # geriye dönük yüzdelik dilim (0..1)
    "trend_state",        # trend_up | trend_down | range | (NaN = bilinmiyor)
    "vol_state",          # vol_high | vol_normal | vol_low | (NaN)
    "regime",             # "<trend>|<vol>" bileşik etiket
    "regime_valid",       # False ise rejim BİLİNMİYOR -> fail-closed
    "long_regime_ok",     # bu barda long sinyale rejim izin veriyor mu
    "short_regime_ok",    # bu barda short sinyale rejim izin veriyor mu
)


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-smoothed ATR. ``shift(1)`` ile yalnızca geçmiş barları kullanır."""
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def label_regime(df: pd.DataFrame, cfg: RegimeConfig = DEFAULT_REGIME,
                 price_col: str = "close",
                 valid_mask: Optional[pd.Series] = None) -> pd.DataFrame:
    """Add the regime columns to a canonical 4H frame. Never modifies prices."""
    out = df.copy()
    close = pd.to_numeric(out[price_col], errors="coerce").astype("float64")
    high = pd.to_numeric(out["high"], errors="coerce").astype("float64")
    low = pd.to_numeric(out["low"], errors="coerce").astype("float64")

    ema = close.ewm(span=cfg.ema_trend_period, adjust=False,
                    min_periods=cfg.ema_trend_period).mean()
    atr = wilder_atr(high, low, close, cfg.atr_period)
    atr_pct = (atr / close * 100.0).replace([np.inf, -np.inf], np.nan)

    # EMA200 eğimi, ATR biriminde (ölçekten bağımsız hale getirmek için)
    ema_shift = ema.shift(cfg.slope_window)
    denom = (atr_pct / 100.0 * close).replace(0, np.nan)      # ~ ATR in price units
    slope_atr = (ema - ema_shift) / denom

    pct = (atr_pct.rolling(cfg.atr_percentile_window, min_periods=max(50, cfg.atr_period * 3))
                  .rank(pct=True))

    trend = pd.Series(np.nan, index=out.index, dtype="object")
    up = (close > ema) & (slope_atr > cfg.slope_min_atr_units)
    dn = (close < ema) & (slope_atr < -cfg.slope_min_atr_units)
    trend[up.fillna(False)] = "trend_up"
    trend[dn.fillna(False)] = "trend_down"
    flat = trend.isna() & ema.notna() & slope_atr.notna()
    trend[flat] = "range"

    vol = pd.Series(np.nan, index=out.index, dtype="object")
    vol[(pct >= cfg.vol_high_pct).fillna(False)] = "vol_high"
    vol[(pct <= cfg.vol_low_pct).fillna(False)] = "vol_low"
    mid = vol.isna() & pct.notna()
    vol[mid] = "vol_normal"

    position = pd.Series(np.arange(len(out)), index=out.index)
    enough_bars = position >= cfg.min_bars_for_regime
    valid = enough_bars & ema.notna() & slope_atr.notna() & pct.notna()
    if valid_mask is not None:
        valid = valid & pd.Series(np.asarray(valid_mask, dtype=bool), index=out.index)

    regime = np.where(valid & trend.notna() & vol.notna(),
                      trend.astype("string").fillna("") + "|" + vol.astype("string").fillna(""),
                      None)

    out["ema_trend"] = ema.to_numpy()
    out["ema_slope_atr"] = slope_atr.to_numpy()
    out["atr"] = atr.to_numpy()
    out["atr_pct"] = atr_pct.to_numpy()
    out["atr_percentile"] = pct.to_numpy()
    out["trend_state"] = trend.where(valid).to_numpy()
    out["vol_state"] = vol.where(valid).to_numpy()
    out["regime"] = regime
    out["regime_valid"] = valid.to_numpy() & pd.Series(regime, index=out.index).notna().to_numpy()

    long_ok = out["regime_valid"] & out["trend_state"].isin(list(cfg.long_allowed_in)) \
        & (out["atr_percentile"] <= cfg.max_atr_percentile)
    short_ok = out["regime_valid"] & out["trend_state"].isin(list(cfg.short_allowed_in)) \
        & (out["atr_percentile"] <= cfg.max_atr_percentile)
    if cfg.fail_closed:
        long_ok = long_ok.fillna(False)
        short_ok = short_ok.fillna(False)
    out["long_regime_ok"] = long_ok.astype(bool).to_numpy()
    out["short_regime_ok"] = short_ok.astype(bool).to_numpy()
    return out


def regime_distribution(df: pd.DataFrame) -> Dict[str, Any]:
    """Label distribution + per-regime descriptive statistics for reporting."""
    n = int(df["regime_valid"].sum()) if "regime_valid" in df.columns else 0
    total = len(df)
    out: Dict[str, Any] = {
        "bars": total,
        "labelled_bars": n,
        "unlabelled_bars": total - n,
        "unlabelled_frac": round((total - n) / total, 4) if total else 0.0,
    }
    if "regime" in df.columns:
        vc = df.loc[df["regime_valid"].astype(bool), "regime"].astype(str).value_counts()
        out["regime_counts"] = {str(k): int(v) for k, v in vc.items()}
        out["regime_pct"] = {str(k): round(float(v) / n * 100, 2) for k, v in vc.items()} if n else {}
    if "trend_state" in df.columns:
        tv = df.loc[df["regime_valid"].astype(bool), "trend_state"].astype(str).value_counts()
        out["trend_counts"] = {str(k): int(v) for k, v in tv.items()}
    if "vol_state" in df.columns:
        vv = df.loc[df["regime_valid"].astype(bool), "vol_state"].astype(str).value_counts()
        out["vol_counts"] = {str(k): int(v) for k, v in vv.items()}
    for col in ("atr_percentile", "ema_slope_atr"):
        if col in df.columns:
            x = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(x):
                out[f"{col}_p50"] = round(float(x.median()), 5)
                out[f"{col}_p05"] = round(float(x.quantile(0.05)), 5)
                out[f"{col}_p95"] = round(float(x.quantile(0.95)), 5)
    if "long_regime_ok" in df.columns:
        out["long_regime_ok_bars"] = int(df["long_regime_ok"].sum())
        out["long_regime_ok_frac"] = round(float(df["long_regime_ok"].mean()), 4)
    if "short_regime_ok" in df.columns:
        out["short_regime_ok_bars"] = int(df["short_regime_ok"].sum())
        out["short_regime_ok_frac"] = round(float(df["short_regime_ok"].mean()), 4)
    return out


def regime_report_markdown(dists: Dict[str, Dict[str, Any]], title: str = "Rejim Dağılımı") -> str:
    L: List[str] = [f"# {title}", ""]
    L.append("| Varlık | bar | etiketli | etiketsiz % | trend_up | trend_down | range | "
             "vol_high | vol_normal | vol_low | long OK | short OK |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, d in dists.items():
        tc = d.get("trend_counts", {})
        vc = d.get("vol_counts", {})
        L.append(f"| **{name}** | {d.get('bars', 0)} | {d.get('labelled_bars', 0)} | "
                 f"%{d.get('unlabelled_frac', 0) * 100:.1f} | "
                 f"{tc.get('trend_up', 0)} | {tc.get('trend_down', 0)} | {tc.get('range', 0)} | "
                 f"{vc.get('vol_high', 0)} | {vc.get('vol_normal', 0)} | {vc.get('vol_low', 0)} | "
                 f"{d.get('long_regime_ok_bars', 0)} | {d.get('short_regime_ok_bars', 0)} |")
    L.append("")
    L.append("> Rejim bileşik etiketi `trend|vol` biçimindedir (6 durum). "
             "`etiketsiz` barlar EMA200/ATR yüzdeliği ISINMA dönemidir ve "
             "`fail_closed=True` olduğu için bu barlarda SİNYAL ÜRETİLMEZ.")
    L.append("")
    return "\n".join(L)


__all__ = ["label_regime", "regime_distribution", "regime_report_markdown",
           "wilder_atr", "TREND_STATES", "VOL_STATES", "REGIME_COLUMNS"]
