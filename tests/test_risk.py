"""Tests for AŞAMA 8 — risk limitleri + portföy simülatörü.

Kilitlenen garantiler:
  * limits doğrulaması (fail-closed) + profilden enjeksiyon
  * boyutlama matematiği: units = risk/stop_mesafesi; stop kaybı == risk_per_trade×equity
  * kaldıraç kıskacı
  * TAVANSIZ tek akış == Aşama 6 motoru (gerçek BTC verisi, alan alan birebir)
  * TAVANLI gerçek koşuda HİÇBİR zamanda tavan ihlali yok (eşzamanlı/ısı/banka)
  * fren: 4 ardışık kayıp -> 20 bar blok + regresyon (limitsiz 5. giriş olur)
  * günlük/haftalık limit: aşım -> yeni giriş kapalı (fail-closed), çıkışlar serbest
  * toplam/banka/metals-ısı/basket-ısı tavanları + red sayaçları
  * tavanlar çıkışa DOKUNMAZ (capped trade çıkışları == unlimited karşılığı)
  * H35 + geometri redleri simülatörde de geçerli
  * equity zinciri: final == start + Σ net
  * profil kilidi: P0 dışı -> ValueError

Run: python3 -W ignore tests/test_risk.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from quant4h.backtest.engine import run_backtest  # noqa: E402
from quant4h.config import UTC, CostModel, ExitConfig, RISK_PROFILES  # noqa: E402
from quant4h.risk.limits import RiskLimits, bank_codes  # noqa: E402
from quant4h.risk.simulator import StreamSpec, simulate_portfolio  # noqa: E402

COST = CostModel(commission_bps=10.0, spread_bps=6.0, slippage_bps=4.0)   # one_way 17bp
ZERO = CostModel(commission_bps=0.0, spread_bps=0.0, slippage_bps=0.0)
START = 100_000.0
RPT = 0.005
PROF = RISK_PROFILES["balanced"]


def _frame(rows, signals=(), stop=90.0, stop_valid=True, atr=2.0, direction="long",
           start="2024-01-01 00:00:00", symbol="TEST"):
    n = len(rows)
    idx = pd.date_range(start, periods=n, freq="4h", tz=UTC)
    df = pd.DataFrame({"symbol": symbol, "timestamp_utc": idx,
                       "open": [r[0] for r in rows], "high": [r[1] for r in rows],
                       "low": [r[2] for r in rows], "close": [r[3] for r in rows],
                       "volume": [1000.0] * n})
    df["atr"] = atr
    df["non_tradable"] = False
    df["return_valid"] = True
    for c in ("stop_long", "stop_short"):
        df[c] = np.nan
    for c in ("stop_valid_long", "stop_valid_short"):
        df[c] = pd.Series(False, index=df.index, dtype=bool)
    sc = "stop_long" if direction == "long" else "stop_short"
    vc = "stop_valid_long" if direction == "long" else "stop_valid_short"
    df[sc] = stop
    df[vc] = pd.Series(bool(stop_valid), index=df.index, dtype=bool)
    df["long_signal"] = pd.Series(False, index=df.index, dtype=bool)
    df["short_signal"] = pd.Series(False, index=df.index, dtype=bool)
    sig = "long_signal" if direction == "long" else "short_signal"
    for s in signals:
        df.loc[df.index[s], sig] = True
    return df


def _spec(key, df, direction="long", cost=ZERO, is_stock=False, lev=2.0):
    return StreamSpec(key, direction, df, cost, max_leverage=lev, is_stock=is_stock)


# --------------------------------------------------------------------------
# config / kilitler
# --------------------------------------------------------------------------

def test_risk_limits_validation_and_profile_injection() -> None:
    for bad in ({"max_concurrent_total": 0}, {"max_bank_concurrent": 0},
                {"metals_heat_max_rpt_mult": 0.0}, {"max_daily_loss": 0.0},
                {"max_weekly_loss": 0.001, "max_daily_loss": 0.01}):  # hafta < gün
        try:
            RiskLimits(**bad)
            raise AssertionError(f"{bad} ValueError vermeli")
        except ValueError:
            pass
    lim = RiskLimits.from_profile(PROF)
    assert lim.max_daily_loss == 0.02 and lim.max_weekly_loss == 0.05
    assert lim.per_asset_cap("BTC") == 2 and lim.per_asset_cap("GOLD") == 1
    assert lim.per_asset_cap("AEFES") == 1                 # hisse -> max_per_stock
    assert RiskLimits.no_limits().unlimited is True
    banks = bank_codes()
    assert banks == ("AKBNK", "GARAN", "ISCTR", "VAKBN", "YKBNK")


def test_profile_lock_p0_only() -> None:
    df = _frame([(100, 101, 99, 100)] * 4, signals=(0,))
    try:
        simulate_portfolio([_spec("BTC", df)], RiskLimits.no_limits(),
                           risk_per_trade=RPT, exit_cfg=ExitConfig(profile="P1"))
        raise AssertionError("P0 dışı profil ValueError vermeli")
    except ValueError:
        pass


# --------------------------------------------------------------------------
# boyutlama matematiği
# --------------------------------------------------------------------------

def test_sizing_stop_loss_equals_risk_budget() -> None:
    rows = [(100, 101, 99, 100), (100, 101, 99.5, 100), (99, 99.5, 88, 89)]
    sim = simulate_portfolio([_spec("BTC", _frame(rows, signals=(0,)))],
                             RiskLimits.no_limits(), risk_per_trade=RPT,
                             starting_equity=START)
    t = sim.trades[0]
    assert abs(t.units - (RPT * START) / 10.0) < 1e-9      # units = risk / stop mesafesi
    assert abs(t.gross_pnl + RPT * START) < 1e-9           # stop'ta kayıp = risk bütçesi
    assert t.exit_reason == "stop" and t.exit_price == 90.0
    assert abs(t.net_pnl - (t.gross_pnl - t.cost_total)) < 1e-9


def test_leverage_clamp_limits_units() -> None:
    rows = [(100, 101, 99, 100), (100, 101, 99.5, 100), (99.95, 100, 99.9, 99.95)]
    sim = simulate_portfolio([_spec("BTC", _frame(rows, signals=(0,), stop=99.9))],
                             RiskLimits.no_limits(), risk_per_trade=RPT,
                             starting_equity=START)
    t = sim.trades[0]
    # stop mesafesi 0.1 -> units 5000 olurdu; kıskac: equity*2/100 = 2000
    assert abs(t.units - (START * 2.0) / 100.0) < 1e-9


# --------------------------------------------------------------------------
# motor eşitliği (tavansız) + gerçek veride tavan denetimi
# --------------------------------------------------------------------------

def test_unlimited_single_stream_equals_engine() -> None:
    import run_exit_grid as G
    frame = G._signals_for("BTC", "4h", False, None, "A0")
    cost = G.RB._cost_for("BTC", False)
    eng = run_backtest(frame, cost, exit_cfg=ExitConfig(), risk_per_trade=PROF.risk_per_trade,
                       starting_equity=START, max_leverage=PROF.max_leverage,
                       allow_short=False, asset="BTC_long")
    sim = simulate_portfolio([_spec("BTC", frame, cost=cost, lev=PROF.max_leverage)],
                             RiskLimits.no_limits(), risk_per_trade=PROF.risk_per_trade,
                             starting_equity=START)
    assert len(eng.trades) == len(sim.trades) > 50       # BTC long-only: 100 trade
    for a, b in zip(eng.trades, sim.trades):
        assert (a.direction, a.entry_bar, a.exit_bar, a.exit_reason) == \
               (b.direction, b.entry_bar, b.exit_bar, b.exit_reason)
        for f in ("entry_price", "exit_price", "units", "net_pnl", "r_multiple",
                  "cost_total", "equity_after"):
            assert abs(getattr(a, f) - getattr(b, f)) < 1e-9, f


def test_capped_real_run_has_no_violations() -> None:
    import run_exit_grid as G
    import run_risk_report as RR
    codes = G.RB._included(os.path.join(G.ROOT, "reports", "bist30_universe_qc.json"))
    streams = RR.build_streams("4h", codes, PROF)
    sim = simulate_portfolio(streams, RiskLimits.from_profile(PROF),
                             risk_per_trade=PROF.risk_per_trade, starting_equity=START)
    CORE = ("BTC", "GOLD", "SILVER")
    banks = set(bank_codes())

    def risk_of(t):
        return abs(t.entry_price - t.stop_price) * t.units / t.equity_before

    def sweep(pred, weight=lambda t: 1):
        """[entry_ts, exit_ts) aralıklarında ağırlıklı maks çakışma.
        Aynı timestamp'te ÇIKIŞ önce işlenir (simülatör semantiğiyle aynı)."""
        ev = []
        for t in sim.trades:
            if pred(t):
                ev.append((t.entry_timestamp_utc, 0, +1, weight(t)))   # 0: giriş
                ev.append((t.exit_timestamp_utc, -1, -1, -weight(t)))  # -1: çıkış (önce)
        ev.sort(key=lambda e: (e[0], e[1]))
        cur = curw = maxn = maxw = 0.0
        for _, order, dn, w in ev:
            cur += dn
            curw += w
            maxn = max(maxn, cur)
            maxw = max(maxw, curw)
        return maxn, maxw

    n_tot, _ = sweep(lambda t: True)
    assert n_tot <= 6, f"toplam eşzamanlı ihlali: {n_tot}"
    for key, cap in (("BTC", 2), ("GOLD", 1), ("SILVER", 1)):
        n, _ = sweep(lambda t, k=key: t.group_key == k)
        assert n <= cap, f"{key} eşzamanlı ihlali: {n} > {cap}"
    n_basket, heat_basket = sweep(lambda t: t.group_key not in CORE, weight=risk_of)
    assert n_basket <= 3, f"basket eşzamanlı ihlali: {n_basket}"
    assert heat_basket <= 3 * RPT + 1e-9, f"basket ısı ihlali: {heat_basket}"
    _, heat_metals = sweep(lambda t: t.group_key in ("GOLD", "SILVER"), weight=risk_of)
    assert heat_metals <= RPT + 1e-9, f"metals kova ısısı ihlali: {heat_metals}"
    n_bank, _ = sweep(lambda t: t.group_key in banks)
    assert n_bank <= 2, f"banka ihlali: {n_bank}"
    assert int(sim.equity["n_open"].max()) <= 6
    assert sim.peaks["peak_metals_heat"] <= RPT + 1e-9
    assert sim.peaks["peak_basket_heat"] <= 3 * RPT + 1e-9
    # final equity zinciri
    total_net = sum(t.net_pnl for t in sim.trades)
    assert abs(float(sim.equity["equity"].iloc[-1]) - (START + total_net)) < 1e-4


# --------------------------------------------------------------------------
# fren + limitler (sentetik)
# --------------------------------------------------------------------------

def _loss_streak_frame():
    # 4 ardışık stop-out: sig 0,4,8,12 -> giriş 1,5,9,13 -> çıkış 3,7,11,15 (low 88)
    rows = []
    sigs = set()
    for k, s in enumerate((0, 4, 8, 12)):
        sigs.add(s)
    n = 60
    for i in range(n):
        if i in (3, 7, 11, 15):
            rows.append((95, 95.5, 88, 89))       # stop 90 ihlali (gap yok: open 95>90)
        else:
            rows.append((100, 101, 99, 100))
    sigs |= {16, 36}                               # 16: blok içinde; 36: blok dışında
    return _frame(rows, signals=sorted(sigs), atr=50.0)


def test_loss_streak_brake_blocks_and_regression_off() -> None:
    df = _loss_streak_frame()
    lim = RiskLimits(loss_streak_count=4, loss_streak_block_bars=20)
    sim = simulate_portfolio([_spec("BTC", df)], lim, risk_per_trade=RPT,
                             starting_equity=START)
    entries = sorted(t.entry_bar for t in sim.trades)
    assert entries[:4] == [1, 5, 9, 13], entries
    assert 17 not in entries, "fren: 4. kayıptan (bar 15) sonra bar 17 girişi bloklanmalı"
    assert any(e > 35 for e in entries), "blok süresi (15+20=35) bitince giriş serbest"
    assert sim.rejections["loss_streak_brake"] >= 1
    # REGRESYON: fren kapalıysa (unlimited) bar 17'de giriş OLUR
    sim2 = simulate_portfolio([_spec("BTC", df)], RiskLimits.no_limits(),
                              risk_per_trade=RPT, starting_equity=START)
    assert 17 in sorted(t.entry_bar for t in sim2.trades)


def test_daily_loss_limit_blocks_same_day_only() -> None:
    rows = [(100, 101, 99, 100)] * 30
    rows[2] = (95, 95.5, 88, 89)                   # A: bar2'de büyük zarar (−%0.5 realized)
    dfa = _frame(rows, signals=(0,))
    dfb = _frame(rows, signals=(3, 7))             # B: bar3 sinyali AYNI gün (bar4 giriş),
    # bar7 sinyali ertesi gün (bar8 giriş; 6 bar = 24h)
    lim = RiskLimits(max_daily_loss=0.001, max_weekly_loss=0.9)
    sim = simulate_portfolio([_spec("AAA", dfa), _spec("BBB", dfb)], lim,
                             risk_per_trade=RPT, starting_equity=START)
    b_trades = [t for t in sim.trades if t.group_key == "BBB"]
    assert all(t.entry_bar != 4 for t in b_trades), "gün içi giriş kapanmalı"
    assert any(t.entry_bar == 8 for t in b_trades), "ertesi gün giriş serbest"
    assert sim.rejections["daily_loss_limit"] >= 1


def test_weekly_loss_limit_blocks_rest_of_week() -> None:
    # TEK kayıpla haftalık limit tetiklenemez (validasyon: hafta >= gün). Gerçekçi
    # senaryo: 3 AYRI GÜNDE küçük kayıplar (her biri günlük limitin ALTINDA) hafta
    # toplamında limiti aşar -> hafta sonuna kadar girişler kapalı, sonraki hafta açık.
    rows = [(100, 101, 99, 100)] * 60
    for i in (2, 8, 14):                            # 3 stop-out barı (3 ayrı gün)
        rows[i] = (95, 95.5, 88, 89)
    dfa = _frame(rows, signals=(0, 6, 12))          # A: giriş 1/7/13, çıkış 2/8/14
    dfb = _frame(rows, signals=(15, 45))            # B: bar16 AYNI hafta (red), bar46 = 2024-01-08 (hafta 2)
    lim = RiskLimits(max_daily_loss=0.0015, max_weekly_loss=0.0025, loss_streak_count=10)
    sim = simulate_portfolio([_spec("AAA", dfa), _spec("BBB", dfb)], lim,
                             risk_per_trade=0.001, starting_equity=START)
    # kayıplar: her biri 0.001*100k = 100 -> gün bazında 100 < 150 (günlük tetiklenmez),
    # hafta toplamı 300 >= 250 -> haftalık tetiklenir
    a_trades = [t for t in sim.trades if t.group_key == "AAA"]
    assert len(a_trades) == 3 and all(t.net_pnl < 0 for t in a_trades)
    b_entries = [t.entry_bar for t in sim.trades if t.group_key == "BBB"]
    assert 16 not in b_entries and 46 in b_entries
    assert sim.rejections["weekly_loss_limit"] >= 1
    assert sim.rejections["daily_loss_limit"] == 0


# --------------------------------------------------------------------------
# tavanlar (sentetik) + çıkışlara dokunmama
# --------------------------------------------------------------------------

def _flat_rows(n=30):
    return [(100, 101, 99, 100)] * n


def test_total_concurrent_cap_six() -> None:
    streams = [_spec(f"X{k}", _frame(_flat_rows(), signals=(0,))) for k in range(7)]
    sim = simulate_portfolio(streams, RiskLimits(), risk_per_trade=RPT,
                             starting_equity=START)
    assert int(sim.equity["n_open"].max()) <= 6
    assert sim.rejections["total_concurrent"] >= 1
    assert len(sim.trades) == 6                    # 7. akışın başka sinyali yok -> hiç girmez


def test_bank_sector_cap_two() -> None:
    streams = [_spec(b, _frame(_flat_rows(), signals=(0,)), is_stock=True)
               for b in ("AKBNK", "GARAN", "ISCTR")]
    sim = simulate_portfolio(streams, RiskLimits(max_basket_concurrent=6),
                             risk_per_trade=RPT, starting_equity=START)
    entered = {t.group_key for t in sim.trades if t.entry_bar == 1}
    assert len(entered) <= 2
    assert sim.rejections["bank_sector"] >= 1


def test_metals_bucket_heat_single_unit() -> None:
    streams = [_spec("GOLD", _frame(_flat_rows(), signals=(0,))),
               _spec("SILVER", _frame(_flat_rows(), signals=(0,)))]
    sim = simulate_portfolio(streams, RiskLimits(), risk_per_trade=RPT,
                             starting_equity=START)
    entered_at_1 = [t for t in sim.trades if t.entry_bar == 1]
    assert len(entered_at_1) == 1, "GOLD+SILVER aynı anda %0.5+%0.5 ısıyla AÇILAMAZ"
    assert sim.rejections["metals_bucket_heat"] == 1
    assert sim.peaks["peak_metals_heat"] <= RPT + 1e-9


def test_basket_heat_cap_with_relaxed_count() -> None:
    streams = [_spec(f"H{i}", _frame(_flat_rows(), signals=(0,)), is_stock=True)
               for i in range(4)]
    lim = RiskLimits(max_basket_concurrent=6, basket_heat_max_rpt_mult=3.0)
    sim = simulate_portfolio(streams, lim, risk_per_trade=RPT, starting_equity=START)
    assert len([t for t in sim.trades if t.entry_bar == 1]) == 3
    assert sim.rejections["basket_heat"] == 1


def test_caps_never_alter_exits() -> None:
    # 3 banka + 1 core: capped koşuda giren trade'lerin ÇIKIŞLARI unlimited ile birebir
    rows = _flat_rows(20)
    rows[6] = (105, 131, 104, 130)                 # TP 130 dokunuşu (bazı trade'ler TP ile çıkar)
    rows[12] = (95, 95.5, 88, 89)                  # stop dokunuşu
    streams = [_spec(b, _frame(rows, signals=(0, 8)), is_stock=True)
               for b in ("AKBNK", "GARAN", "ISCTR")]
    streams.append(_spec("BTC", _frame(rows, signals=(1,))))
    cap = simulate_portfolio(streams, RiskLimits(), risk_per_trade=RPT, starting_equity=START)
    unc = simulate_portfolio(streams, RiskLimits.no_limits(), risk_per_trade=RPT,
                             starting_equity=START)
    idx = {(t.group_key, t.direction, t.entry_bar): t for t in unc.trades}
    for t in cap.trades:
        u = idx.get((t.group_key, t.direction, t.entry_bar))
        assert u is not None, "capped trade unlimited'ta yok (tavanlar girişten başka etki edemez)"
        assert (t.exit_bar, t.exit_reason) == (u.exit_bar, u.exit_reason)
        assert abs(t.exit_price - u.exit_price) < 1e-12


def test_h35_and_geometry_rejections_in_simulator() -> None:
    df_inv = _frame(_flat_rows(6), signals=(0,), stop_valid=False)
    df_geo = _frame(_flat_rows(6), signals=(0,), stop=105.0)   # long'da stop > giriş
    sim = simulate_portfolio([_spec("A", df_inv), _spec("B", df_geo)],
                             RiskLimits.no_limits(), risk_per_trade=RPT,
                             starting_equity=START)
    assert len(sim.trades) == 0
    assert sim.rejections["no_valid_stop"] >= 1
    assert sim.rejections["stop_geometry"] >= 1


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
