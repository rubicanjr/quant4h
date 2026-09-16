#!/usr/bin/env python3
"""
AŞAMA 2 raporu — rejim etiket dağılımı + XU030 bağlam filtresi.

    python3 scripts/run_regime_report.py

Kapsam:
  * core varlıklar  : BTC · GOLD · SILVER           (long + short, filtresiz)
  * bağlam endeksi  : XU030                          (filtre kaynağı, trade YOK)
  * hisse sepeti    : Aşama 1.5'te SEPETE GİREN 28 hisse (LONG-ONLY + filtreli)

Her varlık için: EMA200 yönü + ATR yüzdeliği → 6 durumlu rejim etiketi,
ısınma (etiketsiz) oranı, long/short izinli bar sayısı; hisselerde ayrıca
XU030 filtresinin izin verdiği bar sayısı ve ret sebepleri.

Çıktılar:
  reports/regime_report.md      (dağılım tabloları + zorunlu caveat'ler)
  reports/regime_report.json
  data/processed/regime/<KEY>_4h_regime.parquet   (etiketli frame'ler)
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

from quant4h.config import DEFAULT_ASSETS, DEFAULT_REGIME, UTC, bist_stock_specs  # noqa: E402
from quant4h.data import schema  # noqa: E402
from quant4h.features.context import context_summary, longs_allowed  # noqa: E402
from quant4h.features.regime import (label_regime, regime_distribution,  # noqa: E402
                                     regime_report_markdown)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGIME_DIR = os.path.join(ROOT, "data", "processed", "regime")


def _load(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    side = path.replace(".parquet", ".attrs.json")
    if os.path.exists(side):
        with open(side, "r", encoding="utf-8") as fh:
            df.attrs.update(json.load(fh))
    return df


def _processed(asset_key: str, tf: str) -> Optional[pd.DataFrame]:
    key = asset_key.lower()
    for p in (os.path.join(ROOT, "data", "processed", f"{key}_{tf}_adjusted.parquet"),
              os.path.join(ROOT, "data", "interim", f"{key}_{tf}.parquet")):
        df = _load(p)
        if df is not None and len(df):
            return df
    return None


def _stock(code: str, tf: str) -> Optional[pd.DataFrame]:
    for p in (os.path.join(ROOT, "data", "processed", "bist30", f"{code}_{tf}_adjusted.parquet"),
              os.path.join(ROOT, "data", "interim", "bist30", f"{code}_{tf}.parquet")):
        df = _load(p)
        if df is not None and len(df):
            return df
    return None


def _included_codes(report_path: str) -> List[str]:
    if not os.path.exists(report_path):
        return []
    with open(report_path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return sorted(r["code"] for r in doc.get("stocks", []) if r.get("status") == "INCLUDED")


def _mask_tradable(dist: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
    """Rejim istatistiklerini yalnızca İŞLEM UYGUN barlar üzerinden özetle."""
    if "non_tradable" in df.columns:
        trad = ~pd.to_numeric(df["non_tradable"], errors="coerce").fillna(False).astype(bool)
    else:
        trad = pd.Series(True, index=df.index)
    dist["tradable_bars"] = int(trad.sum())
    dist["tradable_frac"] = round(float(trad.mean()), 4)
    lab = df["regime_valid"].astype(bool) & trad
    dist["labelled_tradable_bars"] = int(lab.sum())
    dist["labelled_tradable_frac"] = round(float(lab.sum() / trad.sum()), 4) if trad.sum() else 0.0
    dist["long_ok_tradable"] = int((df["long_regime_ok"] & trad).sum())
    dist["short_ok_tradable"] = int((df["short_regime_ok"] & trad).sum())
    if lab.sum():
        vc = df.loc[lab, "regime"].astype(str).value_counts()
        dist["regime_counts_tradable"] = {str(k): int(v) for k, v in vc.items()}
        dist["regime_pct_tradable"] = {str(k): round(float(v) / int(lab.sum()) * 100, 2)
                                       for k, v in vc.items()}
    return dist


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--ema-period", type=int, default=DEFAULT_REGIME.ema_trend_period)
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    ap.add_argument("--no-save-frames", action="store_true")
    args = ap.parse_args()

    tf = args.timeframe
    os.makedirs(args.out, exist_ok=True)
    if not args.no_save_frames:
        os.makedirs(REGIME_DIR, exist_ok=True)

    index_4h = _load(os.path.join(ROOT, "data", "interim", f"bist30_{tf}.parquet"))
    if index_4h is None or not len(index_4h):
        print("!! XU030 bağlam verisi yok: data/interim/bist30_4h.parquet")
        return 1

    core_rows: Dict[str, Dict[str, Any]] = {}
    ctx_rows: Dict[str, Dict[str, Any]] = {}
    stock_rows: Dict[str, Dict[str, Any]] = {}
    saved: List[str] = []

    # ---- core assets (long + short, context filter YOK) ----
    print("=== CORE varlıklar (long+short, XU030 filtresi YOK) ===")
    for key in ("BTC", "GOLD", "SILVER", "BIST30"):
        df = _processed(key, tf)
        if df is None:
            print(f"  [{key:7s}] veri yok, atlandı")
            continue
        out = label_regime(df)
        dist = regime_distribution(out)
        dist = _mask_tradable(dist, out)
        # BIST30 endeksi = bağlam kaynağı; trade edilmez
        if key == "BIST30":
            dist["role"] = "context_filter_source"
            ctx_rows[key] = dist
        else:
            dist["role"] = "core_tradable"
            core_rows[key] = dist
        if not args.no_save_frames:
            p = os.path.join(REGIME_DIR, f"{key}_{tf}_regime.parquet")
            out.to_parquet(p, index=False)
            saved.append(p)
        print(f"  [{key:7s}] bar={dist['bars']:6d} etiketli={dist['labelled_bars']:6d} "
              f"trend={dist.get('trend_counts')} long_ok={dist['long_regime_ok_bars']} "
              f"short_ok={dist['short_regime_ok_bars']}")

    # ---- XU030 bağlam sinyali ----
    xu = label_regime(index_4h)
    xu_dist = _mask_tradable(regime_distribution(xu), xu)
    xu_dist["role"] = "context_filter_source"
    ctx_rows["XU030"] = xu_dist

    # ---- stock basket (LONG-ONLY + context filter) ----
    codes = _included_codes(os.path.join(ROOT, "reports", "bist30_universe_qc.json"))
    specs = bist_stock_specs()
    print(f"\n=== BIST30 hisse sepeti ({len(codes)} hisse, LONG-ONLY + XU030 filtresi) ===")
    for code in codes:
        df = _stock(code, tf)
        if df is None or not len(df):
            stock_rows[code] = {"error": "veri yok"}
            print(f"  [{code:6s}] veri yok")
            continue
        spec = specs.get(f"BIST_{code}")
        out = label_regime(df)
        out = longs_allowed(out, index_4h, tf, args.ema_period)
        # nihai long izni = rejim izni AND bağlam filtresi AND işlem-uygun bar
        trad = (~pd.to_numeric(out["non_tradable"], errors="coerce").fillna(False).astype(bool)
                if "non_tradable" in out.columns else pd.Series(True, index=out.index))
        ret_ok = (out["return_valid"].astype(bool) if "return_valid" in out.columns
                  else pd.Series(True, index=out.index))
        out["long_final_ok"] = (out["long_regime_ok"] & out["longs_allowed"] & trad & ret_ok)
        dist = regime_distribution(out)
        dist = _mask_tradable(dist, out)
        dist["context"] = context_summary(out)
        dist["long_final_ok_bars"] = int(out["long_final_ok"].sum())
        dist["long_final_ok_frac"] = round(float(out["long_final_ok"].mean()), 4)
        dist["sector"] = (spec.extras.get("sector", "") if spec else "")
        dist["short_allowed_by_policy"] = False     # KARAR 4: hisseler LONG-ONLY
        stock_rows[code] = dist
        if not args.no_save_frames:
            p = os.path.join(REGIME_DIR, f"{code}_{tf}_regime.parquet")
            out.to_parquet(p, index=False)
            saved.append(p)
        c = dist["context"]
        print(f"  [{code:6s}] bar={dist['bars']:5d} etiketli={dist['labelled_bars']:5d} "
              f"trend_up={dist.get('trend_counts', {}).get('trend_up', 0):5d} "
              f"rejim_long={dist['long_regime_ok_bars']:5d} ctx_izin={c['longs_allowed_bars']:5d} "
              f"({c['longs_allowed_frac'] * 100:4.1f}%) FINAL_long={dist['long_final_ok_bars']:5d} "
              f"({dist['long_final_ok_frac'] * 100:4.1f}%)")

    # ---- rapor ----
    payload = {
        "generated_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
        "timeframe": tf,
        "regime_policy": {
            "trend_filter": f"EMA{args.ema_period} yönü (close vs EMA + ATR-normalize eğim)",
            "volatility_filter": f"ATR({DEFAULT_REGIME.atr_period}) yüzdelik dilimi, "
                                 f"{DEFAULT_REGIME.atr_percentile_window} bar geriye dönük",
            "states": "trend_up|trend_down|range × vol_high|vol_normal|vol_low = 6 durum",
            "long_allowed_in": list(DEFAULT_REGIME.long_allowed_in),
            "short_allowed_in": list(DEFAULT_REGIME.short_allowed_in),
            "max_atr_percentile": DEFAULT_REGIME.max_atr_percentile,
            "min_bars_for_regime": DEFAULT_REGIME.min_bars_for_regime,
            "fail_closed": DEFAULT_REGIME.fail_closed,
            "cancelled_methods": ["ADX", "Hurst", "HMM", "Choppiness", "Bollinger width",
                                  "Ichimoku", "Supertrend", "Keltner"],
        },
        "context_filter": {
            "index": "XU030.IS (4H)",
            "rule": "BIST30 hisseleri LONG-ONLY; yeni long yalnızca XU030 4H kapanış > EMA200 "
                    "iken. Endeks EMA200 altındayken YENİ sinyal açılmaz; MEVCUT pozisyonlar "
                    "kendi stoplarıyla yönetilir (zorla kapatma YOK).",
            "core_assets": "BTC/GOLD/SILVER long+short, filtreye TABİ DEĞİL",
            "anti_lookahead": "karar anı = bar_open - 1 bar; yalnızca KAPANMIŞ XU030 barı kullanılır",
            "fail_closed": True,
            "max_context_age_hours": 120,
            "ema_period": args.ema_period,
        },
        "core_assets": core_rows,
        "context_source": ctx_rows,
        "stocks": stock_rows,
        "saved_frames": [os.path.relpath(p, ROOT) for p in saved],
    }
    with open(os.path.join(args.out, "regime_report.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)

    md = _markdown(payload)
    with open(os.path.join(args.out, "regime_report.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"\nraporlar: {os.path.join(args.out, 'regime_report.md')} · regime_report.json")
    if saved:
        print(f"etiketli frame'ler: {len(saved)} dosya -> data/processed/regime/")
    return 0


def _markdown(payload: Dict[str, Any]) -> str:
    L: List[str] = []
    pol = payload["regime_policy"]
    cf = payload["context_filter"]
    L.append("# AŞAMA 2 — Piyasa Rejimi ve XU030 Bağlam Filtresi Raporu")
    L.append("")
    L.append(f"*Üretim: {payload['generated_at_utc'][:19]} UTC* · timeframe **{payload['timeframe']}**")
    L.append("")
    L.append("## REJİM POLİTİKASI (sadelik kuralı)")
    L.append("")
    L.append(f"- **Trend filtresi:** {pol['trend_filter']}")
    L.append(f"- **Volatilite filtresi:** {pol['volatility_filter']}")
    L.append(f"- **Durumlar:** {pol['states']}")
    L.append(f"- Long izni: `{pol['long_allowed_in']}` · Short izni: `{pol['short_allowed_in']}` · "
             f"ATR yüzdelik tavanı: `{pol['max_atr_percentile']}`")
    L.append(f"- Isınma: ilk `{pol['min_bars_for_regime']}` bar etiketsiz · `fail_closed={pol['fail_closed']}` "
             f"→ **rejim bilinmiyorsa sinyal YOK**")
    L.append(f"- **İPTAL EDİLEN yöntemler:** {', '.join(pol['cancelled_methods'])} "
             f"(config'te bile tutulmuyor: kullanılmayan parametre = overfitting yüzeyi)")
    L.append("")
    L.append("## XU030 BAĞLAM FİLTRESİ (KARAR 4)")
    L.append("")
    L.append(f"- **Kural:** {cf['rule']}")
    L.append(f"- **Core varlıklar:** {cf['core_assets']}")
    L.append(f"- **Anti look-ahead:** {cf['anti_lookahead']}")
    L.append(f"- **Fail-closed:** `{cf['fail_closed']}` · maks bağlam yaşı `{cf['max_context_age_hours']}` saat "
             f"· EMA periyodu `{cf['ema_period']}`")
    L.append("")
    L.append("## ZORUNLU CAVEAT'LER")
    L.append("")
    L.append("- Rejim etiketi bir **tahmin**dir, kesinlik değildir; geçmiş rejim dağılımı "
             "gelecekteki dağılımı garanti etmez.")
    L.append("- `range` rejiminde **yeni sinyal üretilmez**. Bu, fırsat kaçırmak pahasına "
             "yanlış sinyali azaltmayı seçen bilinçli bir tercihtir.")
    L.append("- Isınma döneminde (ilk ~500 bar) etiket YOKTUR; bu barlar backtest'te "
             "kullanılamaz. Metallerde bu, ~2.4 yıllık geçmişin %14'üdür.")
    L.append("- **SURVIVORSHIP BIAS:** hisse sepeti yalnızca BUGÜN BIST30'da olan 28 hisseyi "
             "içerir. Rejim dağılımı da bu çarpık örnekleme aittir.")
    L.append("- XU030 filtresi long'ları bastırdığında **mevcut pozisyonlar zorla kapatılmaz**; "
             "bu bir tasarım kararıdır ve düşen piyasada taşıma riskini azaltmaz.")
    L.append("")
    L.append("## CORE VARLIKLAR")
    L.append("")
    L.append("| Varlık | rol | bar | işlem-uygun | etiketli | etiketsiz % | trend_up | trend_down | range | "
             "vol_high | vol_normal | vol_low | long OK | short OK |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    allrows: Dict[str, Any] = {}
    allrows.update(payload["core_assets"])
    for k, v in payload["context_source"].items():
        allrows.setdefault(k, v)
    for name, d in allrows.items():
        tc, vc = d.get("trend_counts", {}), d.get("vol_counts", {})
        L.append(f"| **{name}** | {d.get('role', '')} | {d.get('bars', 0)} | "
                 f"{d.get('tradable_bars', '-')} | {d.get('labelled_bars', 0)} | "
                 f"%{d.get('unlabelled_frac', 0) * 100:.1f} | {tc.get('trend_up', 0)} | "
                 f"{tc.get('trend_down', 0)} | {tc.get('range', 0)} | {vc.get('vol_high', 0)} | "
                 f"{vc.get('vol_normal', 0)} | {vc.get('vol_low', 0)} | "
                 f"{d.get('long_regime_ok_bars', 0)} | {d.get('short_regime_ok_bars', 0)} |")
    L.append("")
    L.append("## BIST30 HİSSE SEPETİ — REJİM DAĞILIMI VE FİLTRE SONUCU")
    L.append("")
    L.append("| Hisse | sektör | bar | işlem-uygun | etiketli | trend_up | trend_down | range | "
             "vol_high | rejim long | XU030 izin | **FINAL long** | final % |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    tot = {"bars": 0, "trend_up": 0, "trend_down": 0, "range": 0, "regime_long": 0,
           "ctx_ok": 0, "final": 0}
    for code, d in payload["stocks"].items():
        if "error" in d:
            L.append(f"| **{code}** | - | - | - | - | - | - | - | - | - | - | - | VERİ YOK |")
            continue
        tc, vc = d.get("trend_counts", {}), d.get("vol_counts", {})
        c = d.get("context", {})
        L.append(f"| **{code}** | {d.get('sector', '')} | {d.get('bars', 0)} | "
                 f"{d.get('tradable_bars', 0)} | {d.get('labelled_bars', 0)} | "
                 f"{tc.get('trend_up', 0)} | {tc.get('trend_down', 0)} | {tc.get('range', 0)} | "
                 f"{vc.get('vol_high', 0)} | {d.get('long_regime_ok_bars', 0)} | "
                 f"{c.get('longs_allowed_bars', 0)} | **{d.get('long_final_ok_bars', 0)}** | "
                 f"%{d.get('long_final_ok_frac', 0) * 100:.1f} |")
        tot["bars"] += d.get("bars", 0)
        tot["trend_up"] += tc.get("trend_up", 0)
        tot["trend_down"] += tc.get("trend_down", 0)
        tot["range"] += tc.get("range", 0)
        tot["regime_long"] += d.get("long_regime_ok_bars", 0)
        tot["ctx_ok"] += c.get("longs_allowed_bars", 0)
        tot["final"] += d.get("long_final_ok_bars", 0)
    if tot["bars"]:
        L.append(f"| **TOPLAM** | | {tot['bars']} | | | {tot['trend_up']} | {tot['trend_down']} | "
                 f"{tot['range']} | | {tot['regime_long']} | {tot['ctx_ok']} | **{tot['final']}** | "
                 f"%{tot['final'] / tot['bars'] * 100:.1f} |")
    L.append("")
    L.append("### XU030 filtresi ret sebepleri (sepet toplamı)")
    L.append("")
    reasons: Dict[str, int] = {}
    for d in payload["stocks"].values():
        for k, v in (d.get("context", {}) or {}).get("reasons", {}).items():
            reasons[k] = reasons.get(k, 0) + int(v)
    L.append("| Sebep | bar | anlamı |")
    L.append("|---|---:|---|")
    meaning = {
        "context_ok": "XU030 EMA200 ÜSTÜNDE → long'a izin var",
        "context_below_ema200": "XU030 EMA200 ALTINDA → **yeni long YOK** (mevcut pozisyon stopla yönetilir)",
        "context_warmup": "XU030 EMA200 henüz hazır değil → fail-closed, long YOK",
        "context_stale": "en son kapanmış XU030 barı çok eski → fail-closed, long YOK",
        "context_missing": "karar anından önce kapanmış XU030 barı yok → fail-closed, long YOK",
        "context_not_applicable": "filtre bu varlığa uygulanmıyor (core varlık)",
    }
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        L.append(f"| `{k}` | {v} | {meaning.get(k, '')} |")
    L.append("")
    L.append("## FİNAL LONG İZNİNİN BİLEŞİMİ")
    L.append("")
    L.append("```")
    L.append("long_final_ok = long_regime_ok      # trend_up VE ATR yüzdeliği <= tavan")
    L.append("              AND longs_allowed      # XU030 4H kapanış > EMA200 (KAPANMIŞ bar, fail-closed)")
    L.append("              AND NOT non_tradable   # kesinti / ince açılış barı / henüz oluşuyor / kurumsal aksiyon")
    L.append("              AND return_valid       # boşluğu veya ex-date'i atlayan getiri DEĞİL")
    L.append("```")
    L.append("")
    L.append("> Short sinyali hisse sepetinde **politika gereği kapalıdır** (LONG-ONLY). "
             "Core varlıklarda `short_regime_ok` yalnızca `trend_down` rejiminde açılır ve "
             "XU030 filtresine tabi değildir.")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
