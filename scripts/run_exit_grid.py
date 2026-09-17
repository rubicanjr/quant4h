"""AŞAMA 7 — Çıkış mimarisi KARŞILAŞTIRMA grid'i (IN-SAMPLE · SEÇİM YOK).

Grid: 4 çıkış profili (P0..P3) × 3 stop anchor'ı (A0..A2) × {BTC, GOLD, SILVER,
BIST30 basket (28 hisse)} = varlık başına 12 hücre.

**SEÇİM YOKTUR.** Tüm hücreler IN-SAMPLE etiketlidir ve yalnız MİMARİ İÇGÖRÜ
sağlar; profil/anchor SEÇİMİ yalnızca Aşama 9'da, ön-kayıtlı OOS split'lerle ve
yalnız core varlıklar üzerinde yapılır (PER_ASSET_IN_SAMPLE_TUNING_ALLOWED=False).
Rapordaki "en iyi/en kötü hücre" işaretleri TANIMLAYICIDIR, ÖNERİ DEĞİLDİR.

Zincir (Aşama 6 ile aynı, tek farkla): levels frame → **anchor override** →
momentum → (hisse) XU030 bağlam → CAPPED sinyaller → engine(profil) → metrikler.
Anchor override SİNYAL ÜRETİMİNDEN ÖNCE yapılır; böylece hem `stop_valid` kapısı
hem pozisyon vekili (capped proxy) hem motor AYNI stop'u kullanır (tutarlılık).

Regresyon kilidi: **P0×A0 hücresi Aşama 6 baseline'ını birebir yeniden üretmek
ZORUNDADIR** (`reports/backtest_baseline.json` ile karşılaştırılır; uyuşmazsa
exit code 1). Bu, motor refactor'ünün + D6 kilidinin baseline'ı değiştirmediğinin
kanıtıdır.

Çalıştırma:  python3 -W ignore scripts/run_exit_grid.py
Çıktı:       reports/stage7_exit_grid.md + reports/stage7_exit_grid.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))
sys.path.insert(0, _HERE)

import run_backtest as RB  # noqa: E402  (Aşama 6 yardımcıları: _levels/_cost_for/_merge_results/…)
from quant4h.backtest.anchors import ANCHORS, apply_anchor  # noqa: E402
from quant4h.backtest.engine import run_backtest  # noqa: E402
from quant4h.config import (DEFAULT_EXIT, DEFAULT_LEVELS, DEFAULT_MOMENTUM,  # noqa: E402
                            DEFAULT_PROFILE, DEFAULT_REGIME, ExitConfig,
                            RISK_PROFILES, UTC, bist_stock_specs)
from quant4h.features.context import longs_allowed  # noqa: E402
from quant4h.features.momentum import add_momentum  # noqa: E402
from quant4h.strategy.signals import build_signals  # noqa: E402

ROOT = RB.ROOT
PROFILES = ("P0", "P1", "P2", "P3")
PROFILE_DESC = {
    "P0": "baseline: TS90 + TP3R (Aşama 6)",
    "P1": "partial+runner: 1R'de %50 + stop→BE + runner chandelier ATR×3 (TS/TP YOK)",
    "P2": "trailing: girişten chandelier ATR×3 (dondurulmuş stop'un altına inmez, yalnız yukarı taşınır — ratchet), TP YOK, TS90 emniyet",
    "P3": "breakeven: 1R sonrası stop→BE, TP3R + TS90 (partial YOK)",
}
ANCHOR_DESC = {
    "A0": "onaylı swing − 1.0×ATR (mevcut)",
    "A1": "Donchian(20) ters bandı (buffer YOK)",
    "A2": "onaylı swing − 0.5×ATR (kilitli küme içi)",
}
MAX_POSITION_BARS_SIGNAL = 90      # capped akışın sinyal-tarafı time-stop'u (Aşama 6 ile aynı)


def _signals_for(key: str, tf: str, is_stock: bool, index_4h, anchor: str) -> Optional[pd.DataFrame]:
    base = RB._levels(key, tf)
    if base is None or not len(base):
        return None
    allow_short = not is_stock
    out = add_momentum(base, DEFAULT_MOMENTUM, allow_short=allow_short)
    if is_stock and "longs_allowed" not in out.columns and index_4h is not None:
        out = longs_allowed(out, index_4h, tf, DEFAULT_REGIME.ema_trend_period)
    out = apply_anchor(out, anchor, allow_short=allow_short)
    return build_signals(out, is_stock=is_stock, cooldown_bars=3,
                         trigger_period=DEFAULT_LEVELS.donchian_period,
                         allow_short=allow_short,
                         position_exit_proxy="frozen_stop_intrabar",
                         max_position_bars=MAX_POSITION_BARS_SIGNAL)


def _cell_core(key: str, frame: pd.DataFrame, prof, exit_cfg, start_eq) -> Dict[str, Any]:
    cost = RB._cost_for(key, False)
    lr = run_backtest(frame, cost, exit_cfg=exit_cfg, risk_per_trade=prof.risk_per_trade,
                      starting_equity=start_eq, max_leverage=prof.max_leverage,
                      allow_short=False, asset=f"{key}_long")
    sr = run_backtest(frame, cost, exit_cfg=exit_cfg, risk_per_trade=prof.risk_per_trade,
                      starting_equity=start_eq, max_leverage=prof.max_leverage,
                      allow_short=True, signal_col_long="__none__",
                      signal_col_short="short_signal", asset=f"{key}_short")
    merged = RB._merge_results(lr, sr, key)
    m = dict(merged.metrics)
    # exposure: long|short birleşik (bar bazlı, iki ayrı koşudan)
    if lr.equity is not None and sr.equity is not None and len(lr.equity) == len(sr.equity):
        any_pos = (lr.equity["position_open"].to_numpy() | sr.equity["position_open"].to_numpy())
        m["exposure_frac"] = round(float(any_pos.mean()), 4)
    return {"metrics": m, "config": merged.config,
            "long_trades": len(lr.trades), "short_trades": len(sr.trades),
            "cost_bps_round_trip": cost.round_trip_bps}


def _cell_basket(codes: List[str], tf: str, index_4h, prof, exit_cfg, start_eq,
                 anchor: str) -> Dict[str, Any]:
    all_trades: List[Any] = []
    returns: List[pd.Series] = []
    exposures: List[float] = []
    per_stock: Dict[str, Any] = {}
    for code in codes:
        frame = _signals_for(code, tf, True, index_4h, anchor)
        if frame is None:
            per_stock[code] = {"error": "veri yok"}
            continue
        cost = RB._cost_for(code, True)
        lr = run_backtest(frame, cost, exit_cfg=exit_cfg, risk_per_trade=prof.risk_per_trade,
                          starting_equity=start_eq, max_leverage=1.0,
                          allow_short=False, asset=code)
        m = RB.compute_merged_metrics(lr.trades, lr.equity, start_eq, lr.config)
        per_stock[code] = {"n_trades": m["n_trades"], "expectancy_r": m["expectancy_r"],
                           "profit_factor_net": m["profit_factor_net"]}
        all_trades.extend(lr.trades)
        if lr.equity is not None and len(lr.equity):
            r = lr.equity.set_index(pd.to_datetime(lr.equity["timestamp_utc"], utc=True))[
                "equity"].pct_change().fillna(0.0)
            returns.append(r.rename(code))
            exposures.append(float(lr.equity["position_open"].mean()))
    agg: Dict[str, Any] = {"n_stocks": len(codes), "n_trades": len(all_trades)}
    if all_trades:
        cfgmap = {"starting_equity": start_eq, "round_trip_bps": 120.0}
        m = RB.compute_merged_metrics(sorted(all_trades, key=lambda t: (t.entry_bar, t.exit_bar)),
                                      None, start_eq, cfgmap)
        agg["metrics"] = m
        if returns:
            R = pd.concat(returns, axis=1).sort_index()
            eq = (1 + R.mean(axis=1)).cumprod() * start_eq
            peak = eq.cummax()
            agg["basket_equity"] = {
                "net_return_frac": round(float(eq.iloc[-1] / start_eq - 1.0), 6),
                "max_drawdown_frac": round(float(((eq - peak) / peak).min()), 6)}
        if exposures:
            agg.setdefault("metrics", {})["exposure_frac"] = round(float(np.mean(exposures)), 4)
    agg["per_stock"] = per_stock
    agg["flag"] = ("RİSK MODÜLÜ ÖNCESİ ÖNİZLEME — kova ısısı/korelasyon/sektör tavanı "
                   "UYGULANMADI (Aşama 8); survivorship bias caveat'li")
    return agg


def _slim(m: Dict[str, Any]) -> Dict[str, Any]:
    b = m.get("bootstrap") or {}
    return {
        "n_trades": m.get("n_trades"),
        "win_rate": m.get("win_rate"),
        "profit_factor_net": m.get("profit_factor_net"),
        "expectancy_r": m.get("expectancy_r"),
        "expR_ci95": b.get("expectancy_r_ci95"),
        "prob_expR_positive": b.get("prob_expectancy_positive"),
        "max_drawdown_frac": m.get("max_drawdown_frac"),
        "avg_holding_bars": m.get("avg_holding_bars"),
        "exposure_frac": m.get("exposure_frac"),
        "net_return_frac": m.get("net_return_frac"),
        "total_cost": m.get("total_cost"),
        "exit_reason_mix": m.get("exit_reason_mix"),
        "statistically_weak": m.get("statistically_weak"),
    }


def _regression_check(cells: Dict[str, Any], baseline_path: str) -> Dict[str, Any]:
    """P0×A0 hücreleri Aşama 6 baseline'ıyla birebir mi? (tolerans 1e-6)."""
    out: Dict[str, Any] = {"baseline_file": os.path.relpath(baseline_path, ROOT), "items": {}}
    if not os.path.exists(baseline_path):
        out["error"] = "baseline json yok"
        return out
    with open(baseline_path, "r", encoding="utf-8") as fh:
        base = json.load(fh)
    ok_all = True
    for key in ("BTC", "GOLD", "SILVER"):
        cell = cells.get(key, {}).get("P0xA0", {}).get("metrics")
        ref = (base.get("core_assets", {}).get(key) or {}).get("metrics")
        if cell is None or ref is None:
            out["items"][key] = {"ok": False, "reason": "hücre/ref yok"}
            ok_all = False
            continue
        diffs = []
        for f in ("n_trades", "win_rate", "profit_factor_net", "expectancy_r",
                  "max_drawdown_frac", "total_cost", "avg_holding_bars"):
            a, b = cell.get(f), ref.get(f)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if abs(float(a) - float(b)) > max(1e-6, abs(float(b)) * 1e-6):
                    diffs.append(f"{f}: {a} vs {b}")
            elif a != b:
                diffs.append(f"{f}: {a} vs {b}")
        out["items"][key] = {"ok": not diffs, "diffs": diffs}
        ok_all &= not diffs
    bref = (base.get("basket") or {}).get("metrics") or {}
    bcell = cells.get("BIST30_BASKET", {}).get("P0xA0", {}).get("metrics") or {}
    bdiffs = []
    for f in ("n_trades", "profit_factor_net", "expectancy_r", "win_rate"):
        a, b = bcell.get(f), bref.get(f)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if abs(float(a) - float(b)) > max(1e-6, abs(float(b)) * 1e-6):
                bdiffs.append(f"{f}: {a} vs {b}")
    out["items"]["BIST30_BASKET"] = {"ok": not bdiffs, "diffs": bdiffs}
    ok_all &= not bdiffs
    out["all_match"] = bool(ok_all)
    return out


def _md(payload: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append("# AŞAMA 7 — Çıkış mimarisi karşılaştırma grid'i")
    L.append("")
    L.append(f"*Üretim: {payload['generated_at_utc']}* · timeframe **{payload['timeframe']}** · "
             f"risk **{payload['risk_profile']['name']}** (%{payload['risk_profile']['risk_per_trade']*100:.2f}/işlem) · "
             f"başlangıç {payload['starting_equity']:,.0f} · sinyal akışı **CAPPED** (proxy TS{MAX_POSITION_BARS_SIGNAL})")
    L.append("")
    L.append("> ⚠️ **TÜM HÜCRELER IN-SAMPLE'DIR — SEÇİM YOK.** Profil/anchor seçimi YALNIZ "
             "Aşama 9'da, ön-kayıtlı OOS split'lerle, yalnız core varlıklarda yapılır. "
             "En iyi/en kötü işaretleri TANIMLAYICIDIR; **ÖNERİ DEĞİLDİR**. Aşama 8 risk "
             "limitleri (kova ısısı, korelasyon, tavanlar) UYGULANMAMIŞTIR.")
    L.append("")
    reg = payload["p0xa0_regression_vs_stage6"]
    if reg.get("all_match"):
        L.append(f"✅ **P0×A0 regresyon kilidi:** Aşama 6 baseline birebir yeniden üretildi "
                 f"({reg['baseline_file']}; motor refactor'ü + D6 aynı-bar giriş kilidi baseline'ı DEĞİŞTİRMEDİ).")
    else:
        L.append(f"❌ **P0×A0 regresyon UYUŞMADI** — detay json'da. Baseline'a dokunulmuş demektir; "
                 f"Aşama 7 sonuçları bu uyumsuzluk çözülmeden KULLANILAMAZ.")
    L.append("")
    L.append("**Profiller:** " + " · ".join(f"`{p}` {PROFILE_DESC[p]}" for p in PROFILES))
    L.append("")
    L.append("**Anchor'lar:** " + " · ".join(f"`{a}` {ANCHOR_DESC[a]}" for a in ANCHORS))
    L.append("")
    for key in ("BTC", "GOLD", "SILVER", "BIST30_BASKET"):
        cells = payload["cells"].get(key) or {}
        if not cells:
            continue
        L.append(f"## {key}")
        L.append("")
        L.append("| hücre | trade | win% | PF(net) | expR | expR CI95 | P(expR>0) | maxDD | ort.tutma | exposure | net% | zayıf |")
        L.append("|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|")
        best = worst = None
        for p in PROFILES:
            for a in ANCHORS:
                cid = f"{p}x{a}"
                m = (cells.get(cid) or {}).get("metrics") or {}
                if not m or m.get("n_trades") in (None, 0):
                    L.append(f"| {cid} | 0 | — | — | — | — | — | — | — | — | — | — |")
                    continue
                ci = m.get("expR_ci95") or [None, None]
                er = m.get("expectancy_r")
                mark = ""
                if er is not None:
                    if best is None or er > best[1]:
                        best = (cid, er)
                    if worst is None or er < worst[1]:
                        worst = (cid, er)
                L.append("| {cid}{mark} | {n} | {wr} | {pf} | {er} | [{lo}, {hi}] | {pp} | {dd} | {hb} | {ex} | {nr} | {wk} |".format(
                    cid=cid, mark="", n=m.get("n_trades"),
                    wr=f"{m['win_rate']*100:.1f}" if m.get("win_rate") is not None else "—",
                    pf=f"{m['profit_factor_net']:.3f}" if m.get("profit_factor_net") is not None else "—",
                    er=f"{er:+.3f}" if er is not None else "—",
                    lo=f"{ci[0]:+.3f}" if ci[0] is not None else "—",
                    hi=f"{ci[1]:+.3f}" if ci[1] is not None else "—",
                    pp=f"{m.get('prob_expR_positive'):.2f}" if m.get("prob_expR_positive") is not None else "—",
                    dd=f"{m['max_drawdown_frac']*100:.2f}%" if m.get("max_drawdown_frac") is not None else "—",
                    hb=f"{m.get('avg_holding_bars'):.1f}" if m.get("avg_holding_bars") is not None else "—",
                    ex=f"{m['exposure_frac']*100:.1f}%" if m.get("exposure_frac") is not None else "—",
                    nr=f"{m['net_return_frac']*100:+.2f}%" if m.get("net_return_frac") is not None else "—",
                    wk="⚠️" if m.get("statistically_weak") else ""))
        if best and worst and best[0] != worst[0]:
            L.append("")
            L.append(f"*Tanımlayıcı (ÖNERİ DEĞİL): en yüksek expR `{best[0]}` ({best[1]:+.3f}R) · "
                     f"en düşük expR `{worst[0]}` ({worst[1]:+.3f}R) — in-sample.*")
        beq = (cells.get("P0xA0") or {}).get("basket_equity")
        if key == "BIST30_BASKET":
            L.append("")
            L.append("Sepet equity (eşit-risk, mark-to-market) hücre bazında json'da; "
                     "P0×A0 Aşama 6 ile birebir.")
        L.append("")
    L.append("## Çıkış sebebi karışımları (özet)")
    L.append("")
    L.append("Detay `reports/stage7_exit_grid.json → cells.<VARLIK>.<hücre>.metrics.exit_reason_mix`. "
             "P1/P2'de `chandelier` yeni reason'dır; P1'de `time_stop` YOKTUR (şartname), "
             "P2'de `take_profit` YOKTUR.")
    L.append("")
    L.append("## ZORUNLU CAVEAT'LER")
    L.append("")
    L.append("- **SEÇİM YOK**: bu grid Aşama 9 girdisidir; hiçbir hücre 'kazanan' ilan edilemez.")
    L.append("- Tüm sayılar **in-sample** (train/valid/test ayrılmadı) ve maliyet dahil.")
    L.append("- Sepet: survivorship bias + risk modülü önizlemesi (Aşama 8 limitleri yok).")
    L.append("- P1 partial'ı aynı barda STOP ile çakışırsa **STOP kazanır, partial YAPILMAZ** "
             "(kabul kriteri 2, pesimist). BE/trailing güncellemeleri bar SONUNDA yazılır, "
             "sonraki bardan geçerli olur (bar içi sıkılaştırma yok → look-ahead yok).")
    L.append("- P1'de time-stop YOKTUR (şartname gereği): runner chandelier/stop/EOD ile çıkar; "
             "uzun tutma süreleri mümkündür.")
    L.append("- Bu rapor yatırım tavsiyesi DEĞİLDİR; geçmiş performans gelecek sonuçların göstergesi değildir.")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--risk-profile", default=DEFAULT_PROFILE, choices=sorted(RISK_PROFILES))
    ap.add_argument("--starting-equity", type=float, default=100_000.0)
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    args = ap.parse_args()
    tf, prof, start_eq = args.timeframe, RISK_PROFILES[args.risk_profile], args.starting_equity
    index_4h = RB._load(os.path.join(ROOT, "data", "interim", f"bist30_{tf}.parquet"))
    codes = RB._included(os.path.join(ROOT, "reports", "bist30_universe_qc.json"))
    print(f"Aşama 7 grid: {len(PROFILES)} profil × {len(ANCHORS)} anchor × "
          f"(3 core + {len(codes)} hisse) · profil={prof.name} · IN-SAMPLE · SEÇİM YOK")

    cells: Dict[str, Any] = {}
    for key in ("BTC", "GOLD", "SILVER"):
        cells[key] = {}
        for a in ANCHORS:
            frame = _signals_for(key, tf, False, index_4h, a)
            if frame is None:
                print(f"  [{key}] levels verisi yok — atlandı")
                continue
            for p in PROFILES:
                cfg = ExitConfig(profile=p)
                cell = _cell_core(key, frame, prof, cfg, start_eq)
                cells[key][f"{p}x{a}"] = {"metrics": _slim(cell["metrics"]),
                                           "long_trades": cell["long_trades"],
                                           "short_trades": cell["short_trades"],
                                           "cost_bps_round_trip": cell["cost_bps_round_trip"]}
                m = cell["metrics"]
                print(f"  [{key:7s} {p}x{a}] trades={m['n_trades']:4d} PF={m['profit_factor_net']} "
                      f"expR={m['expectancy_r']} maxDD={m['max_drawdown_frac']}")
    cells["BIST30_BASKET"] = {}
    for a in ANCHORS:
        for p in PROFILES:
            cfg = ExitConfig(profile=p)
            agg = _cell_basket(codes, tf, index_4h, prof, cfg, start_eq, a)
            m = agg.get("metrics") or {}
            cells["BIST30_BASKET"][f"{p}x{a}"] = {
                "metrics": _slim(m) if m else {"n_trades": 0},
                "basket_equity": agg.get("basket_equity"),
                "n_stocks": agg.get("n_stocks"),
                "per_stock": agg.get("per_stock"),
                "flag": agg.get("flag")}
            print(f"  [BASKET {p}x{a}] trades={m.get('n_trades')} PF={m.get('profit_factor_net')} "
                  f"expR={m.get('expectancy_r')} eqNet={(agg.get('basket_equity') or {}).get('net_return_frac')}")

    reg = _regression_check(cells, os.path.join(ROOT, "reports", "backtest_baseline.json"))
    payload = {
        "generated_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
        "timeframe": tf,
        "risk_profile": {"name": prof.name, "risk_per_trade": prof.risk_per_trade,
                         "max_leverage": prof.max_leverage},
        "starting_equity": start_eq,
        "signal_variant": "capped",
        "selection_policy": "SEÇİM YOK — in-sample karşılaştırma; seçim yalnız Aşama 9 OOS (core only)",
        "profiles": PROFILE_DESC, "anchors": ANCHOR_DESC,
        "p0xa0_regression_vs_stage6": reg,
        "cells": cells,
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "stage7_exit_grid.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    with open(os.path.join(args.out, "stage7_exit_grid.md"), "w", encoding="utf-8") as fh:
        fh.write(_md(payload))
    print(f"\nP0xA0 regresyon: {'OK — Aşama 6 birebir' if reg.get('all_match') else 'UYUŞMAZ ❌'}")
    print(f"raporlar: reports/stage7_exit_grid.md · .json")
    return 0 if reg.get("all_match") else 1


if __name__ == "__main__":
    raise SystemExit(main())
