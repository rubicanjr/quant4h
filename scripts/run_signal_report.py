#!/usr/bin/env python3
"""
AŞAMA 5 raporu — giriş tetiği, sinyal montajı, cooldown ve icra zamanı.

    python3 scripts/run_signal_report.py
    python3 scripts/run_signal_report.py --cooldown-bars 3 --max-position-bars 90

Girdi : data/processed/levels/<KEY>_4h_levels.parquet (Aşama 2+3)
Çıktı : reports/signal_report.md · reports/signal_report.json
        data/processed/signals/<KEY>_4h_signals.parquet

ÜÇ sinyal akışı birlikte raporlanır (kabul kriteri 4'ün dürüst sunumu):
  A) `strict`  — KULLANICI KURALI: pozisyon açıkken yeni sinyal YOK
                 (pozisyon vekili: dondurulmuş stop'un bar içi ihlali) + cooldown 3 bar
  B) `capped`  — A + zorunlu time-stop (`--max-position-bars`, varsayılan 90)
  C) `cooldown_only` — pozisyon takibi YOK, yalnızca cooldown 3 bar

Neden üçü birden: A, şartnamedeki kuraldır; ama yapısal stop ~2.6 ATR geride
olduğu için fiyat onu yıllarca ihlal etmeyebiliyor ve pozisyon neredeyse hep
açık kalıp ham sinyallerin ~%99'unu bastırıyor (BTC: 592 ham → 3 final). Bu bir
kod hatası DEĞİL; Aşama 7'nin (TP / trailing / time-stop) neden zorunlu
olduğunun ölçülmüş kanıtıdır. B ve C bu etkinin büyüklüğünü gösterir.
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
                            STOCK_ALLOW_SHORT, UTC)
from quant4h.features.context import context_summary, longs_allowed  # noqa: E402
from quant4h.features.momentum import add_momentum  # noqa: E402
from quant4h.strategy.signals import (LONG_CHAIN_V2, SHORT_CHAIN_V2,  # noqa: E402
                                      build_signals, signal_stats)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SIG_DIR = os.path.join(ROOT, "data", "processed", "signals")

VARIANTS = ("strict", "capped", "cooldown_only")


def _load(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    side = path.replace(".parquet", ".attrs.json")
    if os.path.exists(side):
        with open(side, "r", encoding="utf-8") as fh:
            df.attrs.update(json.load(fh))
    return df


def _levels(key: str, tf: str, is_stock: bool) -> Optional[pd.DataFrame]:
    cands = ([os.path.join(ROOT, "data", "processed", "levels", "bist30", f"{key}_{tf}_levels.parquet")]
             if is_stock else [])
    cands += [os.path.join(ROOT, "data", "processed", "levels", f"{key}_{tf}_levels.parquet")]
    for p in cands:
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


def build_variant(base: pd.DataFrame, variant: str, is_stock: bool, cooldown: int,
                  max_pos: Optional[int], tf: str) -> pd.DataFrame:
    allow_short = (not is_stock)
    out = add_momentum(base, DEFAULT_MOMENTUM, allow_short=allow_short)
    if is_stock and "longs_allowed" not in out.columns:
        idx = _load(os.path.join(ROOT, "data", "interim", f"bist30_{tf}.parquet"))
        out = longs_allowed(out, idx, tf, DEFAULT_REGIME.ema_trend_period)
    if variant == "strict":
        kw: Dict[str, Any] = {"position_exit_proxy": "frozen_stop_intrabar"}
    elif variant == "capped":
        kw = {"position_exit_proxy": "frozen_stop_intrabar", "max_position_bars": max_pos}
    elif variant == "cooldown_only":
        kw = {"position_exit_proxy": "none"}
    else:
        raise ValueError(variant)
    return build_signals(out, is_stock=is_stock, cooldown_bars=cooldown,
                         trigger_period=DEFAULT_LEVELS.donchian_period,
                         allow_short=allow_short, **kw)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--cooldown-bars", type=int, default=3)
    ap.add_argument("--max-position-bars", type=int, default=90)
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    ap.add_argument("--no-save-frames", action="store_true")
    args = ap.parse_args()
    tf = args.timeframe
    os.makedirs(args.out, exist_ok=True)
    if not args.no_save_frames:
        os.makedirs(SIG_DIR, exist_ok=True)

    index_4h = _load(os.path.join(ROOT, "data", "interim", f"bist30_{tf}.parquet"))
    assets: List[tuple] = [("BTC", False), ("GOLD", False), ("SILVER", False),
                           ("BIST30", False)]
    assets += [(c, True) for c in
               _included(os.path.join(ROOT, "reports", "bist30_universe_qc.json"))]

    results: Dict[str, Dict[str, Any]] = {}
    print(f"cooldown={args.cooldown_bars} bar · max_position_bars={args.max_position_bars} · "
          f"tetik=Donchian({DEFAULT_LEVELS.donchian_period}) · n={DEFAULT_MOMENTUM.roc_bars} "
          f"m={DEFAULT_MOMENTUM.threshold_atr}")
    for key, is_stock in assets:
        base = _levels(key, tf, is_stock)
        if base is None:
            print(f"  [{key}] seviye verisi yok (once run_levels_report.py)")
            results[key] = {"error": "veri yok", "is_stock": is_stock}
            continue
        if key == "BIST30" and not is_stock:
            # XU030 = bağlam kaynağı, trade YOK; yine de tetik istatistiği raporlanır
            pass
        per: Dict[str, Any] = {"is_stock": is_stock, "bars": len(base),
                               "role": "context_filter_source" if key == "BIST30" and not is_stock
                                       else ("stock" if is_stock else "core_tradable"),
                               "variants": {}}
        for variant in VARIANTS:
            out = build_variant(base, variant, is_stock, args.cooldown_bars,
                                args.max_position_bars, tf)
            st = signal_stats(out, tf)
            per["variants"][variant] = st
            per["chain_long"] = out.attrs.get("long_chain_counts", {})
            per["chain_short"] = out.attrs.get("short_chain_counts", {})
            per["engine"] = out.attrs.get("signal_engine", {})
            per["context"] = context_summary(out) if "ctx_reason" in out.columns else {"applied": False}
            if variant == "strict" and not args.no_save_frames:
                sub = "bist30" if is_stock else ""
                d = os.path.join(SIG_DIR, sub) if sub else SIG_DIR
                os.makedirs(d, exist_ok=True)
                out.to_parquet(os.path.join(d, f"{key}_{tf}_signals.parquet"), index=False)
        s = per["variants"]["strict"]
        c = per["variants"]["cooldown_only"]
        print(f"  [{key:6s}] bar={per['bars']:6d} ham_long={s['long_raw_signals']:4d} | "
              f"STRICT={s['long_signals']:4d} (short {s['short_signals']:3d}) "
              f"pos%={s['position_open_frac'] * 100:5.1f} supp={s['long_suppressed_by_position']:4d} | "
              f"CAPPED={per['variants']['capped']['long_signals']:4d} | "
              f"COOLDOWN_ONLY={c['long_signals']:4d} supp_cool={c['long_suppressed_by_cooldown']:4d} "
              f"min_gap={c['min_signal_gap_bars']}")
        results[key] = per

    payload = {
        "generated_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
        "timeframe": tf,
        "policy": {
            "trigger": f"LONG: close > max(high[t-{DEFAULT_LEVELS.donchian_period}..t-1]); "
                       f"SHORT (yalnız core): close < min(low[t-{DEFAULT_LEVELS.donchian_period}..t-1])",
            "shift_note": "donchian_high ZATEN shift(1) içerir; bu yüzden tetikte İKİNCİ bir "
                          "shift YOKTUR (olsaydı pencere 21 bara çıkardı). Eşdeğerlik "
                          "test_trigger_equals_manual_20_bar_breakout ile kilitli.",
            "chain_long": [c for _, c in LONG_CHAIN_V2],
            "chain_short": [c for _, c in SHORT_CHAIN_V2],
            "extra_link": "stop_valid — fail-closed EK halka (dondurulmuş stop yoksa işlem yok). "
                          "Şartname listesinde açıkça yoktu; require_valid_stop=False ile kapatılabilir.",
            "execution": "sinyal bar t KAPANIŞINDA; giriş bar t+1 AÇILIŞINDA. "
                         "signal_bar_close P&L'de KULLANILMAZ. t+1 yoksa execution_valid=False.",
            "cooldown_bars": args.cooldown_bars,
            "cooldown_semantics": "sinyal barı s ise ilk yeniden sinyal (s+1)+cooldown_bars = s+4 "
                                  "(12 saat). test_cooldown_off_by_one_is_exactly_as_documented.",
            "max_position_bars_capped_variant": args.max_position_bars,
            "position_exit_proxy": "frozen_stop_intrabar (VEKİL — Aşama 6/7'de gerçek motor)",
            "stock_allow_short": STOCK_ALLOW_SHORT,
            "new_indicators_added": [],
        },
        "assets": results,
    }
    with open(os.path.join(args.out, "signal_report.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    md = _markdown(payload)
    with open(os.path.join(args.out, "signal_report.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"\nraporlar: {os.path.join(args.out, 'signal_report.md')} · signal_report.json")
    return 0


def _markdown(p: Dict[str, Any]) -> str:
    pol = p["policy"]
    L: List[str] = []
    L.append("# AŞAMA 5 — Giriş Tetiği ve Sinyal Montajı Raporu")
    L.append("")
    L.append(f"*Üretim: {p['generated_at_utc'][:19]} UTC* · timeframe **{p['timeframe']}** · "
             f"cooldown **{pol['cooldown_bars']} bar (12 saat)**")
    L.append("")
    L.append("## 1) TETİK — yeni indikatör YOK")
    L.append("")
    L.append("```")
    L.append(pol["trigger"])
    L.append("```")
    L.append("")
    L.append(f"> {pol['shift_note']}")
    L.append("")
    L.append("## 2) SİNYAL ZİNCİRİ")
    L.append("")
    L.append("```")
    L.append("long  = " + " ∧ ".join(pol["chain_long"]))
    L.append("short = " + " ∧ ".join(pol["chain_short"]) + "    (yalnız CORE)")
    L.append("```")
    L.append("")
    L.append(f"> **{pol['extra_link']}**")
    L.append("> Bir kapı kolonu frame'de YOKSA sonuç **False**'tur (fail-closed), "
             "sessizce 'geçti' sayılmaz.")
    L.append("")
    L.append("## 3) İCRA ZAMANI — KRİTİK")
    L.append("")
    L.append(f"> {pol['execution']}")
    L.append("")
    L.append("## 4) COOLDOWN ve POZİSYON BASKILAMASI")
    L.append("")
    L.append(f"- **Cooldown sözleşmesi:** {pol['cooldown_semantics']}")
    L.append(f"- **Pozisyon açıkken yeni sinyal YOK.** Pozisyon vekili: `{pol['position_exit_proxy']}` "
             f"— {pol['position_exit_proxy'].split('(')[-1]}")
    L.append("")
    L.append("### ⚠️ ANA BULGU: pozisyon vekili sinyalleri AÇLIKTAN ÖLDÜRÜYOR")
    L.append("")
    L.append("Yapısal stop girişten ~2,6–3,2 ATR geride olduğu için fiyat onu **yıllarca** "
             "ihlal etmeyebiliyor. Vekil çıkış yalnızca stop ihlali olduğu için pozisyon "
             "neredeyse hep açık kalıyor ve ham sinyallerin büyük bölümü bastırılıyor "
             "(BTC: 592 ham → 3 final, pozisyon açıklık oranı %96).")
    L.append("")
    L.append("**Bu bir kod hatası DEĞİL.** Aşama 3'ün dürüst yorumunda öngörülen \"yapısal "
             "stop geniş\" sonucunun doğrudan ölçümüdür ve **Aşama 7'nin (partial + runner, "
             "trailing, time-stop) neden zorunlu olduğunu kanıtlar**. Aşama 6/7'de gerçek "
             "çıkış motoru geldiğinde bu tablo yeniden üretilecektir. Bu yüzden rapor ÜÇ "
             "akışı birlikte verir:")
    L.append("")
    L.append("| Akış | Tanım | Ne için |")
    L.append("|---|---|---|")
    L.append("| **A) strict** | şartnamedeki kural: pozisyon açıkken sinyal yok + cooldown | asıl kural; sonuç GEÇİCİ (vekile bağlı) |")
    L.append(f"| **B) capped** | A + zorunlu time-stop ({pol['max_position_bars_capped_variant']} bar) | vekilin ne kadar bağlayıcı olduğunu gösterir |")
    L.append("| **C) cooldown_only** | pozisyon takibi yok, yalnız cooldown | **cooldown kuralının kendi etkisini** izole eder |")
    L.append("")
    L.append("## 5) VARLIK BAŞINA SİNYAL SAYILARI")
    L.append("")
    L.append("| Varlık | rol | bar | ham long | **A strict** long | A short | A poz açık % | A bastırılan(poz) | **B capped** long | **C cooldown** long | C bastırılan(cooldown) | C min aralık (bar) |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, r in p["assets"].items():
        if "error" in r:
            L.append(f"| **{name}** | — | — | — | — | — | — | — | — | — | — | VERİ YOK |")
            continue
        v = r["variants"]
        a_, b_, c_ = v["strict"], v["capped"], v["cooldown_only"]
        L.append(f"| **{name}** | {r.get('role', '')} | {r['bars']} | {a_['long_raw_signals']} | "
                 f"**{a_['long_signals']}** | {a_['short_signals']} | "
                 f"%{a_['position_open_frac'] * 100:.1f} | {a_['long_suppressed_by_position']} | "
                 f"**{b_['long_signals']}** | **{c_['long_signals']}** | "
                 f"{c_['long_suppressed_by_cooldown']} | {c_['min_signal_gap_bars'] or '—'} |")
    L.append("")
    L.append("## 6) YILLARA GÖRE DAĞILIM ve ORTALAMA SİNYALLER ARASI SÜRE")
    L.append("")
    L.append("Kabul kriteri 5. `strict` akışı vekile bağımlı olduğu için **capped** ve "
             "**cooldown_only** akışlarının dağılımı da verilir.")
    L.append("")
    for variant in VARIANTS:
        L.append(f"### Akış {variant.upper()} — LONG")
        L.append("")
        years: List[int] = []
        for r in p["assets"].values():
            years += list((r.get("variants", {}).get(variant, {}) or {}).get("long_by_year", {}).keys())
        years = sorted(set(years))
        if not years:
            L.append("_(sinyal yok)_")
            L.append("")
            continue
        L.append("| Varlık | " + " | ".join(str(y) for y in years) +
                 " | TOPLAM | ort. aralık (gün) | medyan (gün) | min (gün) | sinyal/yıl |")
        L.append("|---|" + "---:|" * (len(years) + 6))
        for name, r in p["assets"].items():
            if "error" in r:
                continue
            st = r["variants"][variant]
            by = st.get("long_by_year", {}) or {}
            row = " | ".join(str(by.get(y, 0) or "") for y in years)
            L.append(f"| **{name}** | {row} | {st.get('long_signals', 0)} | "
                     f"{st.get('long_mean_gap_days') if st.get('long_mean_gap_days') is not None else '—'} | "
                     f"{st.get('long_median_gap_days') if st.get('long_median_gap_days') is not None else '—'} | "
                     f"{st.get('long_min_gap_days') if st.get('long_min_gap_days') is not None else '—'} | "
                     f"{st.get('long_signals_per_year') if st.get('long_signals_per_year') is not None else '—'} |")
        L.append("")
    L.append("## 7) ZİNCİR HALKALARI (strict akışı)")
    L.append("")
    L.append("| Varlık | " + " | ".join(lbl for lbl, _ in LONG_CHAIN_V2) + " |")
    L.append("|---|" + "---:|" * len(LONG_CHAIN_V2))
    for name, r in p["assets"].items():
        if "error" in r:
            continue
        cc = r.get("chain_long", {}) or {}
        L.append(f"| **{name}** | " + " | ".join(
            "—" if cc.get(lbl) is None else str(cc.get(lbl, "—")) for lbl, _ in LONG_CHAIN_V2) + " |")
    L.append("")
    L.append("## 8) UYGULANAMAYAN SİNYALLER")
    L.append("")
    L.append("| Varlık | strict long sinyali | uygulanabilir | **uygulanamaz** | sebep |")
    L.append("|---|---:|---:|---:|---|")
    for name, r in p["assets"].items():
        if "error" in r:
            continue
        st = r["variants"]["strict"]
        why = "serinin son barında sinyal var ama t+1 bar YOK" if st.get("long_unexecutable") else "—"
        L.append(f"| **{name}** | {st.get('long_signals', 0)} | {st.get('long_executable', 0)} | "
                 f"**{st.get('long_unexecutable', 0)}** | {why} |")
    L.append("")
    L.append("## ZORUNLU CAVEAT'LER")
    L.append("")
    L.append("- Bu tablodaki sinyal SAYILARI **GEÇİCİDİR**: pozisyon vekiline (yalnız stop "
             "ihlali) bağlıdır. Aşama 6/7'de gerçek çıkış motoru (TP, partial+runner, "
             "trailing, time-stop) geldiğinde yeniden üretilecektir.")
    L.append("- Sinyal sayısı bir **başarı ölçüsü DEĞİLDİR**. Az sinyal = az yanlış sinyal "
             "değildir; precision/recall/F1 ve expectancy ölçümü Aşama 5'in kalan işi ve "
             "Aşama 6'nın konusudur.")
    L.append("- `n=10`, `m=1.0`, `cooldown=3`, `Donchian=20` **VARSAYILANDIR**, optimize "
             "EDİLMEMİŞTİR. Seçim Aşama 9'da, yalnızca core varlıklar üzerinde.")
    L.append("- BIST30 sepeti **survivorship bias** taşır; sinyal sayıları da bu çarpık "
             "örnekleme aittir.")
    L.append("- XU030 satırı **bağlam kaynağıdır**; trade edilmez, sinyali portföye yazılmaz.")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
