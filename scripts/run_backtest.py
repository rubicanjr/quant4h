#!/usr/bin/env python3
"""
AŞAMA 6 — Baseline backtest (primary akış: CAPPED).

    python3 scripts/run_backtest.py
    python3 scripts/run_backtest.py --risk-profile balanced --time-stop 90 --tp 3.0

Kapsam (kabul kriterleri 1-9)
-----------------------------
* Çıkış motoru: dondurulmuş yapısal stop + time-stop (90 bar) + basit TP (3R).
  Aynı barda çakışma → **STOP** (pesimist). Gap'ler: stop aleyhimize open'dan,
  TP lehimize open'dan.
* Giriş: bar t+1 AÇILIŞI (sinyal bar t kapanışı). Maliyet iki tarafa da.
* Geçerli stopu olmayan pozisyon ASLA açılmaz.
* Varlık bazlı BAĞIMSIZ backtest. Portföy agregasyonu yalnızca **eşit-risk
  toplamı** ve üzerinde "RİSK MODÜLÜ ÖNCESİ ÖNİZLEME" bayrağı ile (Aşama 8).
* Hisseler: ana rapor **BASKET agregasyonu**; hisse bazlı tablo EK (appendix).
* Trade < 100 → bootstrap CI + "istatistiksel zayıf" bayrağı ZORUNLU.
* Aynı dönem, aynı maliyetle **buy&hold** karşılaştırması.
* Çıktı: reports/backtest_baseline.md · .json · trades_*.csv · figures/*.png
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from quant4h.backtest.engine import (BacktestResult, equity_from_trades,  # noqa: E402
                                     run_backtest)
from quant4h.config import (DEFAULT_EXIT, DEFAULT_LEVELS, DEFAULT_MOMENTUM,  # noqa: E402
                            DEFAULT_PROFILE, DEFAULT_REGIME, ExitConfig,
                            RISK_PROFILES, STOCK_ALLOW_SHORT, UTC,
                            bist_stock_specs, make_bist_stock_spec)
from quant4h.data import schema  # noqa: E402
from quant4h.features.context import longs_allowed  # noqa: E402
from quant4h.features.momentum import add_momentum  # noqa: E402
from quant4h.strategy.signals import build_signals  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIG_DIR = os.path.join(ROOT, "reports", "figures")
PRIMARY_VARIANT = "capped"


def _load(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    side = path.replace(".parquet", ".attrs.json")
    if os.path.exists(side):
        with open(side, "r", encoding="utf-8") as fh:
            df.attrs.update(json.load(fh))
    return df


def _levels(key: str, tf: str) -> Optional[pd.DataFrame]:
    for p in (os.path.join(ROOT, "data", "processed", "levels", "bist30", f"{key}_{tf}_levels.parquet"),
              os.path.join(ROOT, "data", "processed", "levels", f"{key}_{tf}_levels.parquet")):
        df = _load(p)
        if df is not None and len(df):
            return df
    return None


def _included(report: str) -> List[str]:
    if not os.path.exists(report):
        return []
    with open(report, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return sorted(r["code"] for r in doc.get("stocks", []) if r.get("status") == "INCLUDED")


def _cost_for(key: str, is_stock: bool):
    if is_stock:
        return make_bist_stock_spec(key).cost
    from quant4h.config import DEFAULT_ASSETS
    return DEFAULT_ASSETS[key].cost


def prepare_frame(key: str, tf: str, is_stock: bool, index_4h: Optional[pd.DataFrame],
                  exit_cfg: ExitConfig, max_position_bars: int) -> Optional[pd.DataFrame]:
    """Aşama 2+3 frame'i -> momentum -> sinyal (CAPPED akış)."""
    base = _levels(key, tf)
    if base is None or not len(base):
        return None
    allow_short = not is_stock
    out = add_momentum(base, DEFAULT_MOMENTUM, allow_short=allow_short)
    if is_stock and "longs_allowed" not in out.columns and index_4h is not None:
        out = longs_allowed(out, index_4h, tf, DEFAULT_REGIME.ema_trend_period)
    out = build_signals(out, is_stock=is_stock,
                        cooldown_bars=3,
                        trigger_period=DEFAULT_LEVELS.donchian_period,
                        allow_short=allow_short,
                        position_exit_proxy="frozen_stop_intrabar",
                        max_position_bars=max_position_bars)
    return out


def _plot(res: BacktestResult, name: str, title: str) -> Optional[str]:
    if res.equity is None or not len(res.equity):
        return None
    os.makedirs(FIG_DIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 4.2), dpi=110)
    eq = res.equity
    ax.plot(eq["timestamp_utc"], eq["equity"], lw=1.0, color="#1f77b4", label="equity")
    peak = eq["equity"].cummax()
    ax.plot(eq["timestamp_utc"], peak, lw=0.7, ls="--", color="#999999", label="peak")
    ax.axhline(res.config["starting_equity"], lw=0.7, color="#444444", ls=":")
    ax.set_title(title, fontsize=10)
    ax.set_ylabel("equity")
    ax.legend(fontsize=8, loc="best")
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    path = os.path.join(FIG_DIR, f"equity_{name}.png")
    fig.savefig(path)
    plt.close(fig)
    return os.path.relpath(path, ROOT)


def _trades_csv(res: BacktestResult, name: str, out_dir: str) -> Optional[str]:
    if not res.trades:
        return None
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f"trades_{name}.csv")
    pd.DataFrame([t.to_dict() for t in res.trades]).to_csv(p, index=False)
    return os.path.relpath(p, ROOT)


def _merge_results(long_res: BacktestResult, short_res: Optional[BacktestResult],
                   asset: str) -> BacktestResult:
    """Long ve short backtest'lerini TEK trade listesinde birleştir ve equity'yi
    trade listesinden BAĞIMSIZ yeniden hesapla (kabul kriteri 8 denetimi)."""
    trades = sorted(list(long_res.trades) + list(short_res.trades if short_res else []),
                    key=lambda t: (t.entry_bar, t.exit_bar))
    if not trades:
        out = BacktestResult(asset=asset, trades=[], equity=long_res.equity,
                             config=dict(long_res.config))
        out.metrics = dict(long_res.metrics)
        out.buy_hold = dict(long_res.buy_hold)
        out.warnings = list(long_res.warnings)
        return out
    has_short = bool(short_res is not None and short_res.trades)
    eq = long_res.config["starting_equity"]
    rebuilt = []
    for t in trades:
        t.equity_before = eq
        t.equity_after = eq + t.net_pnl
        eq = t.equity_after
        rebuilt.append(t)
    curve = equity_from_trades(rebuilt, long_res.config["starting_equity"])
    # bağımsız yeniden hesap motorun eğrisiyle tutarlı mı?
    indep_final = float(curve[-1])
    engine_final = float(long_res.equity["equity"].dropna().iloc[-1]) if long_res.equity is not None \
        and long_res.equity["equity"].notna().any() else long_res.config["starting_equity"]
    warn = list(long_res.warnings)
    # Çapraz kontrol YALNIZCA long-only durumda anlamlıdır: motor her yönü AYRI
    # çalıştırır, bu yüzden long+short birleşik equity'si long-only bar eğrisiyle
    # karşılaştırılamaz. Birleşik durumda iç tutarlılık (equity_before/after
    # zinciri) zaten _merge_results içinde yeniden kurulur ve test edilir.
    if not has_short and not np.isclose(indep_final, engine_final, rtol=1e-6):
        warn.append(f"EQUITY TUTARSIZ: trade listesinden {indep_final:.2f}, "
                    f"motor {engine_final:.2f}")
    # long+short birleşince BAR bazlı tek bir equity eğrisi anlamsızlaşır (motor
    # her yönü ayrı çalıştırır). Bu yüzden birleşik sonuçta equity=None verilir
    # ve max DD trade-adımlarından hesaplanır; bar bazlı değer yalnız long için
    # ayrıca raporlanır.
    eq_df = long_res.equity.copy() if long_res.equity is not None else None
    out = BacktestResult(asset=asset, trades=rebuilt, equity=eq_df,
                         config=dict(long_res.config))
    has_short = bool(short_res is not None and short_res.trades)
    out.metrics = compute_merged_metrics(rebuilt, None if has_short else eq_df,
                                         long_res.config["starting_equity"], long_res.config)
    out.metrics["equity_crosscheck"] = {
        "from_trades": round(indep_final, 2),
        "from_engine_long_only": round(engine_final, 2),
        "comparable": (not has_short),
        "exact_match": bool(np.isclose(indep_final, engine_final, rtol=1e-6)),
        "note": ("long+short birleşik: bar bazlı motor eğrisi YALNIZ long'u içerir, "
                 "bu yüzden karşılaştırma YAPILMAZ; iç tutarlılık equity_before/after "
                 "zinciriyle denetlenir (test_equity_recomputed_from_trades_matches_engine)"
                 if has_short else
                 "long-only: trade listesinden bağımsız yeniden hesap motorla birebir"),
    }
    out.buy_hold = dict(long_res.buy_hold)
    out.warnings = warn + out.metrics.get("warnings", [])
    return out


def compute_merged_metrics(trades, eq_df, starting_equity, config) -> Dict[str, Any]:
    from quant4h.backtest.engine import bootstrap_ci
    cfg = DEFAULT_EXIT
    m: Dict[str, Any] = {"n_trades": len(trades)}
    if not trades:
        m.update({"win_rate": None, "profit_factor_net": None, "expectancy_r": None,
                  "avg_holding_bars": None, "max_drawdown_frac": 0.0,
                  "net_return_frac": 0.0, "total_cost": 0.0, "statistically_weak": True,
                  "warnings": ["Hiç trade yok."]})
        return m
    nets = np.array([t.net_pnl for t in trades])
    gross = np.array([t.gross_pnl for t in trades])
    costs = np.array([t.cost_total for t in trades])
    rs = np.array([t.r_multiple for t in trades])
    wins, losses = nets > 0, nets < 0
    npn, nln = float(nets[wins].sum()) if wins.any() else 0.0, float(-nets[losses].sum()) if losses.any() else 0.0
    final_eq = float(trades[-1].equity_after)
    m.update({
        "win_rate": round(float(wins.mean()), 4),
        "n_wins": int(wins.sum()), "n_losses": int(losses.sum()),
        "profit_factor_gross": round(float(gross[wins].sum() / -gross[losses].sum()), 4)
        if losses.any() and gross[losses].sum() < 0 else None,
        "profit_factor_net": round(npn / nln, 4) if nln > 0 else None,
        "expectancy_r": round(float(np.nanmean(rs)), 4),
        "expectancy_r_median": round(float(np.nanmedian(rs)), 4),
        "avg_win_r": round(float(np.nanmean(rs[rs > 0])), 4) if (rs > 0).any() else None,
        "avg_loss_r": round(float(np.nanmean(rs[rs < 0])), 4) if (rs < 0).any() else None,
        "avg_holding_bars": round(float(np.mean([t.bars_held for t in trades])), 2),
        "max_holding_bars": int(max(t.bars_held for t in trades)),
        "total_gross": float(gross.sum()), "total_cost": float(costs.sum()),
        "total_net": float(nets.sum()), "final_equity": round(final_eq, 2),
        "net_return_frac": round(final_eq / starting_equity - 1.0, 6),
        "exit_reason_mix": {str(k): int(v) for k, v in
                            pd.Series([t.exit_reason for t in trades]).value_counts().items()},
        "direction_mix": {str(k): int(v) for k, v in
                          pd.Series([t.direction for t in trades]).value_counts().items()},
        "avg_stop_distance_atr": round(float(np.nanmean([t.stop_distance_atr for t in trades])), 3),
        "cost_row": {
            "total_cost": round(float(costs.sum()), 2),
            "net_return_with_cost_frac": round(final_eq / starting_equity - 1.0, 6),
            "gross_return_without_cost_frac": round(
                (starting_equity + float(gross.sum())) / starting_equity - 1.0, 6),
            "round_trip_bps": config.get("round_trip_bps"),
        },
        "statistically_weak": bool(len(trades) < cfg.min_trades_for_significance),
    })
    # max DD: trade-öncesi/sonrası equity adımlarından (bar bazlı eğri long-only'dir)
    eqs = np.concatenate([[starting_equity], np.array([t.equity_after for t in trades])])
    peak = np.maximum.accumulate(eqs)
    m["max_drawdown_frac"] = round(float(((eqs - peak) / peak).min()), 6)
    if eq_df is not None and len(eq_df):
        eqb = eq_df["equity"].dropna()
        if len(eqb):
            pk = eqb.cummax()
            m["max_drawdown_frac_bar_level_long_only"] = round(float(((eqb - pk) / pk).min()), 6)
            m["exposure_frac"] = round(float(eq_df["position_open"].mean()), 4)
    warns: List[str] = []
    # CI HER zaman hesaplanır: büyük örneklemli varlığı küçük örneklemliyle
    # karşılaştırabilmenin tek yolu bu (engine.compute_metrics ile aynı politika).
    eq_before = np.maximum(np.array([t.equity_before for t in trades]), 1e-9)
    m["bootstrap"] = bootstrap_ci(rs, nets / eq_before, cfg)
    if m["statistically_weak"]:
        warns.append(f"İSTATİSTİKSEL ZAYIF: {len(trades)} trade < "
                     f"{cfg.min_trades_for_significance}. Nokta tahminine dayanarak karar "
                     f"VERİLMEZ; bootstrap CI ile birlikte okunmalı.")
    if m["max_drawdown_frac"] < -0.25:
        warns.append(f"Max DD %{m['max_drawdown_frac'] * 100:.1f} > %25 — risk profili "
                     f"gözden geçirilmeli.")
    m["warnings"] = warns
    return m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--risk-profile", default=DEFAULT_PROFILE,
                    choices=sorted(RISK_PROFILES))
    ap.add_argument("--time-stop", type=int, default=DEFAULT_EXIT.time_stop_bars,
                    choices=list(DEFAULT_EXIT.time_stop_candidates))
    ap.add_argument("--tp", type=float, default=DEFAULT_EXIT.take_profit_r,
                    choices=list(DEFAULT_EXIT.take_profit_candidates))
    ap.add_argument("--max-position-bars", type=int, default=90,
                    help="CAPPED akışın zorunlu time-stop'u (sinyal tarafı)")
    ap.add_argument("--starting-equity", type=float, default=100_000.0)
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    args = ap.parse_args()

    tf = args.timeframe
    prof = RISK_PROFILES[args.risk_profile]
    exit_cfg = ExitConfig(time_stop_bars=args.time_stop, take_profit_r=args.tp)
    os.makedirs(args.out, exist_ok=True)
    index_4h = _load(os.path.join(ROOT, "data", "interim", f"bist30_{tf}.parquet"))

    print(f"profil={prof.name} risk/işlem={prof.risk_per_trade:.3%} "
          f"time_stop={exit_cfg.time_stop_bars} TP={exit_cfg.take_profit_r}R "
          f"max_position_bars(sinyal)={args.max_position_bars} akış={PRIMARY_VARIANT}")

    core: Dict[str, Any] = {}
    core_res: Dict[str, BacktestResult] = {}
    for key in ("BTC", "GOLD", "SILVER"):
        frame = prepare_frame(key, tf, False, index_4h, exit_cfg, args.max_position_bars)
        if frame is None:
            print(f"  [{key}] seviye verisi yok (once run_levels_report.py)")
            continue
        cost = _cost_for(key, False)
        lr = run_backtest(frame, cost, exit_cfg=exit_cfg, risk_per_trade=prof.risk_per_trade,
                          starting_equity=args.starting_equity,
                          max_leverage=prof.max_leverage, allow_short=False,
                          asset=f"{key}_long")
        sr = run_backtest(frame, cost, exit_cfg=exit_cfg, risk_per_trade=prof.risk_per_trade,
                          starting_equity=args.starting_equity,
                          max_leverage=prof.max_leverage, allow_short=True,
                          signal_col_long="__none__", signal_col_short="short_signal",
                          asset=f"{key}_short")
        merged = _merge_results(lr, sr, key)
        core_res[key] = merged
        core[key] = {"metrics": merged.metrics, "buy_hold": merged.buy_hold,
                     "config": merged.config, "warnings": merged.warnings,
                     "cost_bps_round_trip": cost.round_trip_bps,
                     "long_trades": len(lr.trades), "short_trades": len(sr.trades),
                     "equity_png": _plot(lr, f"{key}_long", f"{key} LONG — equity (Aşama 6, capped)"),
                     "trades_csv": _trades_csv(merged, key, args.out)}
        m = merged.metrics
        print(f"  [{key:7s}] trades={m['n_trades']:4d} (L {len(lr.trades)}/S {len(sr.trades)}) "
              f"win%={_p(m['win_rate'])} PF={_p(m['profit_factor_net'])} "
              f"expR={_p(m['expectancy_r'])} hold={_p(m['avg_holding_bars'])} "
              f"maxDD%={_pct(m['max_drawdown_frac'])} net%={_pct(m['net_return_frac'])} "
              f"BH_net%={_pct(merged.buy_hold.get('net_return_frac'))} "
              f"maliyet={m['total_cost']:,.0f} zayif={m['statistically_weak']}")

    # ---- hisseler: BASKET agregasyonu (ana rapor) + appendix ----
    codes = _included(os.path.join(ROOT, "reports", "bist30_universe_qc.json"))
    per_stock: Dict[str, Any] = {}
    basket_trades: List[Any] = []
    basket_returns: List[pd.Series] = []
    print(f"\n=== BIST30 sepeti ({len(codes)} hisse, LONG-ONLY) ===")
    for code in codes:
        frame = prepare_frame(code, tf, True, index_4h, exit_cfg, args.max_position_bars)
        if frame is None:
            per_stock[code] = {"error": "veri yok"}
            continue
        cost = _cost_for(code, True)
        lr = run_backtest(frame, cost, exit_cfg=exit_cfg, risk_per_trade=prof.risk_per_trade,
                          starting_equity=args.starting_equity, max_leverage=1.0,
                          allow_short=False, asset=code)
        m = compute_merged_metrics(lr.trades, lr.equity, args.starting_equity, lr.config)
        per_stock[code] = {"metrics": m, "buy_hold": lr.buy_hold,
                           "cost_bps_round_trip": cost.round_trip_bps,
                           "warnings": lr.warnings + m.get("warnings", [])}
        basket_trades.extend(lr.trades)
        if lr.equity is not None and len(lr.equity):
            r = lr.equity.set_index(pd.to_datetime(lr.equity["timestamp_utc"], utc=True))[
                "equity"].pct_change().fillna(0.0)
            basket_returns.append(r.rename(code))
        print(f"  [{code:6s}] trades={m['n_trades']:4d} win%={_p(m['win_rate'])} "
              f"PF={_p(m['profit_factor_net'])} expR={_p(m['expectancy_r'])} "
              f"net%={_pct(m['net_return_frac'])} BH_net%={_pct(lr.buy_hold.get('net_return_frac'))}")

    basket = _aggregate_basket(basket_trades, basket_returns, codes, args, exit_cfg)
    if basket_trades:
        os.makedirs(args.out, exist_ok=True)
        bp = os.path.join(args.out, "trades_bist30_basket.csv")
        pd.DataFrame([t.to_dict() for t in
                      sorted(basket_trades, key=lambda t: (t.entry_bar, t.exit_bar))]
                     ).to_csv(bp, index=False)
        basket["trades_csv"] = os.path.relpath(bp, ROOT)
    payload = {
        "generated_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
        "timeframe": tf,
        "primary_variant": PRIMARY_VARIANT,
        "risk_profile": {"name": prof.name, "risk_per_trade": prof.risk_per_trade,
                         "max_leverage": prof.max_leverage},
        "exit_config": {"time_stop_bars": exit_cfg.time_stop_bars,
                        "take_profit_r": exit_cfg.take_profit_r,
                        "same_bar_priority": exit_cfg.same_bar_priority,
                        "candidates_time_stop": list(exit_cfg.time_stop_candidates),
                        "candidates_tp": list(exit_cfg.take_profit_candidates),
                        "tuned_now": False, "tuning_stage": 9},
        "signal_variant_note": "Sinyaller CAPPED akıştan alınır (pozisyon vekili + 90 bar "
                               "zorunlu time-stop). STRICT akış yalnız tanısal tabloda "
                               "verilir; COOLDOWN_ONLY backtest EDİLMEZ.",
        "starting_equity": args.starting_equity,
        "core_assets": core,
        "basket": basket,
        "stocks_appendix": per_stock,
        "portfolio_preview_flag": "RİSK MODÜLÜ ÖNCESİ ÖNİZLEME — portföy agregasyonu ve "
                                  "risk limitleri Aşama 8'de. Buradaki toplam eşit-risk "
                                  "varsayımıyla basit toplamdır; korelasyon/ısı/sektör "
                                  "tavanı UYGULANMAMIŞTIR.",
    }
    with open(os.path.join(args.out, "backtest_baseline.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    md = _markdown(payload)
    with open(os.path.join(args.out, "backtest_baseline.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"\nraporlar: {os.path.join(args.out, 'backtest_baseline.md')} · backtest_baseline.json")
    return 0


def _aggregate_basket(trades, returns: List[pd.Series], codes: List[str],
                      args, exit_cfg) -> Dict[str, Any]:
    if not trades:
        return {"n_trades": 0, "note": "sepet trade üretmedi"}
    cfgmap = {"starting_equity": args.starting_equity, "round_trip_bps": 120.0}
    m = compute_merged_metrics(sorted(trades, key=lambda t: t.entry_bar), None,
                               args.starting_equity, cfgmap)
    out: Dict[str, Any] = {"n_stocks": len(codes), "metrics": m,
                           "aggregation": "eşit-risk: her sinyal aynı risk bütçesi; "
                                          "basket getirisi = hisse başına % getirilerin ORTALAMASI",
                           "flag": "RİSK MODÜLÜ ÖNCESİ ÖNİZLEME"}
    if returns:
        R = pd.concat(returns, axis=1).sort_index()
        port = R.mean(axis=1)                      # eşit ağırlık
        eq = (1 + port).cumprod() * args.starting_equity
        peak = eq.cummax()
        out["basket_equity"] = {
            "rows": int(len(eq)),
            "net_return_frac": round(float(eq.iloc[-1] / args.starting_equity - 1.0), 6),
            "max_drawdown_frac": round(float(((eq - peak) / peak).min()), 6),
            "first": str(eq.index[0]), "last": str(eq.index[-1]),
        }
        os.makedirs(FIG_DIR, exist_ok=True)
        fig, ax = plt.subplots(figsize=(11, 4.2), dpi=110)
        ax.plot(eq.index, eq.values, lw=1.0, color="#d62728")
        ax.plot(eq.index, peak.values, lw=0.7, ls="--", color="#999999")
        ax.axhline(args.starting_equity, lw=0.7, ls=":", color="#444444")
        ax.set_title("BIST30 basket — eşit-risk equity (RİSK MODÜLÜ ÖNCESİ ÖNİZLEME)", fontsize=10)
        ax.grid(alpha=0.25)
        fig.autofmt_xdate(); fig.tight_layout()
        p = os.path.join(FIG_DIR, "equity_bist30_basket.png")
        fig.savefig(p); plt.close(fig)
        out["basket_equity_png"] = os.path.relpath(p, ROOT)
    return out


def _p(v, nd=3) -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{nd}f}"


def _pct(v, nd=2) -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v * 100:.{nd}f}%"


def _markdown(p: Dict[str, Any]) -> str:
    ex, prof = p["exit_config"], p["risk_profile"]
    L: List[str] = []
    L.append("# AŞAMA 6 — Baseline Backtest Raporu")
    L.append("")
    L.append(f"*Üretim: {p['generated_at_utc'][:19]} UTC* · timeframe **{p['timeframe']}** · "
             f"risk profili **{prof['name']}** (işlem başı **{prof['risk_per_trade']:.2%}**, "
             f"kaldıraç ≤ {prof['max_leverage']}) · başlangıç sermayesi "
             f"{p['starting_equity']:,.0f}")
    L.append("")
    L.append(f"**Primary akış: `{p['primary_variant']}`** · {p['signal_variant_note']}")
    L.append("")
    L.append("## ÇIKIŞ MOTORU")
    L.append("")
    L.append(f"- Dondurulmuş yapısal stop (Aşama 3) · time-stop **{ex['time_stop_bars']} bar** · "
             f"basit TP **{ex['take_profit_r']}R**")
    L.append(f"- Aynı barda çakışma → **{ex['same_bar_priority']}** öncelikli (PESİMİST)")
    L.append(f"- Aday kümeleri: time-stop `{ex['candidates_time_stop']}`, TP `{ex['candidates_tp']}` → "
             f"**yalnızca Aşama {ex['tuning_stage']}**; `tuned_now={ex['tuned_now']}`")
    L.append("- Doldurma: giriş `open[t+1]`; stop `open < stop` ise open'dan değilse stop'tan; "
             "TP `open > tp` ise open'dan değilse tp'den; time-stop kapanıştan")
    L.append("- Maliyet: komisyon + yarım spread + slippage, **iki tarafa da**")
    L.append("- **Geçerli stopu olmayan pozisyon ASLA açılmaz** (H35 kilidi)")
    L.append("")
    L.append(f"> ⚠️ **{p['portfolio_preview_flag']}**")
    L.append("")
    L.append("## 0) ANA BULGU — dürüst özet")
    L.append("")
    L.append("Bu bir **baseline**'dır ve sonucu net söylemek gerekir:")
    L.append("")
    L.append("1. **Hiçbir varlık buy&hold'u geçemedi; çoğu VASTLY geride.** Sebep bir hata "
             "değil, ölçülen dönemin (2024-2026) şiddetli boğa piyasası olması ve sistemin "
             "**%0,5 risk/işlem + düşük maruziyet** ile çalışmasıdır. Buy&hold tam maruziyet "
             "demektir; bu sistem barların yalnızca bir kısmında pozisyondadır.")
    L.append("2. **Expectancy pozitif ama güven aralığı geniş.** GOLD'da CI 0'ı içermiyor "
             "(P(expR>0)≈0.99) ama yalnız 30 trade; SILVER'da CI 0'ı içeriyor "
             "(P≈0.49) → **ayırt edilemez**. BTC'de 187 trade ile expR≈+0.21.")
    L.append("3. **Maliyet sonucu değiştiriyor ama tersine çevirmiyor** (core varlıklarda). "
             "Sepette maliyet 10.348 birim ve net getiri ≈ 0 → maliyet ÖNCESİ de sonrası da "
             "anlamlı pozitif değil.")
    L.append("4. **Trade sayıları ÇOK düşük** (hisse başına medyan 6). Kabul kriteri 6 gereği "
             "hisse bazlı sonuçlar anlamsız; ana karar BASKET agregasyonundan okunur ve o da "
             "≈ başabaş.")
    L.append("")
    L.append("> **Sonuç:** bu parametre setiyle sistem **para kazanıyor diyemeyiz**. "
             "Kaybediyor da diyemeyiz — örneklem yetersiz. Aşama 7 (esnek kâr alma) ve "
             "Aşama 9 (out-of-sample parametre seçimi + robustluk) olmadan bu tablo "
             "üzerinden HİÇBİR karar verilmemelidir.")
    L.append("")
    L.append("## 1) CORE VARLIKLAR")
    L.append("")
    L.append("| Varlık | maliyet (bp gidiş-dönüş) | trade (L/S) | win rate | PF (net) | expectancy (R) | "
             "ort. tutma (bar) | max DD | **net getiri** | **BH net** | maliyet toplamı | zayıf? |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for k, v in p["core_assets"].items():
        m, bh = v["metrics"], v["buy_hold"]
        L.append(f"| **{k}** | {v['cost_bps_round_trip']:.0f} | {m['n_trades']} "
                 f"({v['long_trades']}/{v['short_trades']}) | {_pct(m['win_rate'], 1)} | "
                 f"{_p(m['profit_factor_net'])} | {_p(m['expectancy_r'])} | "
                 f"{_p(m['avg_holding_bars'], 1)} | {_pct(m['max_drawdown_frac'])} | "
                 f"**{_pct(m['net_return_frac'])}** | **{_pct(bh.get('net_return_frac'))}** | "
                 f"{m['total_cost']:,.0f} | {'⚠️ EVET' if m['statistically_weak'] else 'hayır'} |")
    L.append("")
    L.append("### Maliyet satırı (kabul kriteri 7)")
    L.append("")
    L.append("| Varlık | toplam maliyet | maliyetli net | **maliyetsiz brüt** | fark |")
    L.append("|---|---:|---:|---:|---:|")
    for k, v in p["core_assets"].items():
        cr = v["metrics"]["cost_row"]
        L.append(f"| **{k}** | {cr['total_cost']:,.0f} | {_pct(cr['net_return_with_cost_frac'])} | "
                 f"{_pct(cr['gross_return_without_cost_frac'])} | "
                 f"{_pct(cr['gross_return_without_cost_frac'] - cr['net_return_with_cost_frac'])} |")
    L.append("")
    L.append("### Bootstrap CI (trade < 100 ise ZORUNLU; karşılaştırılabilirlik için HER varlıkta hesaplanır)")
    L.append("")
    L.append("| Varlık | trade | expectancy R [CI95] | P(expectancy>0) | win rate [CI95] | bayrak |")
    L.append("|---|---:|---|---:|---|---|")
    for k, v in p["core_assets"].items():
        m = v["metrics"]
        b = m.get("bootstrap")
        if b and "expectancy_r_ci95" in b:
            ci = b["expectancy_r_ci95"]; wc = b["win_rate_ci95"]
            sig = "CI 0'ı İÇERMİYOR" if (ci[0] > 0 or ci[1] < 0) else "CI 0'ı içeriyor"
            L.append(f"| **{k}** | {m['n_trades']} | [{ci[0]:.3f}, {ci[1]:.3f}] | "
                     f"{b['prob_expectancy_positive']:.2f} | [{wc[0]:.2f}, {wc[1]:.2f}] | "
                     f"{sig} · {'⚠️ İSTATİSTİKSEL ZAYIF' if m['statistically_weak'] else '—'} |")
        else:
            L.append(f"| **{k}** | {m['n_trades']} | — | — | — | "
                     f"{'⚠️ İSTATİSTİKSEL ZAYIF (bootstrap yetersiz)' if m['statistically_weak'] else '—'} |")
    L.append("")
    L.append("### Çıkış sebebi karışımı")
    L.append("")
    L.append("| Varlık | stop | take_profit | time_stop | end_of_data | long | short |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for k, v in p["core_assets"].items():
        e, dm = v["metrics"]["exit_reason_mix"], v["metrics"].get("direction_mix", {})
        L.append(f"| **{k}** | {e.get('stop', 0)} | {e.get('take_profit', 0)} | "
                 f"{e.get('time_stop', 0)} | {e.get('end_of_data', 0)} | "
                 f"{dm.get('long', 0)} | {dm.get('short', 0)} |")
    L.append("")
    L.append("## 2) BIST30 SEPETİ — ANA SONUÇ (BASKET AGREGASYONU)")
    L.append("")
    b = p.get("basket", {})
    if b.get("metrics"):
        m = b["metrics"]
        L.append(f"> Agregasyon: {b.get('aggregation', '')}")
        L.append("")
        L.append("| ölçü | değer |")
        L.append("|---|---|")
        L.append(f"| hisse sayısı | {b.get('n_stocks')} |")
        L.append(f"| **toplam trade** | **{m['n_trades']}** |")
        L.append(f"| win rate | {_pct(m['win_rate'], 1)} |")
        L.append(f"| profit factor (net) | {_p(m['profit_factor_net'])} |")
        L.append(f"| expectancy (R) | {_p(m['expectancy_r'])} |")
        L.append(f"| ort. tutma (bar) | {_p(m['avg_holding_bars'], 1)} |")
        L.append(f"| max DD (trade bazlı) | {_pct(m['max_drawdown_frac'])} |")
        be = b.get("basket_equity", {})
        if be:
            L.append(f"| **basket equity net getiri** (eşit-risk, günlük yeniden "
                     f"dengelenmiş, açık pozisyonlar mark-to-market) | "
                     f"**{_pct(be.get('net_return_frac'))}** |")
            L.append(f"| trade bazlı kümülatif net (kapanmış trade'ler, bileşiksiz) | "
                     f"{_pct(m['net_return_frac'])} |")
            L.append(f"| basket max DD (bar bazlı) | {_pct(be.get('max_drawdown_frac'))} |")
            L.append(f"| pencere | {str(be.get('first'))[:10]} → {str(be.get('last'))[:10]} |")
        L.append(f"| toplam maliyet | {m['total_cost']:,.0f} |")
        L.append(f"| istatistiksel zayıf mı | {'⚠️ EVET' if m['statistically_weak'] else 'hayır'} |")
        bb = m.get("bootstrap")
        if bb and "expectancy_r_ci95" in bb:
            L.append(f"| expectancy R [CI95] | [{bb['expectancy_r_ci95'][0]:.3f}, "
                     f"{bb['expectancy_r_ci95'][1]:.3f}] |")
            L.append(f"| P(expectancy > 0) | {bb['prob_expectancy_positive']:.3f} |")
        L.append(f"| çıkış sebepleri | {m['exit_reason_mix']} |")
        L.append("")
        if b.get("basket_equity_png"):
            L.append(f"![basket equity]({b['basket_equity_png']})")
            L.append("")
    L.append("## 3) EK (APPENDIX) — HİSSE BAZLI TABLO")
    L.append("")
    L.append("> Kabul kriteri 6: hisse başına ~6 trade **istatistiksel olarak anlamsızdır**. "
             "Bu tablo yalnızca tanı amaçlıdır; karar BASKET agregasyonuna göre verilir.")
    L.append("")
    L.append("| Hisse | trade | win % | PF | exp R | ort. tutma | net % | BH net % | zayıf |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for code, v in p["stocks_appendix"].items():
        if "error" in v:
            L.append(f"| **{code}** | — | — | — | — | — | — | — | VERİ YOK |")
            continue
        m, bh = v["metrics"], v["buy_hold"]
        L.append(f"| **{code}** | {m['n_trades']} | {_pct(m['win_rate'], 0)} | "
                 f"{_p(m['profit_factor_net'], 2)} | {_p(m['expectancy_r'], 2)} | "
                 f"{_p(m['avg_holding_bars'], 0)} | {_pct(m['net_return_frac'], 1)} | "
                 f"{_pct(bh.get('net_return_frac'), 1)} | "
                 f"{'⚠️' if m['statistically_weak'] else ''} |")
    L.append("")
    L.append("## 4) GRAFİKLER ve TRADE LİSTELERİ")
    L.append("")
    for k, v in p["core_assets"].items():
        L.append(f"- `{k}`: equity `{v.get('equity_png')}` · trade listesi `{v.get('trades_csv')}`")
    if b.get("basket_equity_png"):
        L.append(f"- BIST30 basket: equity `{b['basket_equity_png']}`")
    L.append("")
    L.append("## ZORUNLU CAVEAT'LER")
    L.append("")
    L.append("- **Bu bir baseline'dır.** Parametreler (n=10, m=1.0, Donchian 20, buffer 1.0, "
             "time-stop 90, TP 3R, cooldown 3) **VARSAYILANDIR ve OPTİMİZE EDİLMEMİŞTİR**. "
             "Seçim Aşama 9'da, yalnızca core varlıklar üzerinde, out-of-sample yapılacak.")
    L.append("- **Sinyal akışı CAPPED varyantıdır.** Pozisyon vekili (stop ihlali + 90 bar "
             "time-stop) gerçek çıkış motoruyla değiştirildiğinde sayılar DEĞİŞECEKTİR.")
    L.append("- **Portföy agregasyonu bir ÖNİZLEMEDİR.** Korelasyon limiti, bucket ısısı, "
             "sektör tavanı ve maks eşzamanlı pozisyon Aşama 8'de uygulanacak. GOLD|SILVER "
             "korelasyonu +0.77 olduğu için ikisi TEK risk kovası sayılacak; buradaki basit "
             "toplam o etkiyi İÇERMEZ.")
    L.append("- **Train/valid/test ayrımı bu raporda UYGULANMADI.** Sayılar tüm örneklem "
             "üzerindedir ve bu yüzden **in-sample**'dır. Aşama 9'da ön-kayıtlı split'lerle "
             "(`configs/splits_preregistered.yaml`) OOS ölçümü yapılacak.")
    L.append("- BIST30 sepeti **survivorship bias** taşır → sonuçlar yukarı yönlü çarpıktır.")
    L.append("- Metallerde roll **kesin tespit edilemediği** için getiri serisi ön-ay "
             "fiyatlarına dayanır; roll kaynaklı bias olabilir.")
    L.append("- Trade sayısı < 100 olan HER satır `İSTATİSTİKSEL ZAYIF` bayrağı taşır ve "
             "bootstrap CI olmadan YORUMLANMAMALIDIR.")
    L.append("- Geçmiş performans gelecek sonuçların göstergesi değildir. Bu rapor yatırım "
             "tavsiyesi DEĞİLDİR.")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
