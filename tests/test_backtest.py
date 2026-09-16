"""Tests for AŞAMA 6 — baseline backtest engine.

Kabul kriteri 8'de sayılan testlerin TAMAMI:
  * stop gap dolumu (open stop'un ötesinde → open'dan)
  * TP gap dolumu (open TP'nin ötesinde → open'dan)
  * aynı-bar çakışması → STOP öncelikli (pesimist)
  * time-stop TAM bar sayısında
  * maliyet toplamı assert'i (iki tarafa da, one_way × notional)
  * equity'nin trade listesinden BAĞIMSIZ yeniden hesabı
  * t+1 icra look-ahead silme testi
Ek olarak:
  * geçerli stopu olmayan pozisyon ASLA açılmaz (H35 kilidi)
  * stop pozisyon boyunca DONDURULMUŞTUR (gevşetilmez/kaydırılmaz)
  * short tarafı simetrik çalışır
  * hisselerde short açılmaz

Run: python3 -W ignore tests/test_backtest.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from quant4h.backtest.engine import (buy_hold_reference, compute_metrics,  # noqa: E402
                                     equity_from_trades, run_backtest)
from quant4h.config import (DEFAULT_EXIT, DEFAULT_PROFILE, ExitConfig,  # noqa: E402
                            RISK_PROFILES, UTC, CostModel)

COST = CostModel(commission_bps=10.0, spread_bps=6.0, slippage_bps=4.0)   # one_way 17 bp
ZERO = CostModel(commission_bps=0.0, spread_bps=0.0, slippage_bps=0.0)
START = 100_000.0
RISK = 0.005


def _mk(rows, start: str = "2024-01-01 00:00:00", stop: float = 90.0,
        stop_valid: bool = True, signal_at: int = 0, direction: str = "long",
        atr: float = 2.0) -> pd.DataFrame:
    """rows: list of (open, high, low, close). Signal, bar `signal_at`'in
    KAPANIŞINDA üretilir -> giriş bar `signal_at + 1` AÇILIŞINDA."""
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
    col_s = "stop_long" if direction == "long" else "stop_short"
    col_v = "stop_valid_long" if direction == "long" else "stop_valid_short"
    df["stop_long"] = np.nan
    df["stop_short"] = np.nan
    df["stop_valid_long"] = pd.Series(False, index=df.index, dtype=bool)
    df["stop_valid_short"] = pd.Series(False, index=df.index, dtype=bool)
    df[col_s] = stop
    df[col_v] = pd.Series(bool(stop_valid), index=df.index, dtype=bool)
    df["long_signal"] = pd.Series(False, index=df.index, dtype=bool)
    df["short_signal"] = pd.Series(False, index=df.index, dtype=bool)
    df.loc[df.index[signal_at], "long_signal" if direction == "long" else "short_signal"] = True
    return df


# --------------------------------------------------------------------------
# icra zamanı ve giriş fiyatı
# --------------------------------------------------------------------------

def test_entry_is_next_bar_open_and_costs_are_charged_both_sides() -> None:
    rows = [(100, 101, 99, 100)] * 200
    df = _mk(rows, stop=90.0, signal_at=5)
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    assert len(res.trades) >= 1
    t0 = res.trades[0]
    assert t0.signal_bar == 5 and t0.entry_bar == 6, (t0.signal_bar, t0.entry_bar)
    assert t0.entry_price == 100.0                      # open[6]
    assert t0.entry_timestamp_utc == str(df["timestamp_utc"].iloc[6])
    assert t0.signal_timestamp_utc == str(df["timestamp_utc"].iloc[5])
    assert t0.stop_price == 90.0 and t0.tp_price == 130.0        # 3R = 100 + 3*10
    # birim sayısı: risk_tutar / stop_mesafesi = (0.005*100000)/10 = 50
    assert np.isclose(t0.units, 50.0), t0.units
    assert np.isclose(t0.notional_entry, 5000.0)
    # sıfır maliyette cost 0 olmalı
    assert t0.cost_total == 0.0
    # aynı trade maliyetli modelde: one_way = (10 + 6/2 + 4)/1e4 = 17 bp
    res2 = run_backtest(df, COST, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                        starting_equity=START, asset="TEST")
    t2 = res2.trades[0]
    ow = COST.one_way_cost_frac
    assert np.isclose(ow, 17e-4), ow
    assert np.isclose(t2.cost_entry, t2.notional_entry * ow)
    assert np.isclose(t2.cost_exit, t2.notional_exit * ow)
    assert np.isclose(t2.cost_total, t2.cost_entry + t2.cost_exit)
    assert np.isclose(t2.net_pnl, t2.gross_pnl - t2.cost_total)


def test_stop_gap_fill_uses_open_when_open_is_worse() -> None:
    """Kabul kriteri 2: bar open < stop ise STOP FİYATINDAN DEĞİL open'dan çıkılır."""
    rows = [(100, 101, 99, 100)] * 7 + [(85.0, 86.0, 84.0, 85.0)] + [(85, 86, 84, 85)] * 5
    df = _mk(rows, stop=90.0, signal_at=5)     # giriş bar 6 (open 100), gap bar 7
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    t = res.trades[0]
    assert t.entry_bar == 6 and t.entry_price == 100.0
    assert t.exit_reason == "stop"
    assert t.exit_price == 85.0, t.exit_price          # open, stop'un ALTINDA
    assert t.exit_bar == 7
    assert np.isclose(t.r_multiple, (85.0 - 100.0) / 10.0), t.r_multiple
    assert t.r_multiple < -1.0, "gap stop'ta kayıp 1R'den BÜYÜK olmalı"


def test_stop_normal_fill_uses_stop_price() -> None:
    rows = [(100, 101, 99, 100)] * 7 + [(95.0, 96.0, 89.0, 91.0)] + [(91, 92, 90, 91)] * 5
    df = _mk(rows, stop=90.0, signal_at=5)
    t = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                     starting_equity=START, asset="TEST").trades[0]
    assert t.exit_reason == "stop"
    assert t.exit_price == 90.0, t.exit_price          # open stop'un ÜSTÜNDE -> stop'tan
    assert np.isclose(t.r_multiple, -1.0), t.r_multiple


def test_take_profit_gap_fill_uses_open_when_open_is_better() -> None:
    """TP gap'inde open TP'nin ötesindeyse open'dan çıkılır (kabul kriteri 2)."""
    rows = [(100, 101, 99, 100)] * 7 + [(135.0, 140.0, 134.0, 138.0)] + [(138, 139, 137, 138)] * 5
    df = _mk(rows, stop=90.0, signal_at=5)
    t = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                     starting_equity=START, asset="TEST").trades[0]
    assert t.exit_reason == "take_profit"
    assert t.exit_price == 135.0, t.exit_price         # open > tp(130) -> open
    assert t.r_multiple > 3.0, t.r_multiple


def test_take_profit_normal_fill_uses_tp_price() -> None:
    rows = [(100, 101, 99, 100)] * 7 + [(120.0, 132.0, 119.0, 131.0)] + [(131, 132, 130, 131)] * 5
    df = _mk(rows, stop=90.0, signal_at=5)
    t = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                     starting_equity=START, asset="TEST").trades[0]
    assert t.exit_reason == "take_profit"
    assert t.exit_price == 130.0, t.exit_price         # tp fiyatı (open 120 < 130)
    assert np.isclose(t.r_multiple, 3.0), t.r_multiple


def test_same_bar_stop_and_tp_collision_is_pessimistic() -> None:
    """Kabul kriteri 2: aynı barda hem stop hem TP dokunmuşsa STOP kazanır."""
    rows = [(100, 101, 99, 100)] * 7 + [(100.0, 135.0, 85.0, 100.0)] + [(100, 101, 99, 100)] * 5
    df = _mk(rows, stop=90.0, signal_at=5)
    t = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                     starting_equity=START, asset="TEST").trades[0]
    assert t.exit_reason == "stop", t.exit_reason
    assert t.exit_price == 90.0, t.exit_price
    assert t.r_multiple < 0
    # TP önceliği config düzeyinde YASAK
    try:
        ExitConfig(same_bar_priority="tp")
    except ValueError:
        pass
    else:
        raise AssertionError("same_bar_priority='tp' reddedilmeliydi")


def test_time_stop_fires_at_exact_bar_count() -> None:
    n_stop = 90
    rows = [(100, 101, 99, 100)] * (n_stop + 12)
    df = _mk(rows, stop=90.0, signal_at=5)
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    t = res.trades[0]
    assert t.exit_reason == "time_stop", t.exit_reason
    # giriş barı 6; time-stop (t - entry_i) >= 90 -> çıkış barı 96
    assert t.entry_bar == 6
    assert t.exit_bar == 6 + n_stop, (t.entry_bar, t.exit_bar)
    assert t.bars_held == n_stop
    assert t.exit_price == 100.0                       # kapanıştan
    # aday küme kilidi
    for bad in (45, 75, 100, 200):
        try:
            ExitConfig(time_stop_bars=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"time_stop_bars={bad} reddedilmeliydi")


def test_time_stop_candidates_are_all_accepted() -> None:
    for ts_b in DEFAULT_EXIT.time_stop_candidates:
        for tp in DEFAULT_EXIT.take_profit_candidates:
            cfg = ExitConfig(time_stop_bars=ts_b, take_profit_r=tp)
            assert cfg.time_stop_bars == ts_b and cfg.take_profit_r == tp
    try:
        ExitConfig(take_profit_r=2.5)
    except ValueError:
        pass
    else:
        raise AssertionError("take_profit_r=2.5 reddedilmeliydi")
    try:
        ExitConfig(tune_now=True)
    except ValueError as exc:
        assert "YASAK" in str(exc)
    else:
        raise AssertionError("tune_now=True reddedilmeliydi")


# --------------------------------------------------------------------------
# kabul kriteri 3 — stopsuz pozisyon AÇILMAZ
# --------------------------------------------------------------------------

def test_position_without_valid_stop_is_never_opened() -> None:
    rows = [(100, 101, 99, 100)] * 120
    for kwargs in ({"stop_valid": False}, {"stop": np.nan}):
        df = _mk(rows, signal_at=5, **kwargs)
        res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                           starting_equity=START, asset="TEST")
        assert res.trades == [], kwargs
        assert res.config["rejected_no_valid_stop"] >= 1, kwargs
        assert res.metrics["n_trades"] == 0
        assert float(res.equity["equity"].dropna().iloc[-1]) == START


def test_stop_on_wrong_side_of_entry_is_rejected() -> None:
    """Geometri bozuksa (long için stop girişin ÜSTÜNDE) pozisyon açılmaz."""
    rows = [(100, 101, 99, 100)] * 60
    df = _mk(rows, stop=110.0, signal_at=5)            # stop > entry -> geçersiz
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    assert res.trades == []
    assert res.config["rejected_no_valid_stop"] >= 1


def test_entry_on_non_tradable_bar_is_rejected() -> None:
    rows = [(100, 101, 99, 100)] * 60
    df = _mk(rows, stop=90.0, signal_at=5)
    df.loc[df.index[6], "non_tradable"] = True          # giriş barı işlem-dışı
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    assert res.trades == []
    assert res.config["rejected_not_tradable"] >= 1


# --------------------------------------------------------------------------
# stop dondurulmuşluğu
# --------------------------------------------------------------------------

def test_stop_is_frozen_throughout_the_position() -> None:
    """Stop, giriş barındaki DONDURULMUŞ değerdir. Sonraki barlarda stop_long
    kolonu değişse bile pozisyonun stop'u DEĞİŞMEMELİ (Aşama 3 sözleşmesi)."""
    rows = [(100, 101, 99, 100)] * 8 + [(100, 101, 98, 99)] * 2 + [(100, 101, 85, 88)] * 4
    df = _mk(rows, stop=90.0, signal_at=5)
    df["stop_long"] = 90.0
    # Seviye SONRADAN 99'a yükseliyor. AYIRT EDİCİ TEST:
    #   * stop DONDURULMUŞSA (90) -> çıkış bar 10'da, fiyat 90
    #   * stop İZLENSEYDİ (99)    -> çıkış bar 9'da, fiyat 99 olurdu
    df.loc[df.index[8:], "stop_long"] = 99.0
    df.loc[df.index[8:], "stop_valid_long"] = pd.Series(True, index=df.index[8:], dtype=bool)
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    t = res.trades[0]
    assert t.stop_price == 90.0, t.stop_price           # dondurulmuş değer korunur
    assert t.exit_reason == "stop"
    assert t.exit_bar == 10, (t.exit_bar, "izleyen stop olsaydı 9 olurdu")
    assert t.exit_price == 90.0, (t.exit_price, "izleyen stop olsaydı 99 olurdu")
    assert np.isclose(t.r_multiple, -1.0)


# --------------------------------------------------------------------------
# maliyet ve equity tutarlılığı
# --------------------------------------------------------------------------

def test_total_cost_equals_sum_of_per_trade_costs() -> None:
    rows = [(100, 101, 99, 100)] * 200
    rows[40] = (100, 101, 89, 90)                        # bir stop
    rows[90] = (100, 135, 99, 130)                       # bir TP
    df = _mk(rows, stop=90.0, signal_at=5)
    df.loc[df.index[60], "long_signal"] = True
    df.loc[df.index[110], "long_signal"] = True
    res = run_backtest(df, COST, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    assert len(res.trades) >= 2
    total = sum(t.cost_total for t in res.trades)
    assert np.isclose(total, res.metrics["total_cost"], rtol=1e-9), \
        (total, res.metrics["total_cost"])
    ow = COST.one_way_cost_frac
    manual = sum(abs(t.notional_entry) * ow + abs(t.notional_exit) * ow for t in res.trades)
    assert np.isclose(manual, total), (manual, total)
    assert total > 0
    assert np.isclose(res.metrics["total_net"], res.metrics["total_gross"] - total)
    # maliyet satırı (kabul kriteri 7)
    cr = res.metrics["cost_row"]
    assert np.isclose(cr["total_cost"], total)
    assert cr["gross_return_without_cost_frac"] >= cr["net_return_with_cost_frac"]


def test_equity_recomputed_from_trades_matches_engine() -> None:
    """Kabul kriteri 8: equity, trade listesinden BAĞIMSIZ yeniden hesaplanıp
    motorun eğrisiyle karşılaştırılmalı."""
    rng = np.random.default_rng(7)
    rows = []
    px = 100.0
    for _ in range(600):
        px *= float(np.exp(rng.normal(0, 0.01)))
        o = px * (1 + rng.uniform(-0.004, 0.004))
        h = max(o, px) * 1.004
        l = min(o, px) * 0.996
        rows.append((o, h, l, px))
    df = _mk(rows, stop=0.0, signal_at=5)                # stop aşağıda yeniden yazılacak
    df["stop_long"] = pd.to_numeric(df["close"]) * 0.96
    df["stop_valid_long"] = True
    for i in range(10, 590, 17):
        df.loc[df.index[i], "long_signal"] = True
    res = run_backtest(df, COST, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    assert len(res.trades) > 3, len(res.trades)
    indep = equity_from_trades(res.trades, START)
    assert np.isclose(indep[-1], res.trades[-1].equity_after), (indep[-1], res.trades[-1].equity_after)
    assert np.isclose(indep[-1], res.metrics["final_equity"], rtol=1e-6), (
        indep[-1], res.metrics["final_equity"])
    # her trade'in equity_after'i bir öncekinin + net_pnl'i olmalı
    eq = START
    for t in res.trades:
        assert np.isclose(t.equity_before, eq, rtol=1e-9), (t.equity_before, eq)
        eq = t.equity_after
        assert np.isclose(t.equity_after, t.equity_before + t.net_pnl, rtol=1e-9)
    # Pozisyon taşımayan VE giriş/çıkış barı olmayan barlarda equity DÜZ olmalı.
    # (Giriş barında mark-to-market başlar, çıkış barında gerçekleşir; ikisi de
    #  meşru değişimdir — bu yüzden hariç tutulur.)
    eq = res.equity
    entry_bars = {t.entry_bar for t in res.trades}
    exit_bars = {t.exit_bar for t in res.trades}
    prev_open = eq["position_open"].shift(1).fillna(0).astype(int)
    idx = np.arange(len(eq))
    flat_mask = ((eq["position_open"] == 0) & (prev_open == 0)
                 & ~pd.Series(np.isin(idx, sorted(entry_bars | exit_bars)), index=eq.index)
                 & ~pd.Series(np.isin(idx - 1, sorted(entry_bars | exit_bars)), index=eq.index))
    sub = eq.loc[flat_mask]
    assert len(sub) > 50, len(sub)
    # DİKKAT: mask'li diff() bitişik OLMAYAN barları karşılaştırır ve aradaki
    # trade'in gerçekleşmiş P&L'ini "düz değil" gibi gösterir. Bu yüzden
    # yalnızca GERÇEKTEN bitişik olan çiftler karşılaştırılır.
    d = sub["equity"].diff()
    consecutive = np.diff(sub.index.to_numpy()) == 1
    d = d.iloc[1:][consecutive].abs()
    assert len(d) > 20, len(d)
    assert float(d.max()) < 1e-6, float(d.max())
    # maruziyet: her trade için giriş..çıkış barları position_open=1 olmalı
    for t in res.trades[:10]:
        seg = eq["position_open"].iloc[t.entry_bar:t.exit_bar + 1]
        assert (seg == 1).all(), (t.entry_bar, t.exit_bar, seg.tolist())


def test_costs_turn_a_gross_winner_into_a_net_loser_is_reported() -> None:
    rows = [(100, 100.6, 99.6, 100.2)] * 100
    df = _mk(rows, stop=99.0, signal_at=5)
    big = CostModel(commission_bps=400.0, spread_bps=400.0, slippage_bps=400.0)
    res = run_backtest(df, big, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    if res.metrics["n_trades"]:
        cr = res.metrics["cost_row"]
        assert cr["gross_return_without_cost_frac"] > cr["net_return_with_cost_frac"]
        assert cr["verdict"] in ("maliyet sonucu TERSİNE ÇEVİRİYOR", "maliyet öncesi de negatif",
                                 "maliyet sonrası da pozitif")


# --------------------------------------------------------------------------
# short ve yön politikası
# --------------------------------------------------------------------------

def test_short_side_is_symmetric() -> None:
    # short: giriş 100, stop 110 (R = 10), TP = 100 − 3R = 70
    rows = ([(100, 101, 99, 100)] * 7 + [(95, 96, 80, 82)] + [(78, 79, 74, 75)]
            + [(65, 66, 64, 65)] + [(65, 66, 64, 65)] * 4)
    df = _mk(rows, stop=110.0, signal_at=5, direction="short")
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, allow_short=True, asset="TEST")
    t = res.trades[0]
    assert t.direction == "short"
    assert t.entry_bar == 6 and t.entry_price == 100.0
    assert t.tp_price == 70.0, t.tp_price
    assert t.exit_reason == "take_profit", t.exit_reason
    # bar 9 open=65 < tp=70 -> gap lehimize -> OPEN'dan çıkılır (kabul kriteri 2)
    assert t.exit_price == 65.0, t.exit_price
    assert t.exit_bar == 9
    assert t.r_multiple > 3.0, t.r_multiple
    # short stop gap'i de simetrik: open > stop ise open'dan
    rows2 = [(100, 101, 99, 100)] * 7 + [(115, 120, 114, 118)] + [(118, 119, 117, 118)] * 4
    df2 = _mk(rows2, stop=110.0, signal_at=5, direction="short")
    t2 = run_backtest(df2, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                      starting_equity=START, allow_short=True, asset="TEST").trades[0]
    assert t2.exit_reason == "stop" and t2.exit_price == 115.0, (t2.exit_reason, t2.exit_price)
    assert t2.r_multiple < -1.0


def test_short_is_disabled_for_stocks() -> None:
    rows = [(100, 101, 99, 100)] * 6 + [(100, 101, 60, 65)] * 6
    df = _mk(rows, stop=110.0, signal_at=5, direction="short")
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, allow_short=False, asset="TEST")
    assert res.trades == []


def test_allow_short_false_ignores_short_signals_even_if_present() -> None:
    rows = [(100, 101, 99, 100)] * 60
    df = _mk(rows, stop=90.0, signal_at=5)
    df.loc[df.index[20], "short_signal"] = True
    df["stop_short"] = 110.0
    df["stop_valid_short"] = True
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, allow_short=False, asset="TEST")
    assert all(t.direction == "long" for t in res.trades)


# --------------------------------------------------------------------------
# look-ahead
# --------------------------------------------------------------------------

def test_backtest_has_no_lookahead_on_truncated_data() -> None:
    """Son barlar silindiğinde, silinen bölgeden ÖNCEKİ trade'ler birebir aynı
    kalmalı (giriş fiyatı, çıkış fiyatı, R, equity)."""
    rng = np.random.default_rng(11)
    rows = []
    px = 100.0
    for _ in range(800):
        px *= float(np.exp(rng.normal(0.0003, 0.012)))
        o = px * (1 + rng.uniform(-0.005, 0.005))
        rows.append((o, max(o, px) * 1.005, min(o, px) * 0.995, px))
    df = _mk(rows, stop=0.0, signal_at=5)
    df["stop_long"] = pd.to_numeric(df["close"]) * 0.95
    df["stop_valid_long"] = True
    for i in range(12, 790, 13):
        df.loc[df.index[i], "long_signal"] = True
    full = run_backtest(df, COST, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                        starting_equity=START, asset="TEST")
    cut_n = 250
    trunc = run_backtest(df.iloc[:-cut_n].copy(), COST, exit_cfg=DEFAULT_EXIT,
                         risk_per_trade=RISK, starting_equity=START, asset="TEST")

    def key(t):
        return (t.entry_bar, round(t.entry_price, 9), t.exit_reason,
                round(t.exit_price, 9) if np.isfinite(t.exit_price) else None,
                round(t.r_multiple, 9) if np.isfinite(t.r_multiple) else None)

    fk = [key(t) for t in full.trades if t.exit_bar < len(df) - cut_n]
    tk = [key(t) for t in trunc.trades if t.exit_reason != "end_of_data"]
    assert len(tk) > 3, len(tk)
    assert fk[:len(tk)] == tk, (fk[:len(tk)], tk)


def test_signal_on_last_bar_produces_no_trade() -> None:
    rows = [(100, 101, 99, 100)] * 40
    df = _mk(rows, stop=90.0, signal_at=39)              # son barda sinyal
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    assert res.trades == [], "t+1 bar yokken işlem AÇILAMAZ"


def test_open_position_at_end_is_closed_transparently() -> None:
    rows = [(100, 101, 99, 100)] * 30
    df = _mk(rows, stop=10.0, signal_at=5)               # stop çok uzak -> hiç tetiklenmez
    res = run_backtest(df, ZERO, exit_cfg=ExitConfig(time_stop_bars=120),
                       risk_per_trade=RISK, starting_equity=START, asset="TEST")
    assert len(res.trades) == 1
    assert res.trades[0].exit_reason == "end_of_data"
    assert any("AÇIKTI" in w for w in res.warnings), res.warnings


# --------------------------------------------------------------------------
# metrikler
# --------------------------------------------------------------------------

def test_metrics_and_weak_sample_flag() -> None:
    rows = [(100, 101, 99, 100)] * 200
    rows[40] = (100, 101, 89, 90)
    df = _mk(rows, stop=90.0, signal_at=5)
    df.loc[df.index[60], "long_signal"] = True
    res = run_backtest(df, COST, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    m = res.metrics
    assert m["n_trades"] == 2
    assert m["statistically_weak"] is True              # < 100 trade
    assert any("İSTATİSTİKSEL ZAYIF" in w for w in res.warnings)
    assert "bootstrap" in m or m["n_trades"] < 5
    if "bootstrap" in m:
        b = m["bootstrap"]
        assert b["resamples"] == DEFAULT_EXIT.bootstrap_resamples
        lo, hi = b["expectancy_r_ci95"]
        assert lo <= hi
        assert 0.0 <= b["prob_expectancy_positive"] <= 1.0
    for k in ("win_rate", "profit_factor_net", "expectancy_r", "avg_holding_bars",
              "max_drawdown_frac", "net_return_frac", "total_cost", "exit_reason_mix"):
        assert k in m, k
    assert 0.0 <= m["win_rate"] <= 1.0
    assert set(m["exit_reason_mix"]) <= {"stop", "take_profit", "time_stop", "end_of_data"}


def test_buy_hold_reference_is_computed_with_costs() -> None:
    rows = [(100, 101, 99, 100 + i * 0.1) for i in range(50)]
    df = _mk(rows, stop=90.0, signal_at=5)
    bh = buy_hold_reference(df, COST, START)
    p0 = float(df["close"].iloc[0]); p1 = float(df["close"].iloc[-1])
    assert np.isclose(bh["gross_return_frac"], p1 / p0 - 1.0)
    assert np.isclose(bh["net_return_frac"], p1 / p0 - 1.0 - 2 * COST.one_way_cost_frac)
    assert bh["max_drawdown_frac"] <= 0


def test_no_trades_yields_defined_metrics() -> None:
    df = _mk([(100, 101, 99, 100)] * 50, stop=90.0, signal_at=5, stop_valid=False)
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, asset="TEST")
    m = res.metrics
    assert m["n_trades"] == 0 and m["win_rate"] is None and m["profit_factor_net"] is None
    assert m["net_return_frac"] == 0.0
    assert m["statistically_weak"] is True


def test_position_size_respects_risk_and_leverage_cap() -> None:
    rows = [(100, 101, 99, 100)] * 60
    # çok dar stop -> birim sayısı patlar; kaldıraç tavanı devreye girmeli
    df = _mk(rows, stop=99.9, signal_at=5)
    res = run_backtest(df, ZERO, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                       starting_equity=START, max_leverage=2.0, asset="TEST")
    t = res.trades[0]
    assert t.notional_entry <= START * 2.0 + 1e-6, t.notional_entry
    prof = RISK_PROFILES[DEFAULT_PROFILE]
    assert np.isclose(RISK, prof.risk_per_trade)


def test_engine_is_non_destructive() -> None:
    rows = [(100, 101, 99, 100)] * 120
    df = _mk(rows, stop=90.0, signal_at=5)
    before = df[["open", "high", "low", "close", "stop_long"]].to_numpy().copy()
    run_backtest(df, COST, exit_cfg=DEFAULT_EXIT, risk_per_trade=RISK,
                 starting_equity=START, asset="TEST")
    assert np.allclose(df[["open", "high", "low", "close", "stop_long"]].to_numpy(), before)
    assert len(df) == 120


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
