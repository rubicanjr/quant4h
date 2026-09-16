#!/usr/bin/env python3
"""
AŞAMA 2 + 3 raporu — yapısal seviyeler, yapısal stop mesafeleri ve olay sayıları.

    python3 scripts/run_levels_report.py

Kapsam:
  * core varlıklar : BTC · GOLD · SILVER   (long + short)
  * bağlam endeksi : XU030                (trade yok; yalnızca filtre kaynağı)
  * hisse sepeti   : Aşama 1.5'te sepete giren 28 hisse (LONG-ONLY)

Her varlık için:
  * anchor uygunluğu (return_valid / non_tradable / halt bayrakları sonrası)
  * onaylı swing sayısı (k-bar fraktal, k+1 bar gecikmeli onay)
  * Donchian(20) kullanılabilirlik oranı
  * breakout ve seviye teması sayıları
  * **stop mesafesi**: medyan ATR katı + fiyatın %'si (long ve short ayrı)

Çıktılar:
  reports/levels_report.md · reports/levels_report.json
  data/processed/levels/<KEY>_4h_levels.parquet
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

from quant4h.config import (DEFAULT_LEVELS, DEFAULT_REGIME, PARAM_TUNING_STAGE,  # noqa: E402
                            PARAM_TUNING_UNIVERSE, PER_ASSET_IN_SAMPLE_TUNING_ALLOWED,
                            STOCK_ALLOW_SHORT, UTC, bist_stock_specs)
from quant4h.features.context import context_summary, longs_allowed  # noqa: E402
from quant4h.features.levels import add_levels, count_events, plan_stop  # noqa: E402
from quant4h.features.regime import label_regime, regime_distribution  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(ROOT, "data", "processed", "levels")


def _load(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    side = path.replace(".parquet", ".attrs.json")
    if os.path.exists(side):
        with open(side, "r", encoding="utf-8") as fh:
            df.attrs.update(json.load(fh))
    return df


def _core(key: str, tf: str) -> Optional[pd.DataFrame]:
    for p in (os.path.join(ROOT, "data", "processed", f"{key.lower()}_{tf}_adjusted.parquet"),
              os.path.join(ROOT, "data", "interim", f"{key.lower()}_{tf}.parquet")):
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


def _included(report: str) -> List[str]:
    if not os.path.exists(report):
        return []
    with open(report, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return sorted(r["code"] for r in doc.get("stocks", []) if r.get("status") == "INCLUDED")


def _plan_stop_rate(df: pd.DataFrame, direction: str, allow_short: bool) -> Dict[str, Any]:
    """Kaç barda GERÇEKTEN dondurulmuş bir stop planlanabiliyor (fail-closed ölçüsü)."""
    ok = 0
    mults: List[float] = []
    col = f"stop_valid_{direction}"
    if col not in df.columns:
        return {"plannable_bars": 0, "plannable_frac": 0.0}
    idx = np.flatnonzero(df[col].astype(bool).to_numpy())
    for i in idx:
        st = plan_stop(df.iloc[i], direction, DEFAULT_LEVELS, allow_short=allow_short)
        if st is not None:
            ok += 1
            if np.isfinite(st.stop_atr_multiple):
                mults.append(st.stop_atr_multiple)
    return {"plannable_bars": ok,
            "plannable_frac": round(ok / len(df), 4) if len(df) else 0.0,
            "median_planned_atr_mult": round(float(np.median(mults)), 3) if mults else None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    ap.add_argument("--buffer-atr", type=float, default=DEFAULT_LEVELS.stop_buffer_atr,
                    help=f"VARSAYILAN {DEFAULT_LEVELS.stop_buffer_atr}; aday küme "
                         f"{DEFAULT_LEVELS.stop_buffer_candidates} Aşama {PARAM_TUNING_STAGE}'da")
    ap.add_argument("--no-save-frames", action="store_true")
    args = ap.parse_args()
    tf, cfg = args.timeframe, DEFAULT_LEVELS
    os.makedirs(args.out, exist_ok=True)
    if not args.no_save_frames:
        os.makedirs(OUT_DIR, exist_ok=True)

    index_4h = _core("BIST30", tf)
    if index_4h is None:
        print("!! XU030 bağlam verisi yok")
        return 1

    core: Dict[str, Any] = {}
    ctx: Dict[str, Any] = {}
    stocks: Dict[str, Any] = {}

    print("=== CORE + bağlam (long+short) ===")
    for key in ("BTC", "GOLD", "SILVER", "BIST30"):
        df = _core(key, tf)
        if df is None:
            print(f"  [{key}] veri yok")
            continue
        out = label_regime(df)
        out = add_levels(out, cfg, allow_short=True, buffer_atr=args.buffer_atr)
        ev = count_events(out, cfg)
        ev["regime"] = regime_distribution(out)
        ev["plan_long"] = _plan_stop_rate(out, "long", True)
        ev["plan_short"] = _plan_stop_rate(out, "short", True)
        ev["role"] = "context_filter_source" if key == "BIST30" else "core_tradable"
        (ctx if key == "BIST30" else core)[key] = ev
        if not args.no_save_frames:
            out.to_parquet(os.path.join(OUT_DIR, f"{key}_{tf}_levels.parquet"), index=False)
        sd = ev["stop_distance"].get("long", {})
        print(f"  [{key:7s}] bar={ev['bars']:6d} anchor_ok=%{ev['anchor_ok_frac'] * 100:5.1f} "
              f"swing={ev['swing_low_confirmed']:4d}/{ev['swing_high_confirmed']:4d} "
              f"donchian=%{ev['donchian_available_frac'] * 100:5.1f} "
              f"bo_up={ev['breakout_up']:4d} bo_dn={ev['breakout_down']:4d} "
              f"stop_long={sd.get('median_atr_mult')} ATR / %{sd.get('median_pct_price')}")

    codes = _included(os.path.join(ROOT, "reports", "bist30_universe_qc.json"))
    specs = bist_stock_specs()
    print(f"\n=== BIST30 hisse sepeti ({len(codes)} hisse, LONG-ONLY) ===")
    for code in codes:
        df = _stock(code, tf)
        if df is None:
            stocks[code] = {"error": "veri yok"}
            print(f"  [{code:6s}] veri yok")
            continue
        out = label_regime(df)
        # KARAR 4: hisseler LONG-ONLY -> short stop HİÇ üretilmez
        out = add_levels(out, cfg, allow_short=STOCK_ALLOW_SHORT, buffer_atr=args.buffer_atr)
        out = longs_allowed(out, index_4h, tf, DEFAULT_REGIME.ema_trend_period)
        trad = (~pd.to_numeric(out["non_tradable"], errors="coerce").fillna(False).astype(bool)
                if "non_tradable" in out.columns else pd.Series(True, index=out.index))
        ret_ok = (out["return_valid"].astype(bool) if "return_valid" in out.columns
                  else pd.Series(True, index=out.index))
        out["long_final_ok"] = (out["long_regime_ok"] & out["longs_allowed"] & trad & ret_ok
                                & out["stop_valid_long"].astype(bool))
        ev = count_events(out, cfg)
        ev["regime"] = regime_distribution(out)
        ev["context"] = context_summary(out)
        ev["plan_long"] = _plan_stop_rate(out, "long", False)
        ev["long_final_ok_bars"] = int(out["long_final_ok"].sum())
        ev["long_final_ok_frac"] = round(float(out["long_final_ok"].mean()), 4)
        ev["sector"] = (specs.get(f"BIST_{code}").extras.get("sector", "")
                        if specs.get(f"BIST_{code}") else "")
        ev["short_produced"] = bool(out["stop_short"].notna().any())
        stocks[code] = ev
        if not args.no_save_frames:
            out.to_parquet(os.path.join(OUT_DIR, f"{code}_{tf}_levels.parquet"), index=False)
        sd = ev["stop_distance"].get("long", {})
        print(f"  [{code:6s}] bar={ev['bars']:5d} anchor_ok=%{ev['anchor_ok_frac'] * 100:5.1f} "
              f"swing_lo={ev['swing_low_confirmed']:4d} donchian=%{ev['donchian_available_frac'] * 100:5.1f} "
              f"bo_up={ev['breakout_up']:3d} touch_sl={ev['touch_last_swing_low']:4d} "
              f"stop={sd.get('median_atr_mult')} ATR / %{sd.get('median_pct_price')} "
              f"FINAL_long={ev['long_final_ok_bars']:4d} short_uretildi={ev['short_produced']}")

    payload = {
        "generated_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
        "timeframe": tf,
        "levels_policy": {
            "swing_k": cfg.swing_k,
            "swing_confirmation_delay_bars": cfg.swing_k + 1,
            "swing_lookback": cfg.swing_lookback,
            "donchian_period": cfg.donchian_period,
            "donchian_uses_closed_bars_only": True,
            "stop_buffer_atr": args.buffer_atr,
            "stop_buffer_candidates_stage": PARAM_TUNING_STAGE,
            "stop_buffer_candidates": list(cfg.stop_buffer_candidates),
            "selection_now": False,
            "min_valid_frac_in_window": cfg.min_valid_frac_in_window,
            "anchor_excludes": ["return_valid==False", "non_tradable==True",
                                "halt_or_limit_flag==True", "OHLC NaN veya <=0"],
            "stop_frozen": True,
            "per_asset_in_sample_tuning_allowed": PER_ASSET_IN_SAMPLE_TUNING_ALLOWED,
            "param_tuning_universe": list(PARAM_TUNING_UNIVERSE),
            "stock_allow_short": STOCK_ALLOW_SHORT,
            "new_indicators_added": [],
            "chart_elements": ["candles", "EMA200", "structural_stop/target"],
        },
        "core_assets": core,
        "context_source": ctx,
        "stocks": stocks,
    }
    with open(os.path.join(args.out, "levels_report.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    md = _markdown(payload)
    with open(os.path.join(args.out, "levels_report.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"\nraporlar: {os.path.join(args.out, 'levels_report.md')} · levels_report.json")
    return 0


def _fmt(v: Any, nd: int = 2) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    return str(v)


def _markdown(p: Dict[str, Any]) -> str:
    pol = p["levels_policy"]
    L: List[str] = []
    L.append("# AŞAMA 3 — Yapısal Seviyeler ve Yapısal Stop Raporu")
    L.append("")
    L.append(f"*Üretim: {p['generated_at_utc'][:19]} UTC* · timeframe **{p['timeframe']}** · "
             f"buffer **{pol['stop_buffer_atr']} ATR** (varsayılan)")
    L.append("")
    L.append("## POLİTİKA")
    L.append("")
    L.append(f"- **Swing:** {pol['swing_k']}-bar fraktal. Onay gecikmesi **{pol['swing_confirmation_delay_bars']} bar** "
             f"(p konumlu swing ancak `p+k` barı KAPANDIĞINDA görünür). Lookback {pol['swing_lookback']} bar.")
    L.append(f"- **Donchian({pol['donchian_period']}):** son {pol['donchian_period']} **KAPANMIŞ** bar "
             f"(`shift(1)`); mevcut bar pencereye GİRMEZ. Pencere geçerlilik oranı "
             f"< {pol['min_valid_frac_in_window']} ise seviye **NaN** (fail-closed).")
    L.append(f"- **Anchor kısıtı:** `{', '.join(pol['anchor_excludes'])}` → bu barlar ne swing ne "
             f"Donchian anchor'ı olabilir. **FLAG-ONLY**: veri silinmez, sadece seviye üretimine katılmaz.")
    L.append(f"- **Yapısal stop:** long = onaylı `swing_low − {pol['stop_buffer_atr']}×ATR`; "
             f"short (yalnız core) = onaylı `swing_high + {pol['stop_buffer_atr']}×ATR`. "
             f"Stop **girişten önce** belli ve **DONDURULMUŞ** (`FrozenStop`; "
             f"`widen/move_against/relax` → `StopImmutabilityError`).")
    L.append(f"- **Buffer seçimi YOK:** aday küme `{pol['stop_buffer_candidates']}` yalnızca "
             f"**Aşama {pol['stop_buffer_candidates_stage']}**'da test edilir. "
             f"`selection_now={pol['selection_now']}`")
    L.append(f"- **Hisse başına in-sample parametre seçimi:** "
             f"`{pol['per_asset_in_sample_tuning_allowed']}` (YASAK). Parametre seçimi Aşama "
             f"{pol['param_tuning_universe']} üzerinde, Aşama {pol['stop_buffer_candidates_stage']}'da.")
    L.append(f"- **Hisselerde short:** `{pol['stock_allow_short']}` (LONG-ONLY, KARAR 4).")
    L.append(f"- **Yeni indikatör:** {pol['new_indicators_added'] or 'YOK'} · "
             f"grafik öğeleri: `{pol['chart_elements']}` (maks 3).")
    L.append("")
    L.append("## ZORUNLU NOT (PROGRESS'e işlendi)")
    L.append("")
    L.append("> BIST30 hisselerinde **warmup** nedeniyle TRAIN döneminde etiketli bar sayısı "
             "azdır. Bu yüzden **hiçbir aşamada hisse başına in-sample parametre seçimi "
             "YAPILMAYACAK**. Parametre seçimi Aşama 9'da, küçük bir aday kümesiyle ve yalnızca "
             "**core varlıklar** (BTC / GOLD / SILVER) üzerinde yapılacak; hisseler **yalnızca "
             "OOS** raporlanacak. Bu kural `config.PER_ASSET_IN_SAMPLE_TUNING_ALLOWED=False` "
             "ile kod düzeyinde kilitlidir.")
    L.append("")
    L.append("## CORE VARLIKLAR + BAĞLAM ENDEKSİ")
    L.append("")
    L.append("| Varlık | rol | bar | anchor_ok % | swing_low | swing_high | Donchian % | "
             "breakout ↑ | breakout ↓ | temas Donch ↑ | temas Donch ↓ | temas swing_low | "
             "stop_long (ATR) | stop_long (% fiyat) | stop_short (ATR) | planlanabilir long % |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    rows = list(p["core_assets"].items()) + list(p["context_source"].items())
    for name, e in rows:
        sd = e.get("stop_distance", {})
        lo, sh = sd.get("long", {}), sd.get("short", {})
        L.append(f"| **{name}** | {e.get('role', '')} | {e.get('bars', 0)} | "
                 f"{_fmt((e.get('anchor_ok_frac') or 0) * 100, 1)} | {e.get('swing_low_confirmed', 0)} | "
                 f"{e.get('swing_high_confirmed', 0)} | "
                 f"{_fmt((e.get('donchian_available_frac') or 0) * 100, 1)} | "
                 f"{e.get('breakout_up', 0)} | {e.get('breakout_down', 0)} | "
                 f"{e.get('touch_donchian_high', 0)} | {e.get('touch_donchian_low', 0)} | "
                 f"{e.get('touch_last_swing_low', 0)} | "
                 f"{_fmt(lo.get('median_atr_mult'))} | {_fmt(lo.get('median_pct_price'))} | "
                 f"{_fmt(sh.get('median_atr_mult'))} | "
                 f"{_fmt((e.get('plan_long', {}) or {}).get('plannable_frac', 0) * 100, 1)} |")
    L.append("")
    L.append("## BIST30 HİSSE SEPETİ — STOP MESAFESİ VE OLAY SAYILARI")
    L.append("")
    L.append("| Hisse | sektör | bar | anchor_ok % | swing_low | swing_high | Donchian % | "
             "breakout ↑ | temas swing_low | swing_low kapanış-altı | **stop_long (ATR)** | "
             "**stop_long (% fiyat)** | planlanabilir % | FINAL long | short üretildi |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    agg: Dict[str, List[float]] = {"atr": [], "pct": [], "bo": [], "final": [], "anchor": [],
                                   "donch": [], "plan": []}
    for code, e in p["stocks"].items():
        if "error" in e:
            L.append(f"| **{code}** | — | — | — | — | — | — | — | — | — | — | — | — | — | VERİ YOK |")
            continue
        sd = e.get("stop_distance", {}).get("long", {})
        atr_m, pct_p = sd.get("median_atr_mult"), sd.get("median_pct_price")
        L.append(f"| **{code}** | {e.get('sector', '')} | {e.get('bars', 0)} | "
                 f"{_fmt((e.get('anchor_ok_frac') or 0) * 100, 1)} | {e.get('swing_low_confirmed', 0)} | "
                 f"{e.get('swing_high_confirmed', 0)} | "
                 f"{_fmt((e.get('donchian_available_frac') or 0) * 100, 1)} | {e.get('breakout_up', 0)} | "
                 f"{e.get('touch_last_swing_low', 0)} | {e.get('close_below_swing_low', 0)} | "
                 f"**{_fmt(atr_m)}** | **{_fmt(pct_p)}** | "
                 f"{_fmt((e.get('plan_long', {}) or {}).get('plannable_frac', 0) * 100, 1)} | "
                 f"{e.get('long_final_ok_bars', 0)} ({_fmt(e.get('long_final_ok_frac', 0) * 100, 1)}%) | "
                 f"{'❌ ÜRETİLDİ!' if e.get('short_produced') else '✅ hayır'} |")
        if atr_m is not None:
            agg["atr"].append(float(atr_m))
        if pct_p is not None:
            agg["pct"].append(float(pct_p))
        agg["bo"].append(float(e.get("breakout_up", 0)))
        agg["final"].append(float(e.get("long_final_ok_frac", 0)))
        agg["anchor"].append(float(e.get("anchor_ok_frac") or 0))
        agg["donch"].append(float(e.get("donchian_available_frac") or 0))
        agg["plan"].append(float((e.get("plan_long", {}) or {}).get("plannable_frac", 0)))
    if agg["atr"]:
        L.append(f"| **MEDYAN (28 hisse)** | | | {_fmt(np.median(agg['anchor']) * 100, 1)} | | | "
                 f"{_fmt(np.median(agg['donch']) * 100, 1)} | {_fmt(np.median(agg['bo']), 0)} | | | "
                 f"**{_fmt(np.median(agg['atr']))}** | **{_fmt(np.median(agg['pct']))}** | "
                 f"{_fmt(np.median(agg['plan']) * 100, 1)} | {_fmt(np.median(agg['final']) * 100, 1)}% | ✅ |")
        L.append("")
        L.append(f"Stop mesafesi hisse bazında **{min(agg['atr']):.2f} – {max(agg['atr']):.2f} ATR** "
                 f"(medyan {np.median(agg['atr']):.2f}) ve **%{min(agg['pct']):.2f} – "
                 f"%{max(agg['pct']):.2f}** fiyat (medyan %{np.median(agg['pct']):.2f}) arasında.")
    L.append("")
    L.append("## DURDURMA MESAFESİNİN SONUÇLARI (yorum)")
    L.append("")
    L.append("- Eşit-risk politikasında pozisyon büyüklüğü = `risk_per_trade / stop_mesafesi`. "
             "Yani **geniş yapısal stop = küçük pozisyon**. Bu bir hata değil, tasarımın "
             "doğrudan sonucudur ve stop'un yapısal (swing) olması bedelidir.")
    L.append("- Medyan stop mesafesi ATR cinsinden 1'in çok üstündeyse (ör. 3 ATR) bunun iki "
             "sebebi olabilir: (a) son onaylı swing gerçekten uzakta, (b) `swing_lookback` çok "
             "geniş. **Aşama 7'de** alternatif anchor'lar (Donchian-low, daha yakın swing) ve "
             "partial+runner/trailing yöntemleri test edilecek; **şimdi seçim yapılmıyor**.")
    L.append("- `planlanabilir %` = stop'un gerçekten DONDURULABİLDİĞİ bar oranı. Düşükse "
             "fail-closed çalışıyor demektir: seviye bilinmiyorsa **işlem yok**.")
    L.append("")
    L.append("## FİNAL LONG İZNİNİN BİLEŞİMİ (hisseler)")
    L.append("")
    L.append("```")
    L.append("long_final_ok = long_regime_ok      # trend_up VE ATR yüzdeliği <= tavan   (Aşama 2)")
    L.append("              AND longs_allowed      # XU030 4H kapanış > EMA200, KAPANMIŞ bar (Aşama 2)")
    L.append("              AND NOT non_tradable   # kesinti / ince açılış barı / oluşuyor / kurumsal aksiyon")
    L.append("              AND return_valid       # boşluğu veya ex-date'i atlayan getiri DEĞİL")
    L.append("              AND stop_valid_long    # DONDURULABİLİR yapısal stop VAR  (Aşama 3)")
    L.append("```")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
