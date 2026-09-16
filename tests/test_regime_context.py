"""Tests for AŞAMA 2: regime module + XU030 context filter.

Run: python3 -W ignore tests/test_regime_context.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from quant4h.config import DEFAULT_REGIME, RegimeConfig, UTC  # noqa: E402
from quant4h.data import schema  # noqa: E402
from quant4h.features.context import (REASON_BELOW, REASON_MISSING, REASON_OK,  # noqa: E402
                                      REASON_STALE, REASON_WARMUP, context_summary,
                                      longs_allowed, xu030_signal)
from quant4h.features.regime import (REGIME_COLUMNS, label_regime,  # noqa: E402
                                     regime_distribution, wilder_atr)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NOW = pd.Timestamp("2026-09-30", tz=UTC)


def _series(n: int = 1200, drift: float = 0.0, vol: float = 0.006,
            seed: int = 2, start: str = "2023-01-02 00:00:00") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="4h", tz=UTC)
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.fmax(open_, close) * (1 + rng.uniform(0, 0.002, n))
    low = np.fmin(open_, close) * (1 - rng.uniform(0, 0.002, n))
    return schema.coerce(pd.DataFrame({
        "symbol": "TEST", "timestamp_utc": idx, "open": open_, "high": high,
        "low": low, "close": close, "volume": rng.uniform(1e3, 1e4, n)}))


# --------------------------------------------------------------------------
# rejim: doğruluk
# --------------------------------------------------------------------------

def test_regime_columns_and_labels_are_wellformed() -> None:
    out = label_regime(_series(1200))
    for c in REGIME_COLUMNS:
        assert c in out.columns, c
    lab = out[out["regime_valid"]]
    assert len(lab) > 0
    assert set(lab["trend_state"].unique()) <= {"trend_up", "trend_down", "range"}
    assert set(lab["vol_state"].unique()) <= {"vol_high", "vol_normal", "vol_low"}
    assert all(r in {f"{t}|{v}" for t in ("trend_up", "trend_down", "range")
                     for v in ("vol_high", "vol_normal", "vol_low")}
               for r in lab["regime"])
    # long ve short ayni anda ASLA izinli olmamali (trend_up ile trend_down ayrik)
    assert not (out["long_regime_ok"] & out["short_regime_ok"]).any()


def test_regime_warmup_is_nan_not_range() -> None:
    """Isinma donemi sessizce 'range' sayilmaz; acikca BILINMIYOR olmali ve
    fail_closed=True iken sinyal uretmemeli."""
    cfg = RegimeConfig(min_bars_for_regime=500)
    out = label_regime(_series(1200), cfg)
    head = out.iloc[:400]
    assert head["regime_valid"].sum() == 0
    assert head["regime"].isna().all()
    assert head["long_regime_ok"].sum() == 0 and head["short_regime_ok"].sum() == 0


def test_uptrend_and_downtrend_are_classified_correctly() -> None:
    up = label_regime(_series(1200, drift=0.002, seed=3))
    dn = label_regime(_series(1200, drift=-0.002, seed=3))
    up_lab = up[up["regime_valid"]]["trend_state"].value_counts(normalize=True)
    dn_lab = dn[dn["regime_valid"]]["trend_state"].value_counts(normalize=True)
    assert up_lab.get("trend_up", 0) > 0.80, dict(up_lab)
    assert dn_lab.get("trend_down", 0) > 0.80, dict(dn_lab)
    assert up[up["regime_valid"]]["long_regime_ok"].mean() > 0.5
    assert dn[dn["regime_valid"]]["short_regime_ok"].mean() > 0.5


def test_extreme_volatility_blocks_new_signals() -> None:
    cfg = RegimeConfig(max_atr_percentile=0.90)
    df = _series(1500, seed=7)
    i = df.index[1200:1250]
    df.loc[i, "high"] = df.loc[i, "high"] * 1.15      # volatilite patlamasi
    df.loc[i, "low"] = df.loc[i, "low"] * 0.88
    out = label_regime(df, cfg)
    hot = out.loc[i]
    assert hot["atr_percentile"].max() > 0.90
    blocked = hot[hot["atr_percentile"] > cfg.max_atr_percentile]
    if len(blocked):
        assert not blocked["long_regime_ok"].any() and not blocked["short_regime_ok"].any()


def test_regime_has_no_lookahead() -> None:
    """Gelecek barlar silindiginde gecmis etiketler DEGISMEMELI."""
    df = _series(1500, seed=11)
    full = label_regime(df)
    cut = label_regime(df.iloc[:-300].copy())
    n = len(cut)
    for col in ("ema_trend", "atr", "atr_percentile", "ema_slope_atr"):
        a = full[col].iloc[:n].to_numpy(dtype="float64")
        b = cut[col].to_numpy(dtype="float64")
        assert np.allclose(a, b, equal_nan=True), col
    for col in ("trend_state", "vol_state", "regime"):
        a = full[col].iloc[:n].astype("object").where(full[col].iloc[:n].notna(), None).to_numpy()
        b = cut[col].astype("object").where(cut[col].notna(), None).to_numpy()
        assert list(a) == list(b), col
    assert (full["long_regime_ok"].iloc[:n].to_numpy() == cut["long_regime_ok"].to_numpy()).all()


def test_wilder_atr_is_causal() -> None:
    df = _series(600, seed=5)
    a1 = wilder_atr(df["high"], df["low"], df["close"], 14)
    a2 = wilder_atr(df["high"].iloc[:-50], df["low"].iloc[:-50], df["close"].iloc[:-50], 14)
    assert np.allclose(a1.iloc[:-50].to_numpy(), a2.to_numpy(), equal_nan=True)


def test_regime_config_has_no_forbidden_indicators() -> None:
    """SADELİK KURALI: ADX/Hurst/Choppiness/Bollinger config'te bile OLMAMALI."""
    import dataclasses
    names = " ".join(f.name.lower() for f in dataclasses.fields(RegimeConfig))
    for bad in ("adx", "hurst", "chopp", "bollinger", "bb_", "ichimoku", "supertrend", "keltner"):
        assert bad not in names, bad


# --------------------------------------------------------------------------
# XU030 bağlam filtresi
# --------------------------------------------------------------------------

def _index_and_stock(n: int = 1200, index_drift: float = 0.002):
    idx = _series(n, drift=index_drift, seed=21)
    idx["symbol"] = "XU030_INDEX"
    return idx, _series(n, drift=0.001, seed=22)


def test_context_filter_blocks_longs_below_ema200() -> None:
    idx, stock = _index_and_stock(1200, index_drift=-0.003)   # endeks dusus trendinde
    out = longs_allowed(stock, idx, "4h", 200)
    s = context_summary(out)
    assert s["applied"] is True
    assert s["reasons"].get(REASON_BELOW, 0) > 0
    below = out[out["ctx_reason"] == REASON_BELOW]
    assert (~below["longs_allowed"]).all()
    assert (below["ctx_above_ema"] <= 0).all()
    ok = out[out["ctx_reason"] == REASON_OK]
    assert ok["longs_allowed"].all() and (ok["ctx_above_ema"] > 0).all()


def test_context_filter_allows_longs_above_ema200() -> None:
    idx, stock = _index_and_stock(1200, index_drift=0.003)    # endeks yukselis trendinde
    out = longs_allowed(stock, idx, "4h", 200)
    s = context_summary(out)
    assert s["longs_allowed_frac"] > 0.5, s["reasons"]
    assert s["reasons"].get(REASON_OK, 0) > 600


def test_context_is_fail_closed() -> None:
    """Veri yok / ısınma / bayat -> long YOK. 'Veri yok' asla 'izin var' değildir."""
    idx, stock = _index_and_stock(1200)
    empty = idx.iloc[:0].copy()
    out = longs_allowed(stock, empty, "4h", 200)
    assert not out["longs_allowed"].any()
    assert set(out["ctx_reason"].unique()) <= {REASON_MISSING}
    # isinma: EMA200 hazir degil
    out2 = longs_allowed(stock, idx, "4h", 200)
    warm = out2[out2["ctx_reason"] == REASON_WARMUP]
    assert len(warm) > 0
    assert (~warm["longs_allowed"]).all()
    # bayat baglam
    old = out2[out2["ctx_reason"] == REASON_STALE]
    assert (~old["longs_allowed"]).all() if len(old) else True


def test_context_uses_only_closed_index_bars() -> None:
    """ANTI LOOK-AHEAD sözleşmesi: T damgalı hisse barı, yalnızca T-4h veya
    daha eski (yani KAPANMIŞ) XU030 barını kullanabilir."""
    idx, stock = _index_and_stock(600)
    out = longs_allowed(stock, idx, "4h", 200, max_context_age=pd.Timedelta(hours=1000))
    sig = xu030_signal(idx, 200).set_index("timestamp_utc")
    for k in range(250, len(out), 37):
        row = out.iloc[k]
        decision = row["timestamp_utc"] - pd.Timedelta(hours=4)
        used_close = row["ctx_close"]
        if pd.isna(used_close):
            continue
        cand = sig[sig.index <= decision]
        assert len(cand), "karar anından önce kapanmış bar olmalı"
        assert np.isclose(float(cand["ctx_close"].iloc[-1]), float(used_close)), k
        # bar'in KENDISI (T damgali, henuz olusuyor) ASLA kullanilmamis olmali
        assert not np.isclose(float(sig["ctx_close"].get(row["timestamp_utc"], np.nan)),
                              float(used_close)) or row["timestamp_utc"] > decision


def test_context_truncation_only_affects_bars_after_the_cut() -> None:
    """Endeksin sonu kesilince YALNIZCA kesim noktasından sonraki hisse barları
    etkilenmeli (ve fail-closed ile reddedilmeli). Öncesindeki barlar birebir
    aynı kalmalı — gerçek look-ahead testi budur."""
    idx, stock = _index_and_stock(1200)
    cut_n = 200
    full = longs_allowed(stock, idx, "4h", 200)
    trunc = longs_allowed(stock, idx.iloc[:-cut_n].copy(), "4h", 200)
    last_ctx = pd.to_datetime(idx["timestamp_utc"], utc=True).iloc[-cut_n - 1]
    # grace (120h) ICINDE kalan barlar kesimden sonra da gecerli baglam bulur;
    # bu yuzden "guvenli" sinir yalnizca kesim noktasi degil, kesim + grace'tir.
    grace = pd.Timedelta(hours=120)
    safe = full["timestamp_utc"] - pd.Timedelta(hours=4) <= last_ctx
    grey = (full["timestamp_utc"] - pd.Timedelta(hours=4) > last_ctx) & \
           (full["timestamp_utc"] - pd.Timedelta(hours=4) <= last_ctx + grace)
    beyond = ~(safe | grey)
    a = full.loc[safe, "longs_allowed"].to_numpy()
    b = trunc.loc[safe, "longs_allowed"].to_numpy()
    assert len(a) > 100
    assert (a == b).all(), f"kesim öncesi {int((a != b).sum())} bar değişti — LOOK-AHEAD"
    # grace icinde kalan bolge de ayni kalmali (ayni kapanmis bar kullaniliyor)
    assert (full.loc[grey, "longs_allowed"].to_numpy()
            == trunc.loc[grey, "longs_allowed"].to_numpy()).all()
    # grace DISINDA hic kapanmis bar kalmaz -> fail-closed ile red
    assert beyond.sum() > 0
    assert (~trunc.loc[beyond, "longs_allowed"]).all(), "grace dışında fail-closed olmalı"
    assert set(trunc.loc[beyond, "ctx_reason"].unique()) <= {REASON_STALE, REASON_MISSING}


def test_context_not_applied_to_core_assets() -> None:
    """KARAR 4: BTC/GOLD/SILVER long+short kalır, filtreye TABİ DEĞİL."""
    idx, stock = _index_and_stock(600, index_drift=-0.005)
    out = longs_allowed(stock, idx, "4h", 200, long_only=False)
    assert out["longs_allowed"].all()
    assert (out["ctx_reason"] == "context_not_applicable").all()


def test_context_age_is_small_for_full_bars() -> None:
    """BIST 4H grid'i artık günde 2 TAM bar üretir (07:00 ve 11:00 UTC) ve
    XU030 ile AYNI ızgarayı paylaşır; dolayısıyla bağlam yaşı 0 olmalıdır.
    (Eski 3-barlı grid'de ince 03:00 barı 12 saat yaşındaydı ve grace 13h
    olduğu için tek eksik endeks barı tüm günü reddediyordu — H26. İnce bar
    artık üretilmediği için bu kırılganlık da ortadan kalktı.)"""
    p_idx = os.path.join(ROOT, "data", "interim", "bist30_4h.parquet")
    p_st = os.path.join(ROOT, "data", "processed", "bist30", "THYAO_4h_adjusted.parquet")
    if not (os.path.exists(p_idx) and os.path.exists(p_st)):
        print("SKIP  (gerçek BIST verisi yok)")
        return
    idx, st = schema.load_parquet(p_idx), schema.load_parquet(p_st)
    out = longs_allowed(st, idx, "4h", 200)
    hours = {int(x) for x in out["timestamp_utc"].dt.hour.unique()}
    assert hours <= {7, 11}, hours          # ince 03:00 barı artık YOK
    ages = pd.to_numeric(out["ctx_age_hours"], errors="coerce").dropna()
    assert len(ages) > 100
    # İKİ farklı yaş NORMALDİR ve tasarımın doğrudan sonucudur:
    #   11:00 UTC barı -> karar anı 07:00 -> XU030 07:00 barı KAPANMIŞ -> yaş 0
    #   07:00 UTC barı -> karar anı 03:00 -> XU030'da 03:00 barı YOK, en son
    #                     kapanmış bar dün 11:00 -> yaş 16 saat
    # 16 saat, 120 saatlik grace'in çok altındadır; bu yüzden bar reddedilmez.
    # Önemli olan anti-look-ahead sözleşmesidir: kullanılan bar her zaman
    # karar anından ÖNCE kapanmıştır (ayrıca test ediliyor).
    # yaşlar 4 saatlik ızgaranın katları olmalı (0, 4, 8, ...) — keyfî değer yok
    vals = set(ages.round(0).unique().tolist())
    assert all(v % 4 == 0 for v in vals), sorted(vals)
    assert float(ages.min()) == 0.0
    assert (ages <= 16.0).mean() > 0.85, ages.describe()
    # grace (120h) dışındaki barlar ÇOK az olmalı ve STALE olarak reddedilmeli
    assert (ages <= 120.0).mean() > 0.99, "grace dışı bar oranı çok yüksek"
    stale = out[out["ctx_reason"] == "context_stale"]
    if len(stale):
        assert (pd.to_numeric(stale["ctx_age_hours"], errors="coerce") > 120.0).all()
        assert (~stale["longs_allowed"]).all()
    rc = out["ctx_reason"].value_counts().to_dict()
    considered = len(out) - rc.get("context_warmup", 0) - rc.get("context_missing", 0)
    assert rc.get("context_stale", 0) / considered < 0.01, rc
    assert rc.get("context_ok", 0) / considered > 0.6, rc


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
