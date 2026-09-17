"""Tests for AŞAMA 7 — çıkış profilleri (P0..P3), stop anchor'ları (A0..A2), D6 kilidi.

Kilitlenen garantiler:
  * P0 (varsayılan) Aşama 6 davranışını BİREBİR korur (26 mevcut test + gerçek
    veri regresyonu: BTC/GOLD/SILVER P0×A0 == reports/backtest_baseline.json)
  * D6: bar t içinde kapanan pozisyonun ardından bar t AÇILIŞINDA yeni giriş YOK
  * P1: 1R'de %50 partial (gap→open), stop→BE (bar sonu, sonraki bardan geçerli),
    runner chandelier ATR×3 (zırhır, gevşemez), TS/TP YOK; aynı barda stop+1R → STOP
  * P2: girişten chandelier ATR×3 + TS90 emniyet, TP YOK
  * P3: 1R→BE + TP3R + TS90, partial YOK
  * maliyetler partial'da bacaklara bölünür; toplam = one_way × (giriş + tüm çıkış notional'ları)
  * short tarafı simetrik; trailing'de look-ahead YOK (silme testi)
  * anchor'lar: A0 no-op · A1 Donchian ters bandı · A2 swing−0.5×ATR (elle hesapla
    birebir); küme dışı anchor/profile/sabit → ValueError (tune YOK)

Run: python3 -W ignore tests/test_exit_profiles.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from quant4h.backtest.anchors import ANCHORS, apply_anchor  # noqa: E402
from quant4h.backtest.engine import run_backtest  # noqa: E402
from quant4h.config import UTC, CostModel, ExitConfig  # noqa: E402

COST = CostModel(commission_bps=10.0, spread_bps=6.0, slippage_bps=4.0)   # one_way 17 bp
ZERO = CostModel(commission_bps=0.0, spread_bps=0.0, slippage_bps=0.0)
START = 100_000.0
RISK = 0.005


def _mk(rows, start: str = "2024-01-01 00:00:00", stop: float = 90.0,
        stop_valid: bool = True, signals=(0,), direction: str = "long",
        atr: float = 2.0) -> pd.DataFrame:
    """rows: (open, high, low, close) listesi. signals: sinyal bar İNDEKSLERİ
    (giriş bir SONRAKI barın açılışı)."""
    n = len(rows)
    idx = pd.date_range(start, periods=n, freq="4h", tz=UTC)
    df = pd.DataFrame({
        "symbol": "TEST", "timestamp_utc": idx,
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
        "volume": [1000.0] * n,
    })
    df["atr"] = atr
    df["non_tradable"] = False
    df["return_valid"] = True
    df["stop_long"] = np.nan
    df["stop_short"] = np.nan
    df["stop_valid_long"] = pd.Series(False, index=df.index, dtype=bool)
    df["stop_valid_short"] = pd.Series(False, index=df.index, dtype=bool)
    col_s = "stop_long" if direction == "long" else "stop_short"
    col_v = "stop_valid_long" if direction == "long" else "stop_valid_short"
    df[col_s] = stop
    df[col_v] = pd.Series(bool(stop_valid), index=df.index, dtype=bool)
    df["long_signal"] = pd.Series(False, index=df.index, dtype=bool)
    df["short_signal"] = pd.Series(False, index=df.index, dtype=bool)
    sig_col = "long_signal" if direction == "long" else "short_signal"
    for s in signals:
        df.loc[df.index[s], sig_col] = True
    return df


def _run(df, profile="P0", cost=COST, **kw):
    return run_backtest(df, cost, exit_cfg=ExitConfig(profile=profile),
                        risk_per_trade=RISK, starting_equity=START,
                        allow_short=kw.pop("allow_short", True), **kw)


# ---------------------------------------------------------------------------
# kilitler: enum + şartname sabitleri
# ---------------------------------------------------------------------------

def test_profile_enum_and_constants_locked() -> None:
    for p in ("P0", "P1", "P2", "P3"):
        assert ExitConfig(profile=p).profile == p
    for bad in ("P4", "p1", "", "TRAILING"):
        try:
            ExitConfig(profile=bad)
            raise AssertionError(f"profile {bad!r} ValueError vermeli")
        except ValueError:
            pass
    for kwargs in ({"partial_frac": 0.4}, {"breakeven_trigger_r": 1.5},
                   {"chandelier_atr_mult": 2.0}):
        try:
            ExitConfig(profile="P1", **kwargs)
            raise AssertionError(f"{kwargs} ValueError vermeli (şartname sabiti)")
        except ValueError:
            pass
    assert ExitConfig().profile == "P0", "varsayılan P0 olmalı (Aşama 9'a kadar)"


def test_anchor_enum_locked() -> None:
    for a in ("A3", "a0", ""):
        try:
            apply_anchor(_mk([(100, 101, 99, 100)] * 3), a, allow_short=True)
            raise AssertionError(f"anchor {a!r} ValueError vermeli")
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# D6 — aynı-bar çıkış+giriş kilidi
# ---------------------------------------------------------------------------

def test_same_bar_exit_blocks_same_bar_entry() -> None:
    # bar0: sinyal A -> bar1 giriş (open 100, stop 90)
    # bar1: sinyal B var (engine bar2 açılışında giriş dener)
    # bar2: low 89 -> stop çıkışı (bar2 İÇİNDE). D6: bar2 açılışında giriş YASAK.
    # bar2: sinyal C -> bar3 açılışında giriş SERBEST.
    rows = [(100, 101, 99, 100),      # 0 sinyal A
            (100, 101, 99.5, 100),    # 1 giriş + sinyal B
            (100, 100.5, 89, 90),     # 2 stop çıkışı + sinyal C
            (95, 96, 94, 95),         # 3 ikinci giriş (open 95)
            (95, 96, 94, 95)]         # 4
    df = _mk(rows, signals=(0, 1, 2), atr=50.0)
    res = _run(df, "P0", cost=ZERO)
    assert len(res.trades) == 2, f"2 trade beklenir, {len(res.trades)} bulundu"
    t1, t2 = res.trades
    assert t1.entry_bar == 1 and t1.exit_bar == 2 and t1.exit_reason == "stop"
    assert t2.entry_bar == 3, "D6: çıkış barının AÇILIŞINDA giriş olmamalı; sonraki sinyal bar4'e kalmamalı"
    assert float(t2.entry_price) == 95.0


# ---------------------------------------------------------------------------
# P1 — partial + runner
# ---------------------------------------------------------------------------

def test_p1_partial_at_1r_then_breakeven_stop() -> None:
    # entry 100 (bar1 open), stop 90 -> R=10, tp1=110; atr=5 (chandelier 112-15=97 < BE)
    rows = [(100, 101, 99, 100),        # 0 sinyal
            (100, 101, 99.5, 100.5),    # 1 giriş
            (105, 112, 104, 111),       # 2 high>=110 -> partial 110; bar sonu BE=100
            (100.5, 101, 99, 99.5)]     # 3 low<=100 -> stop BE'den (gap yok)
    df = _mk(rows, atr=5.0)
    res = _run(df, "P1", cost=ZERO)
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.profile == "P1" and t.partial_filled
    assert t.partial_exit_bar == 2 and t.partial_exit_price == 110.0
    assert abs(t.partial_units - t.units / 2.0) < 1e-9
    assert t.exit_reason == "stop" and t.stop_at_breakeven
    assert t.exit_price == 100.0 and t.exit_bar == 3
    # r_multiple = (0.5*(110-100) + 0.5*(100-100)) / 10 = 0.5
    assert abs(t.r_multiple - 0.5) < 1e-9


def test_p1_partial_gap_fills_at_open() -> None:
    rows = [(100, 101, 99, 100),
            (100, 101, 99.5, 100.5),
            (115, 118, 114, 117),       # open 115 > tp1 110 -> partial OPEN'dan
            (100.5, 101, 99, 99.5)]     # BE stop
    df = _mk(rows, atr=50.0)
    res = _run(df, "P1", cost=ZERO)
    t = res.trades[0]
    assert t.partial_filled and t.partial_exit_price == 115.0


def test_p1_same_bar_stop_and_partial_stop_wins() -> None:
    # bar2: hem low<=90 (stop) hem high>=110 (1R) -> STOP kazanır, partial YOK
    rows = [(100, 101, 99, 100),
            (100, 101, 99.5, 100.5),
            (100, 112, 88, 95)]
    df = _mk(rows, atr=5.0)
    res = _run(df, "P1", cost=ZERO)
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.exit_reason == "stop" and not t.partial_filled
    assert t.exit_price == 90.0


def test_p1_runner_chandelier_ratchets_and_exits() -> None:
    # atr=1: partial 110 (bar2); bar2 sonu: hh=112 -> BE 100 -> chandelier 109
    # bar3: hh=115 -> chandelier 112; bar4: low 111 <= 112 -> çıkış 112 (open 113 > 112, gap yok)
    rows = [(100, 101, 99, 100),
            (100, 101, 99.5, 100),
            (105, 112, 104, 111),
            (110, 115, 109.5, 114),
            (113, 113.5, 111, 111.5)]
    df = _mk(rows, atr=1.0)
    res = _run(df, "P1", cost=ZERO)
    t = res.trades[0]
    assert t.partial_filled and t.partial_exit_price == 110.0
    assert t.exit_reason == "chandelier" and t.stop_was_trailed
    assert t.exit_price == 112.0 and t.exit_bar == 4
    # R: 0.5*(110-100)/10 + 0.5*(112-100)/10 = 0.5 + 0.6 = 1.1
    assert abs(t.r_multiple - 1.1) < 1e-9


def test_p1_has_no_time_stop() -> None:
    # 95 düz bar: stop 90'a hiç dokunmaz, 1R (110) hiç gelmez -> P1 pozisyonu
    # TS ile KAPATMAZ; sonunda end_of_data (P0 aynı frame'de time_stop ile kapatır)
    rows = [(100, 101, 99, 100)] * 96
    df = _mk(rows, atr=50.0)
    r1 = _run(df, "P1", cost=ZERO)
    assert r1.trades[-1].exit_reason == "end_of_data"
    r0 = _run(df, "P0", cost=ZERO)
    assert r0.trades[-1].exit_reason == "time_stop"


# ---------------------------------------------------------------------------
# P2 — trailing
# ---------------------------------------------------------------------------

def test_p2_chandelier_ratchet_never_loosens() -> None:
    # atr=2; zirve bar3 (hh=106 -> stop 100). bar4 düşer ama zırh GEVŞEMEZ.
    # bar5: low 98 <= 100 -> çıkış 100'den (open 100.5, gap yok)
    rows = [(100, 101, 99, 100),
            (100, 101, 99.5, 100),
            (102, 104, 101, 103),
            (104, 106, 103, 105),
            (105, 105.5, 101, 101.5),
            (100.5, 101, 98, 99)]
    df = _mk(rows, atr=2.0)
    res = _run(df, "P2", cost=ZERO)
    t = res.trades[0]
    assert t.exit_reason == "chandelier" and t.exit_price == 100.0
    assert t.stop_was_trailed and not t.partial_filled


def test_p2_time_stop_safety_fires() -> None:
    rows = [(100, 101, 99, 100)] * 96
    df = _mk(rows, atr=50.0)
    res = _run(df, "P2", cost=ZERO)
    t = res.trades[0]
    assert t.exit_reason == "time_stop" and t.bars_held == 90


# ---------------------------------------------------------------------------
# P3 — breakeven
# ---------------------------------------------------------------------------

def test_p3_breakeven_stop_and_tp_variants() -> None:
    base = [(100, 101, 99, 100), (100, 101, 99.5, 100.5), (105, 111, 104, 110)]
    # varyant A: BE sonrası düşüş -> stop 100 (BE)
    rows = base + [(100.5, 101, 99, 99.5)]
    t = _run(_mk(rows, atr=5.0), "P3", cost=ZERO).trades[0]
    assert t.exit_reason == "stop" and t.stop_at_breakeven and t.exit_price == 100.0
    assert not t.partial_filled and t.partial_units == 0.0
    # varyant B: BE sonrası TP 130
    rows = base + [(101, 131, 100.5, 130)]
    t = _run(_mk(rows, atr=5.0), "P3", cost=ZERO).trades[0]
    assert t.exit_reason == "take_profit" and t.exit_price == 130.0


def test_p3_be_effective_next_bar_only() -> None:
    # 1R teması olan barın KENDİSİNDE fiyat entry'ye geri dönse bile BE o bar
    # geçerli DEĞİL (bar sonu yazılır): çıkış ancak yapısal stoptan (90) olur.
    rows = [(100, 101, 99, 100),
            (100, 101, 99.5, 100.5),
            (105, 111, 99.5, 100)]   # high>=110 (1R) VE low 99.5 > 90; entry=100'e dönüş
    df = _mk(rows + [(100, 101, 99, 100)] * 3, atr=5.0)
    res = _run(df, "P3", cost=ZERO)
    t = res.trades[0]
    assert t.exit_bar > 2, "BE temas barında geçerli olmamalı"


# ---------------------------------------------------------------------------
# short simetri + maliyetler + look-ahead
# ---------------------------------------------------------------------------

def test_short_p1_symmetric() -> None:
    rows = [(100, 101, 99, 100),
            (100, 100.5, 99, 99.5),
            (95, 96, 88, 89),         # low<=90 (1R) -> partial 90 (open 95 > 90, gap yok)
            (99.5, 101, 99, 100.5)]   # high>=100 -> BE stop 100
    df = _mk(rows, stop=110.0, direction="short", atr=5.0)
    res = _run(df, "P1", cost=ZERO, signal_col_long="__none__",
               signal_col_short="short_signal")
    t = res.trades[0]
    assert t.direction == "short" and t.partial_filled
    assert t.partial_exit_price == 90.0
    assert t.exit_reason == "stop" and t.stop_at_breakeven and t.exit_price == 100.0


def test_costs_split_across_legs_are_round_trip() -> None:
    rows = [(100, 101, 99, 100),
            (100, 101, 99.5, 100.5),
            (105, 112, 104, 111),
            (100.5, 101, 99, 99.5)]
    df = _mk(rows, atr=5.0)
    res = _run(df, "P1", cost=COST)
    t = res.trades[0]
    ow = COST.one_way_cost_frac
    n_entry = abs(t.entry_price * t.units)
    n_exit = abs(t.partial_exit_price * t.partial_units) + abs(t.exit_price * (t.units - t.partial_units))
    assert abs(t.cost_entry - n_entry * ow) < 1e-6
    assert abs(t.cost_exit - n_exit * ow) < 1e-6
    assert abs(t.cost_total - (t.cost_entry + t.cost_exit)) < 1e-9
    assert abs((t.equity_after - t.equity_before) - t.net_pnl) < 1e-6
    # equity eğrisi ile trade zinciri tutarlı (kabul kriteri 8 deseni)
    eq_final = res.equity["equity"].dropna().iloc[-1]
    assert abs(eq_final - t.equity_after) < 1e-6


def test_no_lookahead_trailing_p2_truncation() -> None:
    import run_exit_grid as G
    from quant4h.backtest.engine import run_backtest as rb
    from quant4h.config import RISK_PROFILES
    frame = G._signals_for("BTC", "4h", False, None, "A0")
    assert frame is not None and len(frame) > 1000
    prof = RISK_PROFILES["balanced"]
    cost = G.RB._cost_for("BTC", False)
    cut = len(frame) - 400
    common = dict(exit_cfg=ExitConfig(profile="P2"), risk_per_trade=prof.risk_per_trade,
                  starting_equity=START, max_leverage=prof.max_leverage,
                  allow_short=False, asset="BTC_long")
    r_full = rb(frame, cost, **common)
    r_trunc = rb(frame.iloc[:cut].reset_index(drop=True), cost, **common)
    # kesimden ÖNCE tamamlanan trade'ler birebir aynı olmalı (trailing yalnız
    # KAPALI barlarla güncellenir -> gelecek barların silinmesi geçmişi değiştirmez)
    n_checked = 0
    for a, b in zip(r_trunc.trades, r_full.trades):
        if b.exit_bar >= cut - 1:
            break
        assert (a.entry_bar, a.exit_bar, a.exit_reason) == (b.entry_bar, b.exit_bar, b.exit_reason)
        assert abs(a.exit_price - b.exit_price) < 1e-9
        n_checked += 1
    assert n_checked > 10, f"yetersiz karşılaştırma: {n_checked}"


# ---------------------------------------------------------------------------
# anchor'lar
# ---------------------------------------------------------------------------

def _lvl_frame() -> pd.DataFrame:
    df = _mk([(100, 101, 99, 100)] * 5, atr=2.0)
    df["last_swing_low"] = 95.0
    df["last_swing_high"] = 105.0
    df["donchian_low"] = 97.0
    df["donchian_high"] = 103.0
    df["close"] = 100.0
    return df


def test_anchor_a0_is_noop() -> None:
    df = _lvl_frame()
    df["stop_long"] = 93.0
    df["stop_valid_long"] = True
    out = apply_anchor(df, "A0", allow_short=True)
    assert float(out["stop_long"].iloc[0]) == 93.0


def test_anchor_a1_donchian_reverse_band() -> None:
    out = apply_anchor(_lvl_frame(), "A1", allow_short=True)
    assert float(out["stop_long"].iloc[0]) == 97.0
    assert bool(out["stop_valid_long"].iloc[0])
    assert float(out["stop_short"].iloc[0]) == 103.0
    assert bool(out["stop_valid_short"].iloc[0])
    assert out["stop_anchor_long"].iloc[0] == "donchian20_low"
    # geçersiz geometri: donchian_low >= close -> fail-closed
    bad = _lvl_frame()
    bad["donchian_low"] = 101.0
    out2 = apply_anchor(bad, "A1", allow_short=True)
    assert not bool(out2["stop_valid_long"].iloc[0])


def test_anchor_a2_buffer_half_matches_manual() -> None:
    out = apply_anchor(_lvl_frame(), "A2", allow_short=True)
    # swing 95 - 0.5*ATR(2) = 94
    assert abs(float(out["stop_long"].iloc[0]) - 94.0) < 1e-9
    assert bool(out["stop_valid_long"].iloc[0])
    # short: 105 + 0.5*2 = 106
    assert abs(float(out["stop_short"].iloc[0]) - 106.0) < 1e-9


# ---------------------------------------------------------------------------
# P0 regresyonu — gerçek veri (Aşama 6 baseline birebir)
# ---------------------------------------------------------------------------

def test_p0xa0_reproduces_stage6_core_numbers() -> None:
    import run_exit_grid as G
    base_path = os.path.join(G.ROOT, "reports", "backtest_baseline.json")
    assert os.path.exists(base_path), "baseline json yok"
    with open(base_path, "r", encoding="utf-8") as fh:
        base = json.load(fh)
    from quant4h.config import RISK_PROFILES
    prof = RISK_PROFILES["balanced"]
    for key in ("BTC", "GOLD", "SILVER"):
        frame = G._signals_for(key, "4h", False, None, "A0")
        assert frame is not None, f"{key} frame yok"
        cell = G._cell_core(key, frame, prof, ExitConfig(profile="P0"), START)
        ref = base["core_assets"][key]["metrics"]
        got = cell["metrics"]
        for f, tol in (("n_trades", 0), ("win_rate", 1e-4), ("profit_factor_net", 1e-3),
                       ("expectancy_r", 1e-4), ("max_drawdown_frac", 1e-6)):
            a, b = got.get(f), ref.get(f)
            assert a is not None and b is not None, f"{key}.{f} yok"
            assert abs(float(a) - float(b)) <= tol + abs(float(b)) * 1e-6, \
                f"{key}.{f}: {a} != {b} (P0×A0 Aşama 6'yı birebir üretmeli)"


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
