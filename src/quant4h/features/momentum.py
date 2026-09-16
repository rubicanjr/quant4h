"""AŞAMA 4 — ATR-normalized ROC momentum: çift onayın 2. bacağı.

TEK KURAL (kabul kriteri 1)
---------------------------
    mom(t) = (close[t] / close[t-n] - 1) / (ATR14[t] / close[t-n])

Yani "son n barda fiyat, ATR cinsinden kaç birim yer değiştirdi". Payda
``ATR/close.shift(n)`` olduğu için ölçü birimsizdir ve BTC ile BIST hissesi
karşılaştırılabilir. RSI / MACD / Stochastic / StochRSI / MFI / OBV / CCI
**YOKTUR** (yasaklı liste geçerli).

KARAR ANI SÖZLEŞMESİ (kabul kriteri 3)
--------------------------------------
Bar ``t``'de karar anı ``t``'nin AÇILIŞIDIR. ``close[t-1]`` o ana kadar
KAPANMIŞ son bardır; ``close[t-n]`` haydi haydi kapanmıştır. Formüldeki her
terim karar anından önce bilinir → look-ahead yoktur. Bu, ``tests/
test_momentum.py::test_momentum_has_no_lookahead`` içinde "gelecek barları
sil" testiyle kilitlidir.

GUARD (kabul kriteri 4) — fail-closed
-------------------------------------
``momentum_valid=False`` (dolayısıyla ``momentum_ok=False``) olur:
  * ATR NaN veya <= 0
  * ``close[t-n]`` NaN veya <= 0
  * ``non_tradable == True``
  * ``return_valid == False``
  * ilk n bar (ısınma)
Momentum BİLİNMİYORSA onay YOKTUR. Guard asla "0 varsay" demez.

KALİBRASYON (kabul kriteri 6)
-----------------------------
Geçiş oranı ``[0.10, 0.60]`` bandı dışındaysa **TUNE EDİLMEZ**; yalnızca
bayraklanır ve rapora not düşülür. ``MomentumConfig.tune_out_of_band=True``
config seviyesinde ``ValueError`` verir, yani otomatik ayarlama kod yolu
olarak da kapalıdır. Sebep: bant dışı bir oran ya rejimin ya da varlığın
gerçeğidir; eşiği ona uydurmak geçmişe eğrileri oturtmaktır.

İSİMLENDİRME
------------
``momentum_ok`` = LONG tarafı onayı (``momentum_valid AND mom > +m``). Kullanıcı
şartnamesindeki "momentum_ok=False" ifadesi bu kolonu karşılar. Short tarafı
ayrı kolondur (``momentum_short_ok``) ve yalnızca core varlıklarda üretilir.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import DEFAULT_MOMENTUM, DEFAULT_REGIME, MomentumConfig
from .regime import wilder_atr

MOMENTUM_COLUMNS = (
    "atr",                     # ATR(14) — yoksa hesaplanır
    "mom",                     # ATR-normalize ROC (birimsiz)
    "momentum_valid",          # guard geçti mi (fail-closed)
    "momentum_invalid_reason", # "" | warmup | atr_invalid | base_invalid | non_tradable | return_invalid
    "momentum_state",          # above | below | neutral | invalid
    "momentum_ok",             # LONG onayı: valid AND mom > +m
    "momentum_short_ok",       # SHORT onayı: valid AND mom < -m (yalnız allow_short)
)

# Kabul kriteri 5'teki zincir. SIRA önemlidir: rapor her halkanın bar sayısını
# ayrı ayrı verir, böylece hangi kapının ne kadar elediği görünür.
LONG_CHAIN = (
    ("regime",      "long_regime_ok"),
    ("context",     "longs_allowed"),
    ("tradable",    "~non_tradable"),
    ("return_valid", "return_valid"),
    ("levels",      "stop_valid_long"),
    ("momentum",    "momentum_ok"),
)
SHORT_CHAIN = (
    ("regime",      "short_regime_ok"),
    ("tradable",    "~non_tradable"),
    ("return_valid", "return_valid"),
    ("levels",      "stop_valid_short"),
    ("momentum",    "momentum_short_ok"),
)


def _bool_col(df: pd.DataFrame, col: str, default: bool) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype=bool)
    s = df[col]
    if s.dtype == bool:
        return s
    return pd.to_numeric(s, errors="coerce").fillna(0 if not default else 1).astype(bool)


def add_momentum(df: pd.DataFrame, cfg: MomentumConfig = DEFAULT_MOMENTUM,
                 allow_short: Optional[bool] = None,
                 roc_bars: Optional[int] = None,
                 threshold_atr: Optional[float] = None) -> pd.DataFrame:
    """Attach the momentum leg. Never modifies prices, never drops a row."""
    n = int(cfg.roc_bars if roc_bars is None else roc_bars)
    m = float(cfg.threshold_atr if threshold_atr is None else threshold_atr)
    if n not in cfg.roc_candidates:
        raise ValueError(f"roc_bars {n} aday kümesinde değil: {cfg.roc_candidates} "
                         f"(seçim Aşama 9'da)")
    if m not in cfg.threshold_candidates:
        raise ValueError(f"threshold_atr {m} aday kümesinde değil: {cfg.threshold_candidates} "
                         f"(seçim Aşama 9'da)")
    short_allowed = cfg.allow_short if allow_short is None else bool(allow_short)

    out = df.copy()
    close = pd.to_numeric(out["close"], errors="coerce").astype("float64")
    high = pd.to_numeric(out["high"], errors="coerce").astype("float64")
    low = pd.to_numeric(out["low"], errors="coerce").astype("float64")
    # ATR politikası: kolon YOKSA hesaplanır; VARSA **kullanılır**. Tamamen NaN
    # olsa bile yeniden HESAPLANMAZ — çünkü bu, guard'ı sessizce atlatmak olurdu
    # (test_guard_never_defaults_to_zero_or_pass tam olarak bunu yakalar).
    # Aşama 2 (regime) zaten `atr` kolonunu üretir; yani normal akışta burası
    # hiç hesap yapmaz ve tüm modüller AYNI ATR serisini paylaşır.
    if "atr" not in out.columns:
        out["atr"] = wilder_atr(high, low, close, cfg.atr_period).to_numpy()
    atr = pd.to_numeric(out["atr"], errors="coerce").astype("float64")

    base = close.shift(n)                       # close[t-n]: karar anında KAPALI
    with np.errstate(divide="ignore", invalid="ignore"):
        roc = close / base - 1.0
        atr_pct_at_base = atr / base            # payda: ATR / close[t-n]
        mom = roc / atr_pct_at_base

    # ---- guard (fail-closed) ----
    tradable = ~_bool_col(out, "non_tradable", default=False)
    ret_ok = _bool_col(out, "return_valid", default=True)
    position = pd.Series(np.arange(len(out)), index=out.index)
    warm = position < n
    atr_bad = ~(atr.notna() & (atr > 0))
    base_bad = ~(base.notna() & (base > 0))
    mom_bad = ~pd.Series(np.isfinite(mom.to_numpy(dtype="float64")), index=out.index)
    untradable = (~tradable) | (~ret_ok)

    invalid = (warm | atr_bad | base_bad | mom_bad | untradable).fillna(True).astype(bool)
    valid = ~invalid

    # Sebep atamasi ONCELIK sirasiyla ve TEK seferde yapilir: bir bar birden
    # fazla sebebe uyabilir ama yalnizca en temel olan raporlanir.
    reason = pd.Series("", index=out.index, dtype=object)
    taken = pd.Series(False, index=out.index)
    for mask, label in ((warm, "warmup"),
                        (atr_bad, "atr_invalid"),
                        (base_bad, "base_invalid"),
                        (mom_bad, "mom_not_finite"),
                        (~tradable, "non_tradable"),
                        (~ret_ok, "return_invalid")):
        pick = mask.fillna(False).astype(bool) & ~taken
        reason = reason.mask(pick, label)
        taken = taken | pick
    reason = reason.mask(invalid & (reason == ""), "unknown_guard")

    out["mom"] = pd.Series(mom, index=out.index).where(valid).to_numpy()
    out["momentum_valid"] = valid.to_numpy()
    out["momentum_invalid_reason"] = reason.to_numpy()

    state = pd.Series("invalid", index=out.index, dtype=object)
    state = state.mask(valid & (mom > m), "above")
    state = state.mask(valid & (mom < -m), "below")
    state = state.mask(valid & (mom >= -m) & (mom <= m), "neutral")
    out["momentum_state"] = state.to_numpy()

    out["momentum_ok"] = (valid & (mom > m)).fillna(False).to_numpy()
    if short_allowed:
        out["momentum_short_ok"] = (valid & (mom < -m)).fillna(False).to_numpy()
    else:
        # LONG-ONLY politika: short onayı HİÇ üretilmez (False, NaN değil)
        out["momentum_short_ok"] = False
    out.attrs["momentum_cfg"] = {"roc_bars": n, "threshold_atr": m,
                                 "atr_period": cfg.atr_period,
                                 "allow_short": short_allowed,
                                 "calibration_band": list(cfg.calibration_band)}
    return out


def add_signal_chain(df: pd.DataFrame, cfg: MomentumConfig = DEFAULT_MOMENTUM,
                     is_stock: bool = False,
                     allow_short: Optional[bool] = None) -> pd.DataFrame:
    """Combine every gate into ``long_final_ok`` / ``short_final_ok``.

    long_final_ok = rejim ∧ bağlam(BIST) ∧ tradable ∧ return_valid ∧ seviye ∧ momentum
    Bağlam bacağı yalnızca hisse sepetinde vardır; core varlıklarda ``longs_allowed``
    kolonu ya yoktur ya da ``context_not_applicable`` ile True'dur.
    """
    out = df.copy()
    short_allowed = (not is_stock) if allow_short is None else bool(allow_short)

    def _gate(name: str) -> pd.Series:
        if name == "~non_tradable":
            return ~_bool_col(out, "non_tradable", default=False)
        if name not in out.columns:
            # Kapı YOKSA fail-closed: False. Sessizce "geçti" sayılmaz.
            return pd.Series(False, index=out.index, dtype=bool)
        return _bool_col(out, name, default=False)

    acc = pd.Series(True, index=out.index, dtype=bool)
    counts: Dict[str, int] = {}
    for label, col in LONG_CHAIN:
        if label == "context" and not is_stock:
            counts["context_long"] = int(len(out))
            continue
        g = _gate(col)
        acc = acc & g
        counts[label] = int(acc.sum())
    out["long_final_ok"] = acc.to_numpy()
    out.attrs["long_chain_counts"] = counts

    if short_allowed:
        accs = pd.Series(True, index=out.index, dtype=bool)
        scounts: Dict[str, int] = {}
        for label, col in SHORT_CHAIN:
            g = _gate(col)
            accs = accs & g
            scounts[label] = int(accs.sum())
        out["short_final_ok"] = accs.to_numpy()
        out.attrs["short_chain_counts"] = scounts
    else:
        out["short_final_ok"] = False
        out.attrs["short_chain_counts"] = {}
    return out


def momentum_calibration(df: pd.DataFrame, cfg: MomentumConfig = DEFAULT_MOMENTUM,
                         name: str = "") -> Dict[str, Any]:
    """Geçiş oranı + bant kontrolü. Bant dışında TUNE ETMEZ, bayraklar."""
    n = len(df)
    valid = _bool_col(df, "momentum_valid", default=False)
    n_valid = int(valid.sum())
    long_ok = int(_bool_col(df, "momentum_ok", default=False).sum())
    short_ok = int(_bool_col(df, "momentum_short_ok", default=False).sum())
    lo, hi = cfg.calibration_band
    rate_valid = long_ok / n_valid if n_valid else 0.0
    rate_all = long_ok / n if n else 0.0
    in_band = bool(lo <= rate_valid <= hi)
    reasons = (df["momentum_invalid_reason"].astype(str).value_counts().to_dict()
               if "momentum_invalid_reason" in df.columns else {})
    states = (df["momentum_state"].astype(str).value_counts().to_dict()
              if "momentum_state" in df.columns else {})
    mom = pd.to_numeric(df["mom"] if "mom" in df.columns
                        else pd.Series(np.nan, index=df.index), errors="coerce").dropna()
    out: Dict[str, Any] = {
        "name": name,
        "bars": n,
        "momentum_valid_bars": n_valid,
        "momentum_valid_frac": round(n_valid / n, 4) if n else 0.0,
        "long_pass_bars": long_ok,
        "long_pass_rate_of_valid": round(rate_valid, 4),
        "long_pass_rate_of_all": round(rate_all, 4),
        "short_pass_bars": short_ok,
        "short_pass_rate_of_valid": round(short_ok / n_valid, 4) if n_valid else 0.0,
        "calibration_band": [float(lo), float(hi)],
        "in_band": in_band,
        "calibration_flag": "" if in_band else (
            f"DİKKAT: long geçiş oranı %{rate_valid * 100:.1f}, bant "
            f"[%{lo * 100:.0f}, %{hi * 100:.0f}] DIŞINDA. KABUL KRİTERİ 6 gereği "
            f"TUNE EDILMEDI - yalnizca bayraklandi. Olasi sebepler: rejim/volatilite "
            f"yapisi, n={cfg.roc_bars} ve m={cfg.threshold_atr} kombinasyonu bu varliga "
            f"uygun degil ya da guard cok fazla bar eliyor. Karar Asama 9'da, "
            f"yalnızca core varlıklar üzerinde ve küçük aday kümesiyle verilecek."),
        "invalid_reasons": {str(k): int(v) for k, v in reasons.items()},
        "states": {str(k): int(v) for k, v in states.items()},
        "mom_p05": round(float(mom.quantile(0.05)), 3) if len(mom) else None,
        "mom_p50": round(float(mom.median()), 3) if len(mom) else None,
        "mom_p95": round(float(mom.quantile(0.95)), 3) if len(mom) else None,
        "mom_abs_p50": round(float(mom.abs().median()), 3) if len(mom) else None,
    }
    return out


__all__ = ["add_momentum", "add_signal_chain", "momentum_calibration",
           "MOMENTUM_COLUMNS", "LONG_CHAIN", "SHORT_CHAIN"]
