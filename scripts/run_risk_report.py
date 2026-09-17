"""AŞAMA 8 — Risk katmanı raporu: tavanlı vs tavansız portföy simülasyonu (IN-SAMPLE).

Akış: CAPPED sinyaller (A0 anchor) · çıkış profili **P0×A0 KİLİTLİ** (seçim Aşama 9)
· t+1 icra · çift taraf maliyet · tavanlar YALNIZ GİRİŞTE (çıkışlara dokunmaz).

İki koşu:
  1) TAVANSIZ (`RiskLimits.no_limits`) — Aşama 7 P0×A0 regresyon kilidiyle:
     varlık başına trade sayıları ve expR (R-bazlı, equity'den bağımsız) birebir
     olmalıdır. (Net/PF ORTAK equity semantiğiyle hesaplanır; Aşama 6'nın
     varlık-başına-ayrı-equity koşusundan milimetrik farklılaşabilir — beklenen
     portföy semantiği, raporda açıkça yazılır.)
  2) TAVANLI (`RiskLimits.from_profile(balanced)`) — kullanıcı direktifi 2026-09-17:
     toplam 6 · BTC 2 · GOLD 1 · SILVER 1 · sepet 3 · metals birleşik ısı ≤ 1×rpt ·
     basket ısı ≤ 3×rpt · hisse ≤ 1×rpt · banka ≤ 2 eşzamanlı · günlük %2 / haftalık
     %5 realized kayıp limiti (fail-closed) · 4 ardışık kayıp → 20 bar fren.

Çıktı: reports/stage8_risk.md + .json   (H10: tam log + exit code ile çalıştırın)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))
sys.path.insert(0, _HERE)

import run_exit_grid as G  # noqa: E402  (_signals_for + run_backtest yardımcıları)
from quant4h.backtest.engine import Trade, bootstrap_ci  # noqa: E402
from quant4h.config import DEFAULT_EXIT, RISK_PROFILES, UTC  # noqa: E402
from quant4h.risk.limits import RiskLimits  # noqa: E402
from quant4h.risk.simulator import StreamSpec, simulate_portfolio  # noqa: E402

RB = G.RB
ROOT = G.ROOT
CORE = ("BTC", "GOLD", "SILVER")
BASKET = "BIST30_BASKET"


def build_streams(tf: str, codes: List[str], prof) -> List[StreamSpec]:
    streams: List[StreamSpec] = []
    index_4h = RB._load(os.path.join(ROOT, "data", "interim", f"bist30_{tf}.parquet"))
    for key in CORE:
        frame = G._signals_for(key, tf, False, index_4h, "A0")
        if frame is None:
            raise FileNotFoundError(f"{key} levels frame yok (önce Aşama 2/3 raporları)")
        cost = RB._cost_for(key, False)
        streams.append(StreamSpec(key, "long", frame, cost, max_leverage=prof.max_leverage))
        streams.append(StreamSpec(key, "short", frame, cost, max_leverage=prof.max_leverage))
    for code in codes:
        frame = G._signals_for(code, tf, True, index_4h, "A0")
        if frame is None:
            continue
        cost = RB._cost_for(code, True)
        streams.append(StreamSpec(code, "long", frame, cost, max_leverage=1.0, is_stock=True))
    return streams


def _rebuild_chain(trades: List[Trade], starting_equity: float) -> List[Trade]:
    """equity_before/after zincirini giriş ZAMANINA göre sıralı yeniden kur
    (Aşama 6 `_merge_results` semantiği; ortak equity'li portföy için)."""
    eq = starting_equity
    out = sorted(trades, key=lambda t: (t.entry_timestamp_utc, t.exit_timestamp_utc))
    for t in out:
        t.equity_before = eq
        t.equity_after = eq + t.net_pnl
        eq = t.equity_after
    return out


def _metrics_for(ts: List[Trade]) -> Dict[str, Any]:
    if not ts:
        return {"n_trades": 0}
    rs = np.array([t.r_multiple for t in ts], dtype="float64")
    nets = np.array([t.net_pnl for t in ts], dtype="float64")
    eqb = np.maximum(np.array([t.equity_before for t in ts], dtype="float64"), 1e-9)
    wins, losses = nets > 0, nets < 0
    npn, nln = float(nets[wins].sum()), float(-nets[losses].sum())
    pf = round(npn / nln, 4) if nln > 0 else (None if npn == 0 else float("inf"))
    boot = bootstrap_ci(rs[np.isfinite(rs)], nets / eqb, DEFAULT_EXIT) if len(ts) >= 5 else {}
    return {"n_trades": len(ts),
            "win_rate": round(float(wins.mean()), 4),
            "profit_factor_net": pf,
            "expectancy_r": round(float(np.nanmean(rs)), 4),
            "expR_ci95": boot.get("expectancy_r_ci95"),
            "prob_expR_positive": boot.get("prob_expectancy_positive"),
            "net_pnl_total": round(float(nets.sum()), 2),
            "statistically_weak": len(ts) < DEFAULT_EXIT.min_trades_for_significance}


def summarize(sim, starting_equity: float) -> Dict[str, Any]:
    trades = _rebuild_chain(list(sim.trades), starting_equity)
    eq = sim.equity
    curve_final = float(eq["equity"].iloc[-1]) if len(eq) else starting_equity
    peak = eq["equity"].cummax()
    dd_curve = float(((eq["equity"] - peak) / peak).min()) if len(eq) else 0.0
    exposure = float((eq["n_open"] > 0).mean()) if len(eq) else 0.0
    groups: Dict[str, List[Trade]] = {}
    for t in trades:
        g = t.group_key or "UNMATCHED"
        groups.setdefault(g, []).append(t)
        if g not in CORE:                      # hisseler ayrıca BASKET agregatına
            groups.setdefault(BASKET, []).append(t)
    per = {g: _metrics_for(ts) for g, ts in sorted(groups.items())}
    return {"portfolio": {"n_trades": len(trades),
                          "net_return_frac": round(curve_final / starting_equity - 1.0, 6),
                          "max_drawdown_curve_frac": round(dd_curve, 6),
                          "exposure_frac": round(exposure, 4),
                          "final_equity": round(curve_final, 2)},
            "peaks": dict(sim.peaks),
            "rejections": dict(sim.rejections),
            "per_asset": per,
            "warnings": list(sim.warnings)}


def regression_vs_stage7(unc: Dict[str, Any]) -> Dict[str, Any]:
    p = os.path.join(ROOT, "reports", "stage7_exit_grid.json")
    out: Dict[str, Any] = {"reference": os.path.relpath(p, ROOT), "items": {}}
    if not os.path.exists(p):
        out["error"] = "stage7_exit_grid.json yok"
        return out
    with open(p, "r", encoding="utf-8") as fh:
        g7 = json.load(fh)
    ok_all = True
    for g7key, key in (("BTC", "BTC"), ("GOLD", "GOLD"), ("SILVER", "SILVER"),
                       ("BIST30_BASKET", BASKET)):
        ref = (g7["cells"].get(g7key, {}).get("P0xA0", {}).get("metrics")) or {}
        got = unc["per_asset"].get(key, {})
        same = (got.get("n_trades") == ref.get("n_trades")
                and got.get("expectancy_r") is not None and ref.get("expectancy_r") is not None
                and abs(got["expectancy_r"] - ref["expectancy_r"]) < 5e-4)
        out["items"][key] = {"ok": bool(same),
                             "sim": [got.get("n_trades"), got.get("expectancy_r")],
                             "stage7": [ref.get("n_trades"), ref.get("expectancy_r")]}
        ok_all &= bool(same)
    out["all_match"] = bool(ok_all)
    return out


def _md(payload: Dict[str, Any]) -> str:
    cap, unc = payload["capped"], payload["unlimited"]
    L: List[str] = []
    L.append("# AŞAMA 8 — Risk katmanı: tavanlı vs tavansız portföy simülasyonu")
    L.append("")
    L.append(f"*Üretim: {payload['generated_at_utc']}* · sinyal **CAPPED** · çıkış **P0×A0 KİLİTLİ** "
             f"(seçim Aşama 9) · risk **{payload['risk_profile']['name']}** "
             f"(%{payload['risk_profile']['risk_per_trade']*100:.2f}/işlem) · başlangıç "
             f"{payload['starting_equity']:,.0f} · t+1 icra · maliyet çift taraf · "
             f"**tavanlar YALNIZ girişte** (çıkışlara dokunmaz)")
    L.append("")
    L.append("> ⚠️ **IN-SAMPLE** — bu rapor karar üretmez; nihai hüküm Aşama 9 OOS + "
             "`go_no_go` eşikleridir. Sepet survivorship bias taşır. ORTAK equity "
             "semantiği: boyutlama her girişte GÜNCEL realized equity ile yapılır "
             "(Aşama 6'nın varlık-başına-ayrı-equity koşusundan milimetrik farklar "
             "beklenir; expR ve trade sayıları equity'den bağımsızdır ve regresyonla kilitlidir).")
    L.append("")
    reg = payload["regression_vs_stage7"]
    if reg.get("all_match"):
        L.append("✅ **Regresyon:** TAVANSIZ koşu Aşama 7 P0×A0 hücreleriyle birebir "
                 "(trade sayıları + expR; BTC/GOLD/SILVER/BASKET) → simülatör motorla eşdeğer.")
    else:
        L.append("❌ **Regresyon UYUŞMADI** — json `regression_vs_stage7.items`; bu rapor "
                 "uyumsuzluk çözülmeden KULLANILAMAZ.")
    L.append("")
    L.append("## 1) Bağlayıcı tavanlar (kullanıcı direktifi 2026-09-17 · balanced)")
    L.append("")
    L.append("| tavan | değer |")
    L.append("|---|---|")
    L.append("| maks eşzamanlı (TOPLAM) | 6 |")
    L.append("| BTC / GOLD / SILVER eşzamanlı | 2 / 1 / 1 |")
    L.append("| BIST30 sepet eşzamanlı | 3 |")
    L.append("| kıymetli maden birleşik ISI | ≤ 1 × risk_per_trade (%0.50) — TEK kova (onaylı karar) |")
    L.append("| BIST30 sepet birleşik ISI | ≤ 3 × risk_per_trade (%1.50) |")
    L.append("| hisse başı ISI | ≤ 1 × risk_per_trade (%0.50) |")
    L.append("| banka sektörü eşzamanlı | ≤ 2 (donmuş üniversalden: sector == 'banka') |")
    L.append(f"| günlük / haftalık kayıp limiti | %{payload['limits']['max_daily_loss']*100:.0f} / "
             f"%{payload['limits']['max_weekly_loss']*100:.0f} (RiskProfile — realized P&L bazlı, fail-closed) |")
    L.append("| ardışık kayıp freni | 4 ardışık kayıp → 20 bar yeni giriş yok (varlık bazında, L+S ortak) |")
    L.append("")
    L.append("## 2) TAVANLI vs TAVANSIZ (in-sample, portföy düzeyi)")
    L.append("")
    L.append("| ölçü | TAVANSIZ | TAVANLI | fark |")
    L.append("|---|---:|---:|---:|")
    pu, pc = unc["portfolio"], cap["portfolio"]

    def row(label: str, a, b, fmt="{:.4f}"):
        d = (b - a) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
        L.append(f"| {label} | {fmt.format(a)} | {fmt.format(b)} | "
                 f"{('%+.4f' % d) if d is not None else '—'} |")

    row("trade sayısı", pu["n_trades"], pc["n_trades"], "{:d}")
    row("net getiri (mtm eğri)", pu["net_return_frac"], pc["net_return_frac"])
    row("max DD (mtm eğri)", pu["max_drawdown_curve_frac"], pc["max_drawdown_curve_frac"])
    row("exposure (bar oranı)", pu["exposure_frac"], pc["exposure_frac"])
    L.append("")
    L.append("### Varlık bazında (TAVANLI koşu; expR R-bazlı)")
    L.append("")
    L.append("| grup | trade | win% | PF(net) | expR | expR CI95 | P(expR>0) | net P&L | zayıf |")
    L.append("|---|---:|---:|---:|---:|---|---:|---:|---|")
    for g in ("BTC", "GOLD", "SILVER", BASKET):
        m = cap["per_asset"].get(g)
        if not m or not m.get("n_trades"):
            continue
        ci = m.get("expR_ci95") or [None, None]
        pf = m.get("profit_factor_net")
        L.append("| {g} | {n} | {wr:.1f} | {pf} | {er:+.3f} | [{lo}, {hi}] | {pp} | {np:+,.0f} | {wk} |".format(
            g=g, n=m["n_trades"], wr=(m["win_rate"] or 0) * 100,
            pf=f"{pf:.3f}" if isinstance(pf, float) else "—",
            er=m["expectancy_r"] or 0.0,
            lo=f"{ci[0]:+.3f}" if ci[0] is not None else "—",
            hi=f"{ci[1]:+.3f}" if ci[1] is not None else "—",
            pp=f"{m['prob_expR_positive']:.2f}" if m.get("prob_expR_positive") is not None else "—",
            np=m["net_pnl_total"] or 0.0,
            wk="⚠️" if m.get("statistically_weak") else ""))
    L.append("")
    L.append("## 3) Tavan tipi başına REDDEDİLEN giriş (tavanlı koşu)")
    L.append("")
    L.append("| tavan tipi | red |")
    L.append("|---|---:|")
    for k, v in sorted(cap["rejections"].items(), key=lambda kv: -kv[1]):
        L.append(f"| `{k}` | {v} |")
    L.append("")
    pk, upk = cap["peaks"], unc["peaks"]
    L.append(f"**Tepe değerler — TAVANLI:** maks eşzamanlı {pk['max_concurrent_open']} (tavan 6) · "
             f"metals ısısı %{pk['peak_metals_heat']*100:.2f} (tavan %0.50) · "
             f"basket ısısı %{pk['peak_basket_heat']*100:.2f} (tavan %1.50) · "
             f"toplam ısı %{pk['peak_total_heat']*100:.2f} · banka eşzamanlı {pk['max_bank_concurrent']} (tavan 2)")
    L.append("")
    L.append(f"**Tepe değerler — TAVANSIZ:** maks eşzamanlı {upk['max_concurrent_open']} · "
             f"metals %{upk['peak_metals_heat']*100:.2f} · basket %{upk['peak_basket_heat']*100:.2f} · "
             f"toplam %{upk['peak_total_heat']*100:.2f} · banka {upk['max_bank_concurrent']}")
    L.append("")
    L.append("## 4) EK (APPENDIX) — BIST30 hisse bazlı (tavanlı; tanı amaçlı, kabul kriteri 6)")
    L.append("")
    L.append("| hisse | trade | win% | PF | expR | zayıf |")
    L.append("|---|---:|---:|---:|---:|---|")
    stocks = {g: m for g, m in cap["per_asset"].items() if g not in CORE and g != BASKET}
    for g in sorted(stocks):
        m = stocks[g]
        pf = m.get("profit_factor_net")
        wr = m.get("win_rate")
        er = m.get("expectancy_r")
        L.append("| {g} | {n} | {wr} | {pf} | {er} | {wk} |".format(
            g=g, n=m["n_trades"],
            wr=f"{wr*100:.0f}" if wr is not None else "—",
            pf=f"{pf:.2f}" if isinstance(pf, float) else "—",
            er=f"{er:+.2f}" if er is not None else "—",
            wk="⚠️" if m.get("statistically_weak") else ""))
    L.append("")
    L.append("## ZORUNLU CAVEAT'LER")
    L.append("")
    L.append("- **SEÇİM YOK**: P0×A0 Aşama 9'a kadar kilitli; bu rapor risk KATMANININ "
             "etkisini ölçer, profil/anchor seçmez.")
    L.append("- Tüm sayılar IN-SAMPLE ve maliyet dahil; go/no-go Aşama 9 OOS + "
             "`user_decisions.yaml → go_no_go` eşikleriyle.")
    L.append("- Günlük/haftalık limitler REALIZED P&L bazlıdır (unrealized dahil DEĞİL) — "
             "belgelenmiş seçim; mtm bazlı limite geçiş ayrı onay gerektirir.")
    L.append("- `max_correlation` ayrıca ZORLANMADI: metals tek-kova ısısı (≤ %0.5 birleşik) "
             "GOLD|SILVER'i zaten sınırlar; günlük bazlı korelasyon limiti Aşama 9'da ele alınacak.")
    L.append("- Stage 0 `RiskProfile.max_open_positions=3` bu şartnameyle SUPERSEDE edildi "
             "(toplam 6 · kullanıcı direktifi 2026-09-17); PROGRESS'e işlendi.")
    L.append("- Bu rapor yatırım tavsiyesi DEĞİLDİR; geçmiş performans geleceğin göstergesi değildir.")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--risk-profile", default="balanced", choices=sorted(RISK_PROFILES))
    ap.add_argument("--starting-equity", type=float, default=100_000.0)
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    args = ap.parse_args()
    prof = RISK_PROFILES[args.risk_profile]
    codes = RB._included(os.path.join(ROOT, "reports", "bist30_universe_qc.json"))
    streams = build_streams(args.timeframe, codes, prof)
    print(f"Aşama 8: {len(streams)} akış (3 core × 2 yön + {len(codes)} hisse) · "
          f"profil={prof.name} · P0×A0 kilitli · tavanlar yalnız girişte")

    sim_unc = simulate_portfolio(streams, RiskLimits.no_limits(),
                                 risk_per_trade=prof.risk_per_trade,
                                 starting_equity=args.starting_equity)
    print(f"  [tavansız] trades={len(sim_unc.trades)} tepe_eşzamanlı={sim_unc.peaks['max_concurrent_open']}")
    sim_cap = simulate_portfolio(streams, RiskLimits.from_profile(prof),
                                 risk_per_trade=prof.risk_per_trade,
                                 starting_equity=args.starting_equity)
    print(f"  [tavanlı ] trades={len(sim_cap.trades)} red_toplam={sum(sim_cap.rejections.values())} "
          f"tepe_eşzamanlı={sim_cap.peaks['max_concurrent_open']}")

    unc = summarize(sim_unc, args.starting_equity)
    cap = summarize(sim_cap, args.starting_equity)
    reg = regression_vs_stage7(unc)
    payload = {
        "generated_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
        "timeframe": args.timeframe,
        "risk_profile": {"name": prof.name, "risk_per_trade": prof.risk_per_trade,
                         "max_leverage": prof.max_leverage},
        "starting_equity": args.starting_equity,
        "exit_lock": "P0xA0 (seçim Aşama 9'da, OOS)",
        "signal_variant": "capped",
        "limits": {"max_concurrent_total": 6, "per_asset": {"BTC": 2, "GOLD": 1, "SILVER": 1},
                   "basket_concurrent": 3, "metals_heat_rpt_mult": 1.0,
                   "basket_heat_rpt_mult": 3.0, "per_stock_heat_rpt_mult": 1.0,
                   "bank_concurrent": 2, "max_daily_loss": prof.max_daily_loss,
                   "max_weekly_loss": prof.max_weekly_loss, "loss_streak": [4, 20]},
        "regression_vs_stage7": reg,
        "unlimited": unc, "capped": cap,
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "stage8_risk.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    with open(os.path.join(args.out, "stage8_risk.md"), "w", encoding="utf-8") as fh:
        fh.write(_md(payload))
    print(f"\nRegresyon (tavansız vs Aşama 7 P0xA0): {'OK — birebir' if reg.get('all_match') else 'UYUŞMAZ ❌'}")
    for k, v in reg.get("items", {}).items():
        print(f"  {k}: sim={v['sim']} stage7={v['stage7']} {'✓' if v['ok'] else '✗'}")
    print("raporlar: reports/stage8_risk.md · .json")
    return 0 if reg.get("all_match") else 1


if __name__ == "__main__":
    raise SystemExit(main())
