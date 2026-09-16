#!/usr/bin/env python3
"""
AŞAMA 4 raporu — momentum geçiş oranları + sinyal zinciri halka sayıları.

    python3 scripts/run_momentum_report.py

Girdi: `data/processed/levels/<KEY>_4h_levels.parquet` (Aşama 2+3 çıktıları).
Bulunamazsa rejim+seviye katmanı yeniden hesaplanır.

Çıktı:
  reports/momentum_report.md · reports/momentum_report.json
  data/processed/signals/<KEY>_4h_signals.parquet   (Aşama 5+ girdisi)

Raporlananlar (kabul kriterleri 5, 6, 7):
  * varlık başına momentum GEÇİŞ ORANI + kalibrasyon bandı [0.10, 0.60] kontrolü
    → bant dışında **TUNE YOK**, yalnızca BAYRAK + not
  * sinyal zincirinin HER halkanın bar sayısı (sıralı, monotone azalan)
  * varlık başına FINAL long_final_ok bar sayısı ve %'si
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quant4h.config import (DEFAULT_LEVELS, DEFAULT_MOMENTUM, DEFAULT_REGIME,  # noqa: E402
                            PARAM_TUNING_STAGE, PARAM_TUNING_UNIVERSE,
                            PER_ASSET_IN_SAMPLE_TUNING_ALLOWED, STOCK_ALLOW_SHORT, UTC,
                            bist_stock_specs)
from quant4h.data import schema  # noqa: E402
from quant4h.features.context import context_summary, longs_allowed  # noqa: E402
from quant4h.features.levels import add_levels  # noqa: E402
from quant4h.features.momentum import (LONG_CHAIN, SHORT_CHAIN, add_momentum,  # noqa: E402
                                       add_signal_chain, momentum_calibration)
from quant4h.features.regime import label_regime, regime_distribution  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SIG_DIR = os.path.join(ROOT, "data", "processed", "signals")


def _load(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    side = path.replace(".parquet", ".attrs.json")
    if os.path.exists(side):
        with open(side, "r", encoding="utf-8") as fh:
            df.attrs.update(json.load(fh))
    return df


def _levels_frame(key: str, tf: str, is_stock: bool) -> Optional[pd.DataFrame]:
    sub = "bist30" if is_stock else ""
    name = f"{key}_{tf}_levels.parquet" if not is_stock else f"{key}_{tf}_levels.parquet"
    for p in (os.path.join(ROOT, "data", "processed", "levels", sub, name),
              os.path.join(ROOT, "data", "processed", "levels", name)):
        df = _load(p)
        if df is not None and len(df):
            return df
    return None


def _rebuild(key: str, tf: str, is_stock: bool, index_4h: Optional[pd.DataFrame],
             allow_short: bool) -> Optional[pd.DataFrame]:
    if is_stock:
        src = _load(os.path.join(ROOT, "data", "processed", "bist30",
                                 f"{key}_{tf}_adjusted.parquet"))
    else:
        src = _load(os.path.join(ROOT, "data", "processed", f"{key.lower()}_{tf}_adjusted.parquet"))
        if src is None:
            src = _load(os.path.join(ROOT, "data", "interim", f"{key.lower()}_{tf}.parquet"))
    if src is None or not len(src):
        return None
    out = label_regime(src)
    out = add_levels(out, DEFAULT_LEVELS, allow_short=allow_short)
    if is_stock and index_4h is not None:
        out = longs_allowed(out, index_4h, tf, DEFAULT_REGIME.ema_trend_period)
    return out


def _included(report: str) -> List[str]:
    if not os.path.exists(report):
        return []
    with open(report, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return sorted(r["code"] for r in doc.get("stocks", []) if r.get("status") == "INCLUDED")


def _analyse(df: pd.DataFrame, name: str, is_stock: bool,
             cfg=DEFAULT_MOMENTUM) -> tuple[Dict[str, Any], pd.DataFrame]:
    out = add_momentum(df, cfg, allow_short=(not is_stock))
    out = add_signal_chain(out, cfg, is_stock=is_stock)
    cal = momentum_calibration(out, cfg, name)
    lc = dict(out.attrs.get("long_chain_counts", {}))
    sc = dict(out.attrs.get("short_chain_counts", {}))
    res: Dict[str, Any] = {
        "name": name, "is_stock": is_stock, "bars": len(out),
        "calibration": cal,
        "long_chain_counts": lc,
        "short_chain_counts": sc,
        "long_final_ok_bars": int(out["long_final_ok"].sum()),
        "long_final_ok_frac": round(float(out["long_final_ok"].mean()), 4) if len(out) else 0.0,
        "short_final_ok_bars": int(out["short_final_ok"].sum()) if "short_final_ok" in out.columns else 0,
        "short_final_ok_frac": round(float(out["short_final_ok"].mean()), 4)
        if "short_final_ok" in out.columns and len(out) else 0.0,
        "regime": regime_distribution(out),
        "context": context_summary(out) if "ctx_reason" in out.columns else {"applied": False},
        "stop_valid_long_bars": int(out["stop_valid_long"].sum()) if "stop_valid_long" in out.columns else 0,
    }
    return res, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    ap.add_argument("--roc-bars", type=int, default=DEFAULT_MOMENTUM.roc_bars)
    ap.add_argument("--threshold-atr", type=float, default=DEFAULT_MOMENTUM.threshold_atr)
    ap.add_argument("--no-save-frames", action="store_true")
    args = ap.parse_args()
    tf = args.timeframe
    cfg = DEFAULT_MOMENTUM
    os.makedirs(args.out, exist_ok=True)
    if not args.no_save_frames:
        os.makedirs(SIG_DIR, exist_ok=True)

    index_4h = _load(os.path.join(ROOT, "data", "interim", f"bist30_{tf}.parquet"))
    core: Dict[str, Any] = {}
    frames: Dict[str, pd.DataFrame] = {}
    print("=== CORE (long+short) ===")
    for key in ("BTC", "GOLD", "SILVER"):
        base = _levels_frame(key, tf, False)
        if base is None:
            base = _rebuild(key, tf, False, index_4h, allow_short=True)
        if base is None:
            print(f"  [{key}] veri yok")
            continue
        res, out = _analyse(base, key, False, cfg)
        core[key] = res
        frames[key] = out
        if not args.no_save_frames:
            out.to_parquet(os.path.join(SIG_DIR, f"{key}_{tf}_signals.parquet"), index=False)
        c = res["calibration"]
        print(f"  [{key:7s}] bar={res['bars']:6d} mom_geçiş=%{c['long_pass_rate_of_valid'] * 100:5.1f} "
              f"bant={c['in_band']} | zincir={res['long_chain_counts']} | "
              f"FINAL_long={res['long_final_ok_bars']} (%{res['long_final_ok_frac'] * 100:.2f}) "
              f"FINAL_short={res['short_final_ok_bars']}")

    xu = _levels_frame("BIST30", tf, False)
    if xu is None:
        xu = _rebuild("BIST30", tf, False, index_4h, allow_short=True)
    ctx_res: Dict[str, Any] = {}
    if xu is not None:
        ctx_res, _ = _analyse(xu, "XU030", False, cfg)
        ctx_res["role"] = "context_filter_source (trade YOK)"

    codes = _included(os.path.join(ROOT, "reports", "bist30_universe_qc.json"))
    specs = bist_stock_specs()
    stocks: Dict[str, Any] = {}
    print(f"\n=== BIST30 sepet ({len(codes)} hisse, LONG-ONLY) ===")
    for code in codes:
        base = _levels_frame(code, tf, True)
        if base is None:
            base = _rebuild(code, tf, True, index_4h, allow_short=False)
        if base is None:
            stocks[code] = {"error": "veri yok"}
            continue
        res, out = _analyse(base, code, True, cfg)
        sp = specs.get(f"BIST_{code}")
        res["sector"] = sp.extras.get("sector", "") if sp else ""
        stocks[code] = res
        frames[code] = out
        if not args.no_save_frames:
            out.to_parquet(os.path.join(SIG_DIR, f"{code}_{tf}_signals.parquet"), index=False)
        c = res["calibration"]
        print(f"  [{code:6s}] mom_geçiş=%{c['long_pass_rate_of_valid'] * 100:5.1f} "
              f"{'✅' if c['in_band'] else '⚠️ BANT DIŞI'} | "
              f"FINAL_long={res['long_final_ok_bars']:4d} (%{res['long_final_ok_frac'] * 100:4.1f}) | "
              f"zincir son={list(res['long_chain_counts'].values())[-1] if res['long_chain_counts'] else '-'}")

    payload = {
        "generated_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
        "timeframe": tf,
        "momentum_policy": {
            "formula": "mom = (close/close.shift(n) − 1) / (ATR14/close.shift(n))",
            "roc_bars": args.roc_bars, "threshold_atr": args.threshold_atr,
            "roc_candidates": list(cfg.roc_candidates),
            "threshold_candidates": list(cfg.threshold_candidates),
            "selection_now": False, "selection_stage": PARAM_TUNING_STAGE,
            "tuning_universe": list(PARAM_TUNING_UNIVERSE),
            "per_asset_in_sample_tuning_allowed": PER_ASSET_IN_SAMPLE_TUNING_ALLOWED,
            "calibration_band": list(cfg.calibration_band),
            "tune_out_of_band": cfg.tune_out_of_band,
            "forbidden": ["RSI", "MACD", "Stochastic", "StochRSI", "MFI", "OBV", "CCI", "Williams%R"],
            "decision_time_contract": "bar t kararı bar t AÇILIŞINDA verilir; close[t−1] ve "
                                      "close[t−n] o ana kadar KAPANMIŞTIR",
            "guard": ["ATR NaN/<=0", "close[t−n] NaN/<=0", "non_tradable", "return_valid==False",
                      f"ilk {args.roc_bars} bar (warmup)"],
            "atr_policy": "ATR kolonu VARSA kullanılır (Aşama 2 ile aynı seri); yoksa hesaplanır. "
                          "Tamamen NaN olsa bile YENİDEN HESAPLANMAZ — guard yakalar.",
            "stock_allow_short": STOCK_ALLOW_SHORT,
        },
        "long_chain": [c for _, c in LONG_CHAIN],
        "short_chain": [c for _, c in SHORT_CHAIN],
        "core_assets": core,
        "context_source": ctx_res,
        "stocks": stocks,
    }
    with open(os.path.join(args.out, "momentum_report.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    md = _markdown(payload)
    with open(os.path.join(args.out, "momentum_report.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"\nraporlar: {os.path.join(args.out, 'momentum_report.md')} · momentum_report.json")
    if not args.no_save_frames:
        print(f"sinyal frame'leri: {len(frames)} dosya -> data/processed/signals/")
    return 0


def _pct(x: Optional[float], nd: int = 1) -> str:
    return "—" if x is None else f"%{x * 100:.{nd}f}"


def _markdown(p: Dict[str, Any]) -> str:
    pol = p["momentum_policy"]
    lo, hi = pol["calibration_band"]
    L: List[str] = []
    L.append("# AŞAMA 4 — Momentum Onayı ve Sinyal Zinciri Raporu")
    L.append("")
    L.append(f"*Üretim: {p['generated_at_utc'][:19]} UTC* · timeframe **{p['timeframe']}** · "
             f"**n={pol['roc_bars']}**, **m={pol['threshold_atr']} ATR** (varsayılan)")
    L.append("")
    L.append("## TEK MOMENTUM KURALI")
    L.append("")
    L.append("```")
    L.append(pol["formula"])
    L.append("long  onayı: mom > +m        short onayı: mom < −m   (short yalnız CORE)")
    L.append("```")
    L.append("")
    L.append(f"- **YASAKLI olanlar kullanılmadı:** {', '.join(pol['forbidden'])}")
    L.append(f"- **Karar anı sözleşmesi:** {pol['decision_time_contract']}")
    L.append(f"- **Guard (fail-closed):** {' · '.join(pol['guard'])}")
    L.append(f"- **ATR politikası:** {pol['atr_policy']}")
    L.append(f"- **Parametre seçimi YOK:** aday kümeler `n={pol['roc_candidates']}`, "
             f"`m={pol['threshold_candidates']}` → yalnızca **Aşama {pol['selection_stage']}**, "
             f"yalnızca **{pol['tuning_universe']}** üzerinde. "
             f"`per_asset_in_sample_tuning_allowed={pol['per_asset_in_sample_tuning_allowed']}`")
    L.append(f"- **Kalibrasyon bandı:** [{lo:.2f}, {hi:.2f}] · bant dışında "
             f"**TUNE EDİLMEZ**, yalnızca bayraklanır (`tune_out_of_band={pol['tune_out_of_band']}`)")
    L.append("")
    L.append("## SİNYAL ZİNCİRİ (kabul kriteri 5)")
    L.append("")
    L.append("```")
    L.append("long_final_ok  = " + " ∧ ".join(c for c in p["long_chain"]))
    L.append("short_final_ok = " + " ∧ ".join(c for c in p["short_chain"]) + "   (yalnız CORE)")
    L.append("```")
    L.append("")
    L.append("> Bir kapı kolonu frame'de YOKSA zincir **False** üretir (fail-closed); "
             "sessizce 'geçti' sayılmaz. `test_missing_gate_is_fail_closed_not_pass` ile kilitli.")
    L.append("")
    L.append("## KALİBRASYON: MOMENTUM GEÇİŞ ORANLARI")
    L.append("")
    L.append(f"Bant **[{lo * 100:.0f}%, {hi * 100:.0f}%]**. Oran = `momentum_ok` / `momentum_valid`.")
    L.append("")
    L.append("| Varlık | bar | mom geçerli % | **long geçiş %** | short geçiş % | bant | mom p05/p50/p95 | |mom| p50 |")
    L.append("|---|---:|---:|---:|---:|---|---|---:|")
    rows = list(p["core_assets"].items())
    if p.get("context_source"):
        rows.append(("XU030", p["context_source"]))
    rows += list(p["stocks"].items())
    flags: List[str] = []
    for name, r in rows:
        if "error" in r:
            continue
        c = r["calibration"]
        mark = "✅ içinde" if c["in_band"] else "⚠️ **DIŞINDA**"
        if not c["in_band"]:
            flags.append(f"**{name}** — {c['calibration_flag']}")
        L.append(f"| **{name}** | {r['bars']} | {_pct(c['momentum_valid_frac'])} | "
                 f"**{_pct(c['long_pass_rate_of_valid'])}** | {_pct(c['short_pass_rate_of_valid'])} | "
                 f"{mark} | {c['mom_p05']} / {c['mom_p50']} / {c['mom_p95']} | {c['mom_abs_p50']} |")
    L.append("")
    if flags:
        L.append("### ⚠️ BANT DIŞI KALİBRASYON BAYRAKLARI (TUNE EDİLMEDİ)")
        L.append("")
        for f in flags:
            L.append(f"- {f}")
        L.append("")
        L.append("> Kabul kriteri 6 gereği bu oranlar **değiştirilmedi**. Eşik veya `n` "
                 "burada ayarlansaydı, bu bir in-sample optimizasyon olurdu ve Aşama 9'un "
                 "out-of-sample iddiasını geçersiz kılardı.")
    else:
        L.append("### ✅ Tüm varlıklar kalibrasyon bandı içinde — bayrak YOK")
        L.append("")
    L.append("## ZİNCİR HALKALARI: BAR SAYILARI (sıralı)")
    L.append("")
    L.append("| Varlık | " + " | ".join(lbl for lbl, _ in LONG_CHAIN) + " | **FINAL long** | % |")
    L.append("|---|" + "---:|" * (len(LONG_CHAIN) + 2))
    for name, r in rows:
        if "error" in r:
            continue
        cc = r.get("long_chain_counts", {})
        vals = []
        for lbl, col in LONG_CHAIN:
            if lbl == "context" and not r.get("is_stock"):
                vals.append("—")
            else:
                vals.append(str(cc.get(lbl, "—")))
        L.append(f"| **{name}** | " + " | ".join(vals) +
                 f" | **{r.get('long_final_ok_bars', 0)}** | {_pct(r.get('long_final_ok_frac', 0))} |")
    L.append("")
    L.append("### CORE varlıklar — short zinciri")
    L.append("")
    L.append("| Varlık | " + " | ".join(lbl for lbl, _ in SHORT_CHAIN) + " | **FINAL short** |")
    L.append("|---|" + "---:|" * (len(SHORT_CHAIN) + 1))
    for name, r in p["core_assets"].items():
        sc = r.get("short_chain_counts", {})
        L.append(f"| **{name}** | " + " | ".join(str(sc.get(lbl, "—")) for lbl, _ in SHORT_CHAIN) +
                 f" | **{r.get('short_final_ok_bars', 0)}** |")
    L.append("")
    L.append("> Hisselerde short zinciri **politika gereği üretilmez** "
             f"(`STOCK_ALLOW_SHORT={pol['stock_allow_short']}`, KARAR 4: LONG-ONLY).")
    L.append("")
    L.append("## FİNAL SİNYAL ÖZETİ")
    L.append("")
    L.append("| Varlık | bar | rejim long | bağlam izin | seviye (stop) geçerli | mom long | **FINAL long** | **%** |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    tot = {"bars": 0, "final": 0}
    for name, r in rows:
        if "error" in r:
            continue
        cc = r.get("long_chain_counts", {})
        rg = r.get("regime", {})
        ctx = r.get("context", {}) or {}
        L.append(f"| **{name}** | {r['bars']} | {rg.get('long_regime_ok_bars', '—')} | "
                 f"{ctx.get('longs_allowed_bars', '—') if ctx.get('applied') else '—'} | "
                 f"{r.get('stop_valid_long_bars', '—')} | {cc.get('momentum', '—')} | "
                 f"**{r.get('long_final_ok_bars', 0)}** | {_pct(r.get('long_final_ok_frac', 0))} |")
        if r.get("is_stock"):
            tot["bars"] += r["bars"]
            tot["final"] += r.get("long_final_ok_bars", 0)
    if tot["bars"]:
        L.append(f"| **SEPET TOPLAM (28 hisse)** | {tot['bars']} | | | | | "
                 f"**{tot['final']}** | {_pct(tot['final'] / tot['bars'], 2)} |")
    L.append("")
    L.append("## ZORUNLU CAVEAT'LER")
    L.append("")
    L.append("- Momentum onayı bir **olasılık filtresidir**, kesinlik değildir. Geçmiş geçiş "
             "oranları gelecekteki oranları garanti etmez.")
    L.append("- `n=10` ve `m=1.0` **VARSAYILANDIR**, optimize EDİLMEMİŞTİR. Aşama 9'da küçük "
             "aday kümesiyle ve yalnızca core varlıklar üzerinde test edilecek; hisseler "
             "yalnızca OOS raporlanacak.")
    L.append("- Guard'ın elediği barlar (kesinti, ince bar, kurumsal aksiyon, oluşmakta olan bar) "
             "**silinmez**; yalnızca sinyale katılmaz. Bu, örneklem sayısını küçültür ama "
             "veri bütünlüğünü korur.")
    L.append("- BIST30 sepeti **survivorship bias** taşır: momentum geçiş oranları da bu "
             "çarpık örnekleme aittir.")
    L.append("- Zincirdeki her halka **fail-closed**'tur: kolon yoksa veya değer bilinmiyorsa "
             "sonuç False'tur. Bu tasarım işlem SAYISINI azaltır, yanlış sinyal oranını düşürür.")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
