"""Tests for AŞAMA 3 — structural levels and the frozen structural stop.

Her test bir KABUL KRİTERİNİ kilitler:
  1. swing onayı (k bar gecikme) — onaysız swing seviyede GÖRÜNMEZ
  2. Donchian(20) son 20 KAPANMIŞ barı kullanır — mevcut bar pencereye GİRMEZ
  3. return_valid=False / non_tradable barlar anchor OLAMAZ
  4. long stop = onaylı swing_low − buffer×ATR; short = swing_high + buffer×ATR
  5. stop DONDURULMUŞTUR — gevşetme/kaydırma StopImmutabilityError verir
  6. yeni indikatör YOK

Run: python3 -W ignore tests/test_levels.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from quant4h.config import (DEFAULT_LEVELS, DEFAULT_REGIME, LevelsConfig,  # noqa: E402
                            PER_ASSET_IN_SAMPLE_TUNING_ALLOWED, STOCK_ALLOW_SHORT, UTC)
from quant4h.data import schema  # noqa: E402
from quant4h.features.levels import (FrozenStop, StopImmutabilityError,  # noqa: E402
                                     add_donchian, add_levels, add_swings,
                                     anchor_eligible, count_events, plan_stop)
from quant4h.features.regime import label_regime, wilder_atr


def _frame(n: int = 900, seed: int = 1, start: str = "2023-01-02 00:00:00") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="4h", tz=UTC)
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.006, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.fmax(open_, close) * (1 + rng.uniform(0.001, 0.006, n))
    low = np.fmin(open_, close) * (1 - rng.uniform(0.001, 0.006, n))
    df = schema.coerce(pd.DataFrame({
        "symbol": "TEST", "timestamp_utc": idx, "open": open_, "high": high,
        "low": low, "close": close, "volume": rng.uniform(1e3, 1e4, n)}))
    df["return_valid"] = True
    df["non_tradable"] = False
    df["non_tradable_reason"] = ""
    df["atr"] = wilder_atr(df["high"], df["low"], df["close"], DEFAULT_REGIME.atr_period)
    return df


# --------------------------------------------------------------------------
# KRİTER 1 — swing onayı: k bar gecikme, onaysız swing GÖRÜNMEZ
# --------------------------------------------------------------------------

def test_unconfirmed_swing_is_invisible() -> None:
    cfg = LevelsConfig(swing_k=3)
    df = _frame(400, seed=5)
    p = 200
    peak = float(df["high"].max()) * 1.5
    assert int((df["high"] == peak).sum()) == 0, "spike benzersiz olmalı"
    df.loc[df.index[p], "high"] = peak
    out = add_swings(df, cfg)
    assert bool(out["swing_high_candidate"].iloc[p]) is True, "fraktal zirve bulunmalı"
    # p+k = 203 barı KAPANMADAN bilinemez -> t <= p+k için bu spike confirmed OLAMAZ
    for t in range(p, p + cfg.swing_k + 1):
        assert bool(out["swing_high_confirmed"].iloc[t]) is False or t <= p, t
        v = out["last_swing_high"].iloc[t]
        assert pd.isna(v) or float(v) != peak, f"onaysız swing t={t}'de sızdı"
    # t = p+k+1 = 204'te artık GÖRÜNÜR
    assert bool(out["swing_high_confirmed"].iloc[p + cfg.swing_k + 1]) is True
    assert float(out["last_swing_high"].iloc[p + cfg.swing_k + 1]) == peak
    # onay GECIKMESI tam olarak k+1 bar olmali
    conf_idx = out.index[out["swing_high_confirmed"] &
                          out["last_swing_high"].eq(peak)]
    assert len(conf_idx) and out.index.get_loc(conf_idx[0]) == p + cfg.swing_k + 1


def test_swing_requires_clean_neighbours() -> None:
    """Komşu bar bayraklıysa fraktal ONAYLANMAZ: eksik veriyle 'zirve' ilan
    etmek yanıltıcı olur (FLAG-ONLY felsefesi)."""
    cfg = LevelsConfig(swing_k=3)
    df = _frame(400, seed=6)
    p = 200
    df.loc[df.index[p], "high"] = float(df["high"].max()) * 1.5
    clean = add_swings(df, cfg)
    assert bool(clean["swing_high_confirmed"].iloc[p + cfg.swing_k + 1]) is True
    dirty = df.copy()
    dirty.loc[dirty.index[p + 1], "non_tradable"] = True       # komşu bayraklı
    out = add_swings(dirty, cfg)
    assert bool(out["swing_high_confirmed"].iloc[p + cfg.swing_k + 1]) is False


def test_swing_confirmed_count_never_exceeds_candidates() -> None:
    df = _frame(1200, seed=7)
    out = add_swings(df, DEFAULT_LEVELS)
    assert int(out["swing_high_confirmed"].sum()) <= int(out["swing_high_candidate"].sum())
    assert int(out["swing_low_confirmed"].sum()) <= int(out["swing_low_candidate"].sum())
    # ilk k+1 barda HİÇ onaylı swing olamaz
    assert int(out["swing_high_confirmed"].iloc[:DEFAULT_LEVELS.swing_k + 1].sum()) == 0


# --------------------------------------------------------------------------
# KRİTER 2 — Donchian: mevcut bar pencereye GİRMEZ
# --------------------------------------------------------------------------

def test_donchian_excludes_the_current_bar() -> None:
    cfg = LevelsConfig(donchian_period=20)
    df = _frame(300, seed=8)
    i = 150
    df.loc[df.index[i], "high"] = float(df["high"].max()) * 3.0     # dev spike
    out = add_donchian(df, cfg)
    # spike'ın KENDİ barında Donchian onu İÇERMEMELİ
    assert float(out["donchian_high"].iloc[i]) < float(df["high"].iloc[i])
    expected = float(df["high"].iloc[i - cfg.donchian_period:i].max())
    assert np.isclose(float(out["donchian_high"].iloc[i]), expected), (
        float(out["donchian_high"].iloc[i]), expected)
    # bir SONRAKI bar artık kapanmış olduğu için spike pencereye girer
    assert np.isclose(float(out["donchian_high"].iloc[i + 1]), float(df["high"].iloc[i]))


def test_donchian_window_is_exactly_n_closed_bars() -> None:
    cfg = LevelsConfig(donchian_period=20)
    df = _frame(200, seed=9)
    out = add_donchian(df, cfg)
    for i in (60, 100, 150):
        exp_hi = float(df["high"].iloc[i - cfg.donchian_period:i].max())
        exp_lo = float(df["low"].iloc[i - cfg.donchian_period:i].min())
        assert np.isclose(float(out["donchian_high"].iloc[i]), exp_hi), i
        assert np.isclose(float(out["donchian_low"].iloc[i]), exp_lo), i
    # Geçerlilik-oranı kapısı: Donchian, pencerede yeterli GEÇERLİ bar olduğu
    # anda üretilir (frac >= min_valid_frac_in_window = 0.90 -> i = 18). O ana
    # kadar NaN'dır. Hiçbir yerde 0'a ya da ilk bara SABİTLENMEMELİ.
    frac = out["donchian_valid_frac"]
    dh = out["donchian_high"]
    assert dh[frac < cfg.min_valid_frac_in_window].isna().all(), "yetersiz pencere NaN olmalı"
    assert frac.isna().iloc[0]                                   # bar 0'da pencere yok
    first_valid = int(frac[frac >= cfg.min_valid_frac_in_window].index[0])
    assert dh.iloc[:first_valid].isna().all()
    assert bool(dh.iloc[first_valid:].notna().any())
    assert not (dh.fillna(-1) == 0).any()
    # TAM pencere dolduğunda (i = N) değer son N KAPANMIŞ barın zirvesidir
    assert float(frac.iloc[cfg.donchian_period]) == 1.0
    exp_first = float(df["high"].iloc[0:cfg.donchian_period].max())
    assert np.isclose(float(dh.iloc[cfg.donchian_period]), exp_first)


# --------------------------------------------------------------------------
# KRİTER 3 — bayraklı barlar anchor OLAMAZ
# --------------------------------------------------------------------------

def test_flagged_bars_cannot_be_anchors() -> None:
    df = _frame(600, seed=10)
    i = 300
    df.loc[df.index[i], "low"] = float(df["low"].min()) * 0.5      # bariz dip
    df.loc[df.index[i], "return_valid"] = False                    # ama bayraklı
    out = add_swings(df, LevelsConfig(swing_k=3))
    assert bool(out["anchor_ok"].iloc[i]) is False
    assert bool(out["swing_low_candidate"].iloc[i]) is False
    trough = float(df["low"].iloc[i])
    assert float(out["last_swing_low"].iloc[i + 10]) != trough, "bayraklı bar seviyeye sızdı"

    df2 = df.copy()
    df2.loc[df2.index[i], "return_valid"] = True
    out2 = add_swings(df2, LevelsConfig(swing_k=3))
    assert bool(out2["swing_low_candidate"].iloc[i]) is True, "temiz bar anchor olabilmeli"


def test_non_tradable_and_halt_bars_are_excluded_from_donchian() -> None:
    cfg = LevelsConfig(donchian_period=20)
    df = _frame(400, seed=11)
    i = 250
    df.loc[df.index[i], "high"] = float(df["high"].max()) * 4.0
    df.loc[df.index[i], "non_tradable"] = True
    out = add_donchian(df, cfg)
    spike = float(df["high"].iloc[i])
    # bayraklı spike, SONRAKİ barların Donchian penceresine GİRMEMELİ.
    # (spike çok büyük olduğu için 'window < spike' tek başına zayıf bir test;
    #  asıl iddia spike DEĞERİNİN hiçbir Donchian barında görünmemesidir.)
    window = out["donchian_high"].iloc[i + 1:i + cfg.donchian_period]
    # bayraklı bar pencerede olduğu sürece geçerli oranı 19/20 = 0.95 olur ve
    # seviye spike'ı İÇERMEZ (spike maskelendiği için rolling onu görmez)
    win = window.dropna().to_numpy(dtype="float64")
    assert (win < spike).all(), "bayraklı bar Donchian'a sızdı"
    tail = out["donchian_high"].iloc[i + 1:]
    assert not np.isclose(tail.to_numpy(dtype="float64"), spike).any(), \
        "bayraklı spike değeri hiçbir Donchian barında görünmemeli"
    # kontrol: aynı spike BAYRAKSIZ olsaydı Donchian'a GİRMELİYDİ
    clean = df.copy()
    clean.loc[clean.index[i], "non_tradable"] = False
    out_clean = add_donchian(clean, cfg)
    assert np.isclose(out_clean["donchian_high"].iloc[i + 1], spike), \
        "temiz bar Donchian'a girmeli (test anlamlı olsun diye)"


def test_donchian_fails_closed_when_window_is_mostly_invalid() -> None:
    cfg = LevelsConfig(donchian_period=20, min_valid_frac_in_window=0.90)
    df = _frame(300, seed=12)
    df.loc[df.index[180:190], "non_tradable"] = True               # pencerenin yarısı bozuk
    out = add_donchian(df, cfg)
    bad = out["donchian_valid_frac"] < cfg.min_valid_frac_in_window
    assert bad.any()
    assert out.loc[bad, "donchian_high"].isna().all(), "yetersiz pencere NaN olmalı (fail-closed)"


def test_anchor_eligible_defaults_are_safe() -> None:
    df = _frame(50, seed=13)
    df.loc[df.index[5], "close"] = np.nan
    df.loc[df.index[6], "open"] = -1.0
    df.loc[df.index[7], "non_tradable"] = True
    df.loc[df.index[8], "return_valid"] = False
    df.loc[df.index[9], "halt_or_limit_flag"] = True
    ok = anchor_eligible(df)
    for i in (5, 6, 7, 8, 9):
        assert bool(ok.iloc[i]) is False, i
    assert bool(ok.iloc[20]) is True


# --------------------------------------------------------------------------
# KRİTER 4 — yapısal stop formülü ve yön kısıtı
# --------------------------------------------------------------------------

def test_long_stop_is_confirmed_swing_low_minus_buffer_atr() -> None:
    cfg = LevelsConfig(swing_k=3, stop_buffer_atr=1.0)
    df = _frame(600, seed=14)
    out = add_levels(df, cfg, allow_short=True)
    v = out[out["stop_valid_long"]].iloc[300]
    expected = float(v["last_swing_low"]) - cfg.stop_buffer_atr * float(v["atr"])
    assert np.isclose(float(v["stop_long"]), expected), (float(v["stop_long"]), expected)
    assert float(v["stop_long"]) < float(v["close"])
    assert np.isclose(float(v["stop_long_dist"]), float(v["close"]) - expected)
    assert np.isclose(float(v["stop_long_atr_mult"]), (float(v["close"]) - expected) / float(v["atr"]))


def test_short_stop_is_swing_high_plus_buffer_atr_and_policy_gated() -> None:
    cfg = LevelsConfig(swing_k=3, stop_buffer_atr=1.0)
    df = _frame(600, seed=15)
    core = add_levels(df, cfg, allow_short=True)
    v = core[core["stop_valid_short"]].iloc[300]
    expected = float(v["last_swing_high"]) + cfg.stop_buffer_atr * float(v["atr"])
    assert np.isclose(float(v["stop_short"]), expected)
    assert float(v["stop_short"]) > float(v["close"])
    # KARAR 4: hisseler LONG-ONLY -> short stop HİÇ üretilmez
    assert STOCK_ALLOW_SHORT is False
    stock = add_levels(df, cfg, allow_short=False)
    assert stock["stop_short"].isna().all()
    assert (stock["stop_valid_short"] == False).all()          # noqa: E712
    assert plan_stop(stock.iloc[300], "short", cfg, allow_short=False) is None


def test_stop_is_never_derived_from_the_entry_bar_itself() -> None:
    """Stop, giriş barının KENDİ high/low'undan türetilemez (look-ahead)."""
    cfg = LevelsConfig(swing_k=3, stop_buffer_atr=1.0)
    df = _frame(500, seed=16)
    i = 300
    df.loc[df.index[i], "low"] = float(df["low"].min()) * 0.5      # giriş barı dev dip
    out = add_levels(df, cfg, allow_short=True)
    stop = float(out["stop_long"].iloc[i])
    assert stop > float(df["low"].iloc[i]), "stop giriş barının kendi dibinden türetilmiş"
    # stop, giriş barının low'u değiştirilse bile AYNI kalmalı
    df2 = df.copy()
    df2.loc[df2.index[i], "low"] = float(df["low"].iloc[i]) * 1.3
    out2 = add_levels(df2, cfg, allow_short=True)
    assert np.isclose(float(out2["stop_long"].iloc[i]), stop)


def test_buffer_candidates_are_not_selected_now() -> None:
    """Kabul kriteri 4: buffer aday kümesi {0.5, 1.0, 1.5} SADECE Aşama 9'da
    test edilir. Şimdi seçim YOK; varsayılan 1.0 ve küme dışında buffer reddedilir."""
    assert DEFAULT_LEVELS.stop_buffer_atr == 1.0
    assert DEFAULT_LEVELS.stop_buffer_candidates == (0.5, 1.0, 1.5)
    df = _frame(200, seed=17)
    for b in (0.5, 1.0, 1.5):
        out = add_levels(df, DEFAULT_LEVELS, allow_short=True, buffer_atr=b)
        assert len(out) == len(df)
    try:
        add_levels(df, DEFAULT_LEVELS, buffer_atr=0.7)
    except ValueError as exc:
        assert "Aşama 9" in str(exc)
    else:
        raise AssertionError("küme dışı buffer reddedilmeli")
    # hisse başına in-sample tuning YASAK
    assert PER_ASSET_IN_SAMPLE_TUNING_ALLOWED is False


def test_no_stop_means_no_trade_fail_closed() -> None:
    cfg = LevelsConfig(swing_k=3)
    df = _frame(200, seed=18)
    out = add_levels(df, cfg, allow_short=True)
    head = out.iloc[:cfg.swing_k + 2]                    # henüz onaylı swing yok
    assert head["stop_valid_long"].sum() == 0
    for _, row in head.iterrows():
        assert plan_stop(row, "long", cfg) is None
    # ısınma döneminde seviye NaN'dır, 0'a veya fiyata SABİTLENMEZ
    assert out["stop_long"].iloc[:cfg.swing_k + 2].isna().all()


# --------------------------------------------------------------------------
# KRİTER 5 — stop dondurulmuş: gevşetme/kaydırma imkânsız
# --------------------------------------------------------------------------

def _a_stop(direction: str = "long", entry: float = 100.0, stop: float = 95.0) -> FrozenStop:
    return FrozenStop(direction=direction, initial_stop=stop, entry_price=entry,
                      planned_at_utc="2024-01-01T00:00:00+00:00", anchor="swing_low",
                      atr_at_plan=2.0, buffer_atr=1.0)


def test_frozen_stop_cannot_be_widened_or_moved_against() -> None:
    st = _a_stop("long", 100.0, 95.0)
    for fn, arg in (("widen", 90.0), ("move_against", 90.0), ("relax", None)):
        try:
            getattr(st, fn)() if arg is None else getattr(st, fn)(arg)
        except StopImmutabilityError:
            pass
        else:
            raise AssertionError(f"{fn} engellenmeliydi")
    assert st.initial_stop == 95.0 and st.active_stop == 95.0
    # frozen dataclass: __setattr__ kapalı (python seviyesinde de degistirilemez)
    try:
        st.initial_stop = 90.0                            # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("frozen dataclass alan atamasina izin VERMEMELI")
    assert st.initial_stop == 95.0


def test_short_stop_cannot_be_raised() -> None:
    st = _a_stop("short", 100.0, 105.0)
    try:
        st.tighten(110.0)
    except StopImmutabilityError:
        pass
    else:
        raise AssertionError("short stop YUKARI sıkılaştırılamaz")
    t = st.tighten(101.0)
    assert t.active_stop == 101.0 and t.initial_stop == 105.0
    assert t is not st


def test_tighten_preserves_the_initial_stop_and_returns_a_new_object() -> None:
    st = _a_stop("long", 100.0, 95.0)
    t = st.tighten(98.0, reason="trailing")
    assert t is not st
    assert t.initial_stop == 95.0 and t.current_stop == 98.0 and t.active_stop == 98.0
    assert st.active_stop == 95.0, "orijinal nesne DEĞİŞMEMELİ"
    try:
        t.tighten(94.0)
    except StopImmutabilityError:
        pass
    else:
        raise AssertionError("initial_stop'un altına inilemez")


def test_plan_stop_is_a_pure_deterministic_function() -> None:
    """Aynı girdi -> aynı çıktı, yan etki yok. Bu, 'stop girişten önce belli ve
    dondurulmuş' garantisinin hesaplanabilir kısmıdır."""
    cfg = LevelsConfig(swing_k=3, stop_buffer_atr=1.0)
    df = _frame(500, seed=19)
    out = add_levels(df, cfg, allow_short=True)
    row = out[out["stop_valid_long"]].iloc[200]
    a = plan_stop(row, "long", cfg)
    b = plan_stop(row, "long", cfg)
    assert a is not None and b is not None
    assert a == b
    snapshot = out.copy(deep=True)
    plan_stop(row, "long", cfg)
    pd.testing.assert_frame_equal(out, snapshot)
    assert a.risk_per_unit == abs(a.entry_price - a.initial_stop)
    assert np.isfinite(a.stop_atr_multiple)


def test_frozen_stop_rejects_nonsensical_geometry() -> None:
    for kwargs in ({"direction": "long", "initial_stop": 105.0, "entry_price": 100.0},
                   {"direction": "short", "initial_stop": 95.0, "entry_price": 100.0},
                   {"direction": "sideways", "initial_stop": 95.0, "entry_price": 100.0},
                   {"direction": "long", "initial_stop": float("nan"), "entry_price": 100.0}):
        try:
            FrozenStop(planned_at_utc="x", anchor="swing_low", atr_at_plan=1.0,
                       buffer_atr=1.0, **kwargs)
        except (ValueError, StopImmutabilityError):
            continue
        raise AssertionError(f"reddedilmeliydi: {kwargs}")


# --------------------------------------------------------------------------
# KRİTER 6 — yeni indikatör YOK + look-ahead yok
# --------------------------------------------------------------------------

def test_no_forbidden_indicator_in_levels_module() -> None:
    import dataclasses
    names = " ".join(f.name.lower() for f in dataclasses.fields(LevelsConfig))
    for bad in ("adx", "hurst", "chopp", "bollinger", "bb_", "ichimoku",
                "supertrend", "keltner", "vwap", "profile", "orderblock"):
        assert bad not in names, bad
    import ast
    import re
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                        "src", "quant4h", "features", "levels.py")
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    # Yalnızca ÇALIŞAN KOD taranır: docstring ve yorumlar çıkarılır. Aksi hâlde
    # "yasaklı indikatör yok" diyen bir cümlenin kendisi yasaklı kelimeyi içerir
    # ve test kendi dokümantasyonuna takılır.
    tree = ast.parse(raw)
    doc_spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ds = ast.get_docstring(node, clean=False)
            if ds:
                i = raw.find(ds)
                if i >= 0:
                    doc_spans.append((i, i + len(ds)))
    code_chars = []
    for i, line in enumerate(raw.splitlines(keepends=True)):
        stripped = line.split("#", 1)[0]
        code_chars.append(stripped)
    code = "".join(code_chars).lower()
    for lo, hi in sorted(doc_spans, reverse=True):
        code = code[:lo] + " " * (hi - lo) + code[hi:]
    for bad in ("rsi", "macd", "stochastic", "ichimoku", "supertrend", "keltner",
                "bollinger", "adx", "hurst", "choppiness", "vwap", "poc",
                "order_block", "fractal_level_lib"):
        assert not re.search(rf"\b{bad}\b", code), f"{bad} levels.py KODUNDA geçmemeli"


def test_levels_have_no_lookahead() -> None:
    df = _frame(1200, seed=20)
    full = add_levels(df, DEFAULT_LEVELS, allow_short=True)
    cut = add_levels(df.iloc[:-300].copy(), DEFAULT_LEVELS, allow_short=True)
    n = len(cut)
    cols = ["last_swing_high", "last_swing_low", "donchian_high", "donchian_low",
            "stop_long", "stop_short", "stop_long_atr_mult", "highest_swing_high"]
    for c in cols:
        a = full[c].iloc[:n].to_numpy(dtype="float64")
        b = cut[c].to_numpy(dtype="float64")
        assert np.allclose(a, b, equal_nan=True), c
    for c in ("swing_high_confirmed", "swing_low_confirmed", "stop_valid_long",
              "stop_valid_short", "anchor_ok"):
        a = full[c].iloc[:n].astype(bool).to_numpy()
        b = cut[c].astype(bool).to_numpy()
        assert (a == b).all(), c


def test_add_levels_never_changes_prices_or_row_count() -> None:
    df = _frame(700, seed=21)
    before = df[["open", "high", "low", "close", "volume"]].to_numpy().copy()
    out = add_levels(df, DEFAULT_LEVELS, allow_short=True)
    assert len(out) == len(df)
    assert np.allclose(out[["open", "high", "low", "close", "volume"]].to_numpy(), before)
    assert list(out["timestamp_utc"]) == list(df["timestamp_utc"])


def test_count_events_reports_distances_and_touches() -> None:
    df = label_regime(_frame(900, seed=22))
    out = add_levels(df, DEFAULT_LEVELS, allow_short=True)
    ev = count_events(out, DEFAULT_LEVELS)
    assert ev["bars"] == 900
    assert ev["swing_high_confirmed"] > 0 and ev["swing_low_confirmed"] > 0
    assert ev["donchian_available_frac"] > 0.5
    assert "long" in ev["stop_distance"]
    d = ev["stop_distance"]["long"]
    assert d["median_atr_mult"] > 0 and d["median_pct_price"] > 0
    assert ev["stop_valid_long"] > 0
    assert ev["breakout_up"] >= 0 and ev["touch_last_swing_low"] >= 0


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
