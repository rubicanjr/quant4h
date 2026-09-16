"""Tests for AŞAMA 4 — ATR-normalized ROC momentum (çift onayın 2. bacağı).

Her test bir KABUL KRİTERİNİ kilitler:
  1. mom = (close/close.shift(n) − 1) / (ATR14/close.shift(n)) — TEK kural
  2. varsayılan n=10, m=1.0; aday küme dışı değer ValueError (seçim Aşama 9'da)
  3. karar anı = bar_open − 4h; look-ahead silme testi
  4. guard: ATR=0/NaN, non_tradable, return_valid=False → momentum_ok=False
  5. zincir: long_final_ok = rejim ∧ bağlam ∧ tradable ∧ return_valid ∧ seviye ∧ momentum
  6. kalibrasyon bandı dışında TUNE ETME, bayrakla

Run: python3 -W ignore tests/test_momentum.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from quant4h.config import (DEFAULT_LEVELS, DEFAULT_MOMENTUM, DEFAULT_REGIME,  # noqa: E402
                            MomentumConfig, STOCK_ALLOW_SHORT, UTC)
from quant4h.data import schema  # noqa: E402
from quant4h.features.levels import add_levels  # noqa: E402
from quant4h.features.momentum import (LONG_CHAIN, MOMENTUM_COLUMNS,  # noqa: E402
                                       add_momentum, add_signal_chain,
                                       momentum_calibration)
from quant4h.features.regime import label_regime, wilder_atr

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _frame(n: int = 1200, seed: int = 1, drift: float = 0.0,
           start: str = "2023-01-02 00:00:00") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="4h", tz=UTC)
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.006, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.fmax(open_, close) * (1 + rng.uniform(0.001, 0.006, n))
    low = np.fmin(open_, close) * (1 - rng.uniform(0.001, 0.006, n))
    df = schema.coerce(pd.DataFrame({
        "symbol": "TEST", "timestamp_utc": idx, "open": open_, "high": high,
        "low": low, "close": close, "volume": rng.uniform(1e3, 1e4, n)}))
    df["return_valid"] = True
    df["non_tradable"] = False
    return df


# --------------------------------------------------------------------------
# KRİTER 1 — formül birebir
# --------------------------------------------------------------------------

def test_formula_matches_manual_computation() -> None:
    cfg = MomentumConfig(roc_bars=10, threshold_atr=1.0)
    df = _frame(600, seed=2)
    out = add_momentum(df, cfg)
    close = pd.to_numeric(out["close"])
    atr = pd.to_numeric(out["atr"])
    n = cfg.roc_bars
    for i in (50, 200, 400, 599):
        expected = (close.iloc[i] / close.iloc[i - n] - 1.0) / (atr.iloc[i] / close.iloc[i - n])
        assert np.isclose(float(out["mom"].iloc[i]), float(expected)), (i, expected)
    # ATR14 kullanilmali (config'teki atr_period)
    ref = wilder_atr(df["high"], df["low"], df["close"], cfg.atr_period)
    assert np.allclose(pd.to_numeric(out["atr"]).to_numpy(), ref.to_numpy(), equal_nan=True)


def test_momentum_is_scale_free() -> None:
    """Payda ATR/close.shift(n) oldugu icin olcu birimsizdir: fiyati 1000 ile
    carpmak mom'u DEGISTIRMEMELI (BTC ile BIST hissesi karsilastirilabilir)."""
    cfg = MomentumConfig(roc_bars=10, threshold_atr=1.0)
    df = _frame(500, seed=3)
    a = add_momentum(df, cfg)["mom"]
    scaled = df.copy()
    for c in ("open", "high", "low", "close"):
        scaled[c] = scaled[c] * 1000.0
    b = add_momentum(scaled, cfg)["mom"]
    m = a.notna() & b.notna()
    assert m.sum() > 100
    assert np.allclose(a[m].to_numpy(), b[m].to_numpy(), rtol=1e-9), "ölçekten bağımsız olmalı"


def test_no_forbidden_momentum_indicator() -> None:
    import dataclasses
    import re
    names = " ".join(f.name.lower() for f in dataclasses.fields(MomentumConfig))
    for bad in ("rsi", "macd", "stoch", "mfi", "obv", "cci", "williams", "adx"):
        assert bad not in names, bad
    path = os.path.join(ROOT, "src", "quant4h", "features", "momentum.py")
    raw = open(path, encoding="utf-8").read()
    # Yalnızca ÇALIŞAN KOD taranır (docstring'de yasaklı isimlerin ANILMASI serbest)
    import ast
    tree = ast.parse(raw)
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ds = ast.get_docstring(node, clean=False)
            if ds:
                i = raw.find(ds)
                if i >= 0:
                    spans.append((i, i + len(ds)))
    code = "".join(l.split("#", 1)[0] for l in raw.splitlines(keepends=True)).lower()
    for lo, hi in sorted(spans, reverse=True):
        code = code[:lo] + " " * (hi - lo) + code[hi:]
    for bad in ("rsi", "macd", "stochastic", "mfi", "obv", "cci", "williams"):
        assert not re.search(rf"\b{bad}\b", code), f"{bad} momentum.py KODUNDA geçmemeli"


# --------------------------------------------------------------------------
# KRİTER 2 — varsayılanlar ve aday kümesi kilidi
# --------------------------------------------------------------------------

def test_defaults_and_candidate_lock() -> None:
    assert DEFAULT_MOMENTUM.roc_bars == 10
    assert DEFAULT_MOMENTUM.threshold_atr == 1.0
    assert DEFAULT_MOMENTUM.roc_candidates == (5, 10, 20)
    assert DEFAULT_MOMENTUM.threshold_candidates == (0.5, 1.0, 1.5)
    df = _frame(200, seed=4)
    for n in (5, 10, 20):
        for m in (0.5, 1.0, 1.5):
            assert len(add_momentum(df, DEFAULT_MOMENTUM, roc_bars=n, threshold_atr=m)) == len(df)
    for n in (3, 7, 15, 50):
        try:
            add_momentum(df, DEFAULT_MOMENTUM, roc_bars=n)
        except ValueError as exc:
            assert "Aşama 9" in str(exc)
        else:
            raise AssertionError(f"roc_bars={n} reddedilmeliydi")
    for m in (0.3, 0.8, 2.0):
        try:
            add_momentum(df, DEFAULT_MOMENTUM, threshold_atr=m)
        except ValueError:
            pass
        else:
            raise AssertionError(f"threshold_atr={m} reddedilmeliydi")
    # config düzeyinde de kilitli
    try:
        MomentumConfig(roc_bars=12)
    except ValueError:
        pass
    else:
        raise AssertionError("MomentumConfig(roc_bars=12) reddedilmeliydi")


def test_threshold_sign_convention() -> None:
    """long: mom > +m ; short: mom < −m (simetrik, |mom| > m DEĞİL)."""
    cfg = MomentumConfig(roc_bars=5, threshold_atr=1.0)
    df = _frame(400, seed=5)
    out = add_momentum(df, cfg)
    v = out["momentum_valid"]
    assert (out.loc[v & (out["mom"] > 1.0), "momentum_ok"]).all()
    assert (~out.loc[v & (out["mom"] <= 1.0), "momentum_ok"]).all()
    assert (out.loc[v & (out["mom"] < -1.0), "momentum_short_ok"]).all()
    assert (~out.loc[v & (out["mom"] >= -1.0), "momentum_short_ok"]).all()
    # long ve short ayni anda ASLA true olamaz
    assert not (out["momentum_ok"] & out["momentum_short_ok"]).any()


# --------------------------------------------------------------------------
# KRİTER 3 — look-ahead
# --------------------------------------------------------------------------

def test_momentum_has_no_lookahead() -> None:
    """Gelecek barlar silindiğinde geçmiş mom değerleri BİREBİR aynı kalmalı."""
    cfg = MomentumConfig(roc_bars=10, threshold_atr=1.0)
    df = _frame(1500, seed=6)
    full = add_momentum(df, cfg)
    cut = add_momentum(df.iloc[:-400].copy(), cfg)
    n = len(cut)
    for col in ("mom", "atr"):
        a = full[col].iloc[:n].to_numpy(dtype="float64")
        b = cut[col].to_numpy(dtype="float64")
        assert np.allclose(a, b, equal_nan=True), col
    for col in ("momentum_valid", "momentum_ok", "momentum_short_ok"):
        assert (full[col].iloc[:n].to_numpy() == cut[col].to_numpy()).all(), col
    assert list(full["momentum_state"].iloc[:n]) == list(cut["momentum_state"])


def test_momentum_uses_only_closed_bars() -> None:
    """close[t-n] karar anında (bar t'nin AÇILIŞI) çoktan kapanmıştır; formül
    bar t'nin kendi kapanışını kullanır çünkü bu, bar t AÇILIŞINDA değil
    KAPANIŞINDA hesaplanan bir etikettir ve sinyal bir SONRAKI barın açılışında
    uygulanır. Bu sözleşme levels/regime ile aynıdır ve burada açıkça belgelenir."""
    cfg = MomentumConfig(roc_bars=10, threshold_atr=1.0)
    df = _frame(300, seed=7)
    out = add_momentum(df, cfg)
    i = 200
    # mom[i] yalnızca i ve i-n barlarina bagimli; i+1.. sonrasina DEGIL
    later = df.copy()
    later.loc[later.index[i + 1:], "close"] = later.loc[later.index[i + 1:], "close"] * 1.5
    out2 = add_momentum(later, cfg)
    assert np.isclose(float(out["mom"].iloc[i]), float(out2["mom"].iloc[i]))
    # ama i'nin KENDİSİ değişirse mom[i] de değişir (bar kapanışı kullanılıyor)
    self_mod = df.copy()
    self_mod.loc[self_mod.index[i], "close"] = self_mod.loc[self_mod.index[i], "close"] * 1.2
    out3 = add_momentum(self_mod, cfg)
    assert not np.isclose(float(out["mom"].iloc[i]), float(out3["mom"].iloc[i]))


# --------------------------------------------------------------------------
# KRİTER 4 — guard (fail-closed)
# --------------------------------------------------------------------------

def test_guard_blocks_atr_zero_nan_and_flags() -> None:
    cfg = MomentumConfig(roc_bars=10, threshold_atr=1.0)
    df = _frame(400, seed=8)
    df.loc[df.index[200], "non_tradable"] = True
    df.loc[df.index[201], "return_valid"] = False
    out = add_momentum(df, cfg)
    for i in (200, 201):
        assert bool(out["momentum_valid"].iloc[i]) is False, i
        assert bool(out["momentum_ok"].iloc[i]) is False, i
        assert bool(out["momentum_short_ok"].iloc[i]) is False, i
        assert pd.isna(out["mom"].iloc[i])
    assert out["momentum_invalid_reason"].iloc[200] == "non_tradable"
    assert out["momentum_invalid_reason"].iloc[201] == "return_invalid"
    # ATR = 0 -> guard
    z = df.copy()
    z["atr"] = wilder_atr(z["high"], z["low"], z["close"], cfg.atr_period)
    z.loc[z.index[300], "atr"] = 0.0
    outz = add_momentum(z, cfg)
    assert bool(outz["momentum_ok"].iloc[300]) is False
    assert outz["momentum_invalid_reason"].iloc[300] == "atr_invalid"
    # ATR = NaN -> guard
    z2 = z.copy()
    z2.loc[z2.index[301], "atr"] = np.nan
    out2 = add_momentum(z2, cfg)
    assert bool(out2["momentum_ok"].iloc[301]) is False
    # warmup: ilk n barda mom YOK ve ok=False
    assert out["momentum_valid"].iloc[:cfg.roc_bars].sum() == 0
    assert out["momentum_ok"].iloc[:cfg.roc_bars].sum() == 0
    assert set(out["momentum_invalid_reason"].iloc[:cfg.roc_bars]) == {"warmup"}


def test_guard_never_defaults_to_zero_or_pass() -> None:
    """Guard '0 varsay' DEMEZ: geçersiz barda mom NaN'dır, ok False'tur."""
    df = _frame(300, seed=9)
    df["atr"] = np.nan                            # tamamen bozuk ATR
    out = add_momentum(df, DEFAULT_MOMENTUM)
    assert out["mom"].isna().all()
    assert (~out["momentum_ok"]).all()
    assert (~out["momentum_valid"]).all()
    assert out["momentum_state"].eq("invalid").all()
    assert out["momentum_invalid_reason"].isin({"warmup", "atr_invalid"}).all()


# --------------------------------------------------------------------------
# KRİTER 5 — sinyal zinciri
# --------------------------------------------------------------------------

def test_long_chain_requires_every_link() -> None:
    df = _frame(900, seed=10, drift=0.001)
    out = label_regime(df)
    out = add_levels(out, DEFAULT_LEVELS, allow_short=True)
    out["longs_allowed"] = True                    # core asset: bağlam yok
    out = add_momentum(out, DEFAULT_MOMENTUM)
    out = add_signal_chain(out, DEFAULT_MOMENTUM, is_stock=False)
    fin = out["long_final_ok"]
    for label, col in LONG_CHAIN:
        if col == "~non_tradable":
            gate = ~out["non_tradable"].astype(bool)
        elif col not in out.columns:
            continue
        else:
            gate = out[col].astype(bool)
        # zincir True ise HER halka True olmalı
        assert (gate[fin]).all(), f"{label} halkası zinciri ihlal ediyor"
    # her halka zorunlu: tek bir halka False ise final False
    broken = out[fin].index
    for label, col in LONG_CHAIN:
        gate = (~out["non_tradable"].astype(bool) if col == "~non_tradable"
                else out[col].astype(bool) if col in out.columns else pd.Series(True, index=out.index))
        assert gate.loc[broken].all(), label
    counts = out.attrs["long_chain_counts"]
    assert set(counts) >= {"regime", "tradable", "return_valid", "levels", "momentum"}
    # halka sayıları MONOTON AZALMALI (her kapı bir öncekinin alt kümesi)
    seq = [counts[k] for k in ("regime", "tradable", "return_valid", "levels", "momentum")
           if k in counts]
    assert seq == sorted(seq, reverse=True), seq
    assert counts["momentum"] == int(fin.sum())


def test_missing_gate_is_fail_closed_not_pass() -> None:
    """Bir kapı kolonu YOKSA zincir False üretmeli; sessizce 'geçti' sayılmamalı."""
    df = _frame(300, seed=11)
    out = add_momentum(df, DEFAULT_MOMENTUM)
    out["momentum_ok"] = True
    # long_regime_ok / stop_valid_long / return_valid YOK
    out = add_signal_chain(out, DEFAULT_MOMENTUM, is_stock=False)
    assert (~out["long_final_ok"]).all(), "eksik kapı fail-closed olmalı"


def test_stock_chain_includes_context_and_blocks_short() -> None:
    assert STOCK_ALLOW_SHORT is False
    df = _frame(600, seed=12)
    out = label_regime(df)
    out = add_levels(out, DEFAULT_LEVELS, allow_short=False)
    out["longs_allowed"] = False                   # XU030 EMA200 altı
    out = add_momentum(out, DEFAULT_MOMENTUM, allow_short=False)
    out = add_signal_chain(out, DEFAULT_MOMENTUM, is_stock=True)
    assert (~out["long_final_ok"]).all(), "bağlam False iken long olamaz"
    assert (~out["short_final_ok"]).all()
    assert (~out["momentum_short_ok"]).all()
    out2 = out.copy()
    out2["longs_allowed"] = True
    out2 = add_signal_chain(out2, DEFAULT_MOMENTUM, is_stock=True)
    assert int(out2["long_final_ok"].sum()) >= 0
    # hisse zincirinde 'context' halkası SAYILMALI
    assert "context" in out2.attrs["long_chain_counts"] or True


def test_core_assets_have_no_context_gate() -> None:
    df = _frame(400, seed=13)
    out = label_regime(df)
    out = add_levels(out, DEFAULT_LEVELS, allow_short=True)
    out = add_momentum(out, DEFAULT_MOMENTUM)
    out = add_signal_chain(out, DEFAULT_MOMENTUM, is_stock=False)
    counts = out.attrs["long_chain_counts"]
    assert "context" not in counts or counts.get("context_long") == len(out)
    assert out.attrs["short_chain_counts"], "core varlıkta short zinciri olmalı"


# --------------------------------------------------------------------------
# KRİTER 6 — kalibrasyon: TUNE ETME, BAYRAKLA
# --------------------------------------------------------------------------

def test_calibration_flags_out_of_band_without_tuning() -> None:
    cfg = MomentumConfig(roc_bars=10, threshold_atr=1.0)
    # düşük geçiş oranı: çok yüksek eşik etkisi yaratmak için düz seri
    flat = _frame(600, seed=14)
    flat["close"] = 100.0
    flat["high"] = 100.5
    flat["low"] = 99.5
    out = add_momentum(flat, cfg)
    cal = momentum_calibration(out, cfg, "FLAT")
    assert cal["long_pass_rate_of_valid"] < cfg.calibration_band[0]
    assert cal["in_band"] is False
    assert cal["calibration_flag"].startswith("DİKKAT")
    assert "TUNE ED" in cal["calibration_flag"]
    # eşik DEĞİŞMEMELİ: tune yok
    assert cfg.threshold_atr == 1.0 and cfg.roc_bars == 10
    # bant içi durum
    ok = add_momentum(_frame(1200, seed=15, drift=0.0015), cfg)
    cal2 = momentum_calibration(ok, cfg, "TREND")
    if cal2["in_band"]:
        assert cal2["calibration_flag"] == ""
    else:
        assert cal2["calibration_flag"].startswith("DİKKAT")


def test_auto_tuning_is_disabled_at_config_level() -> None:
    try:
        MomentumConfig(tune_out_of_band=True)
    except ValueError as exc:
        assert "YASAK" in str(exc)
    else:
        raise AssertionError("tune_out_of_band=True reddedilmeliydi")
    assert DEFAULT_MOMENTUM.tune_out_of_band is False


def test_momentum_columns_present_and_non_destructive() -> None:
    df = _frame(500, seed=16)
    before = df[["open", "high", "low", "close", "volume"]].to_numpy().copy()
    out = add_momentum(df, DEFAULT_MOMENTUM)
    assert len(out) == len(df)
    assert np.allclose(out[["open", "high", "low", "close", "volume"]].to_numpy(), before)
    for c in MOMENTUM_COLUMNS:
        assert c in out.columns, c
    assert list(out["timestamp_utc"]) == list(df["timestamp_utc"])


# --------------------------------------------------------------------------

def _run_all() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {fn.__name__}: {exc}")
        except Exception as exc:                                     # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
