"""Tests for the BIST30 stock universe layer (Aşama 1.5).

Pinned guarantees:
  * the universe file is frozen, timestamped and has exactly 30 members
  * the stock cost model really is 120 bp round-trip (unit-contract trap)
  * the Istanbul grid gives exactly 3 bins/day (2 full + 1 thin opening bar)
  * Yahoo's 1h adjclose == close trap is detected and reported
  * corporate actions are detected from the DAILY series and FLAGGED ONLY:
    no price is written, no bar is deleted
  * a split-like step is classified differently from a dividend-like step
  * the liquidity / quality gates exclude with a written reason, never delete

Run: python3 -W ignore tests/test_bist_universe.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from quant4h.config import (BIST_STOCK_ROUND_TRIP_BPS, UTC, bist_stock_specs,  # noqa: E402
                            load_bist_universe, make_bist_stock_spec)
from quant4h.data import schema  # noqa: E402
from quant4h.data.adjust import (corporate_actions_from_daily,  # noqa: E402
                                 flag_corporate_actions_from_dates,
                                 flag_price_limit_bars)
from quant4h.data.resample import resample_ohlcv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NOW = pd.Timestamp("2026-09-30 00:00:00", tz=UTC)


# --------------------------------------------------------------------------
# 1. universe file
# --------------------------------------------------------------------------

def test_universe_is_frozen_and_has_30_members() -> None:
    u = load_bist_universe()
    codes = [m["code"] for m in u["members"]]
    assert len(codes) == 30, len(codes)
    assert len(set(codes)) == 30, "duplicate member"
    assert u["version"] and u["frozen_at_utc"], "tarih damgası zorunlu"
    assert u["index_code"] == "XU030"
    assert u["xu030_context"]["tradable"] is False
    assert u["xu030_context"]["role"] == "context_filter_for_longs"
    # survivorship-bias caveat'i ZORUNLU
    ids = {c["id"] for c in u["mandatory_caveats"]}
    assert {"SURVIVORSHIP_BIAS", "POINT_IN_TIME_MISSING", "SOURCE_NOT_OFFICIAL"} <= ids, ids
    # ihtilaflı semboller şeffaf biçimde kayıtlı
    disp = {d["code"]: d["decision"] for d in u["disputed_members"]}
    assert disp.get("FROTO") == "KABUL EDİLDİ"
    assert disp.get("CIMSA") == "REDDEDİLDİ" and disp.get("ULKER") == "REDDEDİLDİ"
    assert u["corporate_actions_policy"]["auto_adjust"] is False


def test_universe_matches_investing_full_list() -> None:
    """The 30th member (FROTO) was missing from Midas/HangiKredi; Investing.com
    was the only source giving all 30. This pins the resolved list."""
    u = load_bist_universe()
    got = {m["code"] for m in u["members"]}
    expected = {"AEFES", "AKBNK", "ASELS", "ASTOR", "BIMAS", "DSTKF", "EKGYO", "ENKAI",
                "EREGL", "FROTO", "GARAN", "GUBRF", "ISCTR", "KCHOL", "KRDMD", "MGROS",
                "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "TAVHL", "TCELL", "THYAO",
                "TOASO", "TRALT", "TTKOM", "TUPRS", "VAKBN", "YKBNK"}
    assert got == expected, (sorted(got ^ expected))


# --------------------------------------------------------------------------
# 2. cost model unit contract
# --------------------------------------------------------------------------

def test_stock_cost_model_is_120bp_round_trip() -> None:
    """CostModel contract: commission/slippage are PER SIDE, spread_bps is the
    FULL quoted spread. Getting this wrong silently yields 90 bp instead of 120."""
    assert abs(BIST_STOCK_ROUND_TRIP_BPS - 120.0) < 1e-9, BIST_STOCK_ROUND_TRIP_BPS
    spec = make_bist_stock_spec("THYAO")
    assert abs(spec.cost.one_way_cost_frac * 1e4 - 60.0) < 1e-9
    assert abs(spec.cost.round_trip_bps - 120.0) < 1e-9
    u = load_bist_universe()
    assert abs(float(u["cost_model"]["round_trip_bps"]) - 120.0) < 1e-9


def test_stock_spec_grid_and_flags() -> None:
    spec = make_bist_stock_spec("AKBNK", "Akbank", "banka")
    assert spec.symbol == "AKBNK.IS" and spec.venue == "yahoo_stock"
    assert spec.native_session_tz == "Europe/Istanbul"
    assert spec.bar_anchor_local == "10:00" and spec.bar_anchor_mode == "local"
    assert spec.session_day_start_local == "05:00"
    assert spec.tradable is True and spec.has_volume is True
    assert spec.volume_required is True          # hisselerde hacim VAR (endekste yoktu)
    assert spec.requires_adjustment is False     # hisse: roll yok
    assert len(spec.caveats) >= 5
    assert len(bist_stock_specs()) == 30


# --------------------------------------------------------------------------
# 3. resample grid
# --------------------------------------------------------------------------

def _stock_1h(days: int = 60, code: str = "AKBNK", px0: float = 60.0,
              zero_open_print: bool = True) -> pd.DataFrame:
    """BIST-like 1h feed: prints at 09:30..17:30 Europe/Istanbul, weekdays."""
    rng = np.random.default_rng(9)
    stamps, rows = [], []
    px = px0
    for d in pd.bdate_range("2024-01-02", periods=days, tz="Europe/Istanbul"):
        for k, (hh, mm) in enumerate([(9, 30), (10, 30), (11, 30), (12, 30), (13, 30),
                                      (14, 30), (15, 30), (16, 30), (17, 30)]):
            stamps.append(d.replace(hour=hh, minute=mm))
            o = px
            px *= float(np.exp(rng.normal(0, 0.006)))
            vol = 0.0 if (k == 0 and zero_open_print) else float(rng.uniform(1e5, 1e6))
            rows.append((o, max(o, px) * 1.001, min(o, px) * 0.999, px, vol))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    df.insert(0, "timestamp_utc", pd.DatetimeIndex(stamps).tz_convert(UTC))
    df.insert(0, "symbol", f"{code}.IS")
    return df


def test_istanbul_grid_gives_two_full_bars_only() -> None:
    spec = make_bist_stock_spec("AKBNK")
    src = _stock_1h(days=40)
    out = resample_ohlcv(src, "4h", spec, now=NOW)
    assert len(out) > 0
    local = {int(x) for x in out["timestamp_utc"].dt.tz_convert("Europe/Istanbul").dt.hour.unique()}
    assert local == {10, 14}, local
    utc_hours = {int(x) for x in out["timestamp_utc"].dt.hour.unique()}
    assert utc_hours == {7, 11}, utc_hours             # Türkiye'de DST yok -> sabit
    per = out.groupby("session_date").size()
    assert int(per.median()) == 2, per.value_counts().to_dict()
    # min_source_bars_per_target=4 -> YALNIZCA TAM barlar; ince bar ÜRETİLMEZ
    # eşik 3 (>= %75 kapsama): 17:30 printi günlerin ~%45'inde feed'de YOK,
    # bu yüzden 14:00-18:00 bin'i çoğu gün 3 kaynak bar içerir.
    assert spec.min_source_bars_per_target == 3
    assert (out["n_src_bars"] >= 3).all(), out["n_src_bars"].value_counts().to_dict()


def test_forming_last_bar_is_dropped_for_stocks() -> None:
    spec = make_bist_stock_spec("AKBNK")
    src = _stock_1h(days=40)
    last_close = pd.to_datetime(src["timestamp_utc"], utc=True).max() + pd.Timedelta(hours=1)
    keep = resample_ohlcv(src, "4h", spec, drop_partial=True, now=last_close)
    allb = resample_ohlcv(src, "4h", spec, drop_partial=False, now=last_close)
    assert len(allb) >= len(keep)
    for ts in pd.to_datetime(keep["timestamp_utc"], utc=True):
        assert ts + pd.Timedelta(hours=4) <= last_close


def test_zero_volume_was_confined_to_the_thin_opening_bar() -> None:
    """H18 kök nedeninin kanıtı: 16.5% sıfır-hacim oranının TAMAMI 09:30
    açılış-anı printinden geliyordu. İnce barlar tutulduğunda (min_bars_fill=1)
    bu ölçülebilir; spec varsayılanı (4) ise ince barı HİÇ üretmez ve sıfır
    hacim oranı ~0'a düşer."""
    spec = make_bist_stock_spec("AKBNK")
    thin_kept = resample_ohlcv(_stock_1h(days=40), "4h", spec, min_bars_fill=1, now=NOW)
    vol = thin_kept["volume"].fillna(0.0)
    thin = thin_kept["n_src_bars"] < 3
    assert (vol[thin] == 0).mean() > 0.9, "ince bar hacimsiz olmalı"
    assert (vol[~thin] == 0).mean() == 0.0, "TAM barlarda sıfır hacim olmamalı"
    full_only = resample_ohlcv(_stock_1h(days=40), "4h", spec, now=NOW)
    assert (full_only["n_src_bars"] >= 3).all()
    assert float((full_only["volume"].fillna(0.0) == 0).mean()) == 0.0


# --------------------------------------------------------------------------
# 4. corporate actions: FLAG ONLY, from the DAILY series
# --------------------------------------------------------------------------

def _daily_with_actions(n: int = 500, split_at: int = 300, div_at: int = 150,
                        split_ratio: float = 0.5) -> pd.DataFrame:
    idx = pd.bdate_range("2023-01-02", periods=n, tz=UTC)
    rng = np.random.default_rng(4)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    close[split_at:] *= split_ratio                       # 2:1 split
    adj = close.copy()
    adj[:div_at] *= 0.97                                  # temettü düzeltmesi
    adj[:split_at] *= split_ratio
    return pd.DataFrame({"symbol": "TEST.IS", "timestamp_utc": idx,
                         "open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": 1e6, "adjclose": adj})


def test_corporate_actions_detected_from_daily_series() -> None:
    daily = _daily_with_actions()
    ev = corporate_actions_from_daily(daily)
    assert len(ev) >= 2, len(ev)
    types = set(ev["event_type"])
    assert "split" in types, types
    assert "dividend_or_other" in types, types
    # split günü = 300. iş günü
    assert pd.Timestamp(daily["timestamp_utc"].iloc[300]).normalize() in set(ev["date"])


def test_corporate_action_flagging_writes_no_price_and_deletes_no_bar() -> None:
    spec = make_bist_stock_spec("AKBNK")
    frame = resample_ohlcv(_stock_1h(days=120), "4h", spec, now=NOW)
    frame["close_raw"] = frame["close"]
    frame["return_valid"] = True
    frame["non_tradable"] = False
    frame["non_tradable_reason"] = ""
    frame["close_to_close_return"] = np.log(frame["close"] / frame["close"].shift(1))
    ex_date = pd.to_datetime(frame["session_date"].astype(str)).iloc[100]
    before_close = frame["close"].to_numpy().copy()
    n0 = len(frame)

    out = flag_corporate_actions_from_dates(frame, [ex_date], event_types={ex_date: "split"})

    assert len(out) == n0                                     # hiçbir bar silinmedi
    assert np.allclose(out["close"].to_numpy(), before_close)  # hiçbir fiyat yazılmadı
    assert int(out["corporate_action_flag"].sum()) >= 1
    assert "split" in set(out["corporate_action_type"])
    marked = out[out["corporate_action_flag"] | out["non_tradable_reason"].str.contains("corporate_action")]
    assert len(marked) >= 1
    assert (~marked["return_valid"]).all(), "ex-date barının getirisi geçersiz olmalı"
    assert marked["non_tradable"].all()
    assert out.attrs["corporate_action_events"] == 1
    assert out.attrs["corporate_action_bars"] >= 1, "tz kaybı olursa 0 olur (regresyon)"
    assert out.attrs["corporate_action_source"] == "daily adjclose/close ratio step"
    assert "corporate_action_warning" not in out.attrs


def test_corporate_action_matching_is_not_silently_fooled_by_tz() -> None:
    """REGRESYON: pd.DatetimeIndex(datetime64[us, UTC]) tz'yi sessizce dusurur;
    o zaman isin() hep False doner ve HICBIR bar isaretlenmez. Eslesme olmazsa
    fonksiyon sessiz kalmamali, uyari uretmelidir."""
    spec = make_bist_stock_spec("AKBNK")
    frame = resample_ohlcv(_stock_1h(days=60), "4h", spec, now=NOW)
    frame["close_raw"] = frame["close"]
    frame["return_valid"] = True
    frame["non_tradable"] = False
    frame["non_tradable_reason"] = ""
    # bilincli olarak IMKANSIZ bir tarih ver -> eslesme olmamali ama UYARI cikmali
    out = flag_corporate_actions_from_dates(frame, [pd.Timestamp("1999-01-01", tz=UTC)])
    assert int(out["corporate_action_flag"].sum()) == 0
    # pencere DISINDA tarih -> uyari degil BILGI notu (normal durum)
    assert "corporate_action_note" in out.attrs, out.attrs
    assert "corporate_action_warning" not in out.attrs
    # pencere ICINDE olup eslesmeyen tarih -> GERCEK uyari (tz/tarih hatasi suphesi)
    inside = pd.Timestamp(str(pd.to_datetime(frame["session_date"].astype(str)).iloc[10].date()), tz=UTC)
    out3 = flag_corporate_actions_from_dates(frame, [inside])
    assert int(out3["corporate_action_flag"].sum()) >= 1 or "corporate_action_warning" in out3.attrs
    # tz-naive tarih verilse bile eslesme CALISMALI (utc'a zorlaniyor)
    ex = pd.to_datetime(frame["session_date"].astype(str)).iloc[50]
    out2 = flag_corporate_actions_from_dates(frame, [ex.to_pydatetime()])
    assert int(out2["corporate_action_flag"].sum()) >= 1, "tz-naive girdi de eslesmeli"


def test_1h_adjclose_trap_is_real_and_documented() -> None:
    """Ölçülmüş bulgu: Yahoo 1h BIST serisinde adjclose == close. Bunu bilmeyen
    bir tespit sessizce HİÇBİR şey bulamaz."""
    path = os.path.join(ROOT, "data", "raw", "bist30", "AKBNK_1h_raw.parquet")
    if not os.path.exists(path):
        print("SKIP  (AKBNK_1h_raw.parquet yok)")
        return
    h1 = schema.load_parquet(path)
    assert "adjclose" in h1.columns
    same = float(np.isclose(h1["adjclose"], h1["close"], rtol=1e-6).mean())
    assert same > 0.99, same
    assert len(corporate_actions_from_daily(h1)) == 0, "1h seriden olay ÇIKMAMALI"
    dpath = os.path.join(ROOT, "data", "raw", "bist30", "AKBNK_1d_raw.parquet")
    if os.path.exists(dpath):
        d1 = schema.load_parquet(dpath)
        assert len(corporate_actions_from_daily(d1)) > 0, "günlük seriden olay ÇIKMALI"


# --------------------------------------------------------------------------
# 5. halt / price-limit flags
# --------------------------------------------------------------------------

def test_price_limit_flag_is_heuristic_and_non_destructive() -> None:
    spec = make_bist_stock_spec("AKBNK")
    frame = resample_ohlcv(_stock_1h(days=40), "4h", spec, now=NOW)
    i = frame.index[20]
    frame.loc[i, "high"] = frame.loc[i, "low"]                    # zero range
    j = frame.index[40]
    frame.loc[j, "high"] = frame.loc[j, "open"] * 1.20            # marja koşma
    frame.loc[j, "low"] = frame.loc[j, "open"]
    n0 = len(frame)
    out = flag_price_limit_bars(frame)
    assert len(out) == n0
    assert bool(out.loc[i, "halt_or_limit_flag"]) is True
    assert bool(out.loc[j, "halt_or_limit_flag"]) is True
    assert int(out["halt_or_limit_flag"].sum()) >= 2
    # bayrak fiyatı DEĞİŞTİRMEZ, getiriyi de geçersiz SAYMAZ (yalnızca uyarı)
    assert np.allclose(out["close"].to_numpy(), frame["close"].to_numpy())
    assert out.attrs["halt_or_limit_bars"] >= 2


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
