#!/usr/bin/env python3
"""
KARAR 2 & KARAR 3 driver: roll / data-outage adjustment.

    python3 scripts/run_adjust.py --assets BTC GOLD SILVER BIST30

Reads  data/interim/<asset>_4h.parquet   (produced by run_data_qc.py)
Writes data/processed/<asset>_4h_adjusted.parquet
       data/processed/<asset>_4h_adjusted.attrs.json   (parquet drops .attrs)
       reports/adjust_evidence.md

Hard rules enforced here (and pinned by tests/test_adjust.py):
  * no bar is deleted, no bar is fabricated  -> rows_in == rows_out
  * the outage window is MARKED non-tradable, never repaired
  * a return that jumps the outage is invalidated, never trusted
  * raw prices are preserved verbatim in close_raw
  * prices are NOT back-adjusted unless --apply-roll-correction is passed,
    because a roll cannot be told apart from a genuine extreme move without
    contract-month identity in the feed
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import pandas as pd  # noqa: E402

from quant4h.config import DEFAULT_ASSETS  # noqa: E402
from quant4h.data import schema  # noqa: E402
from quant4h.data.adjust import adjust_asset  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _attrs_path(asset: str) -> str:
    return os.path.join(ROOT, "data", "processed", f"{asset.lower()}_4h_adjusted.attrs.json")


def _frame_path(asset: str) -> str:
    return os.path.join(ROOT, "data", "processed", f"{asset.lower()}_4h_adjusted.parquet")


def load_adjusted(asset: str) -> pd.DataFrame | None:
    """Load the adjusted frame and re-attach its attrs (parquet drops them)."""
    fp, ap = _frame_path(asset), _attrs_path(asset)
    if not (os.path.exists(fp) and os.path.exists(ap)):
        return None
    df = schema.load_parquet(fp)
    with open(ap, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    for k, v in raw.items():
        df.attrs[k] = v
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets", nargs="*", default=list(DEFAULT_ASSETS))
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--roll-atr-multiple", type=float, default=3.0)
    ap.add_argument("--apply-roll-correction", action="store_true",
                    help="back-adjust prices at flagged rolls (default: FLAG ONLY)")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    args = ap.parse_args()

    os.makedirs(os.path.join(ROOT, "data", "processed"), exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    evidence: List[Dict[str, Any]] = []
    for key in args.assets:
        if key not in DEFAULT_ASSETS:
            print(f"!! unknown asset {key}")
            continue
        spec = DEFAULT_ASSETS[key]
        interim = os.path.join(ROOT, "data", "interim", f"{key.lower()}_{args.timeframe}.parquet")
        if not os.path.exists(interim):
            print(f"!! {key}: {interim} yok - once run_data_qc.py calistirin")
            continue
        before = schema.load_parquet(interim)
        adj, rep, log = adjust_asset(before, spec, args.timeframe,
                                     roll_atr_multiple=args.roll_atr_multiple,
                                     apply_roll_correction=args.apply_roll_correction,
                                     src_timeframe=spec.raw_timeframe)
        adj.to_parquet(_frame_path(key), index=False)
        with open(_attrs_path(key), "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in adj.attrs.items()}, fh, indent=2, default=str)
        print(f"[{key}] {rep.rows_in} -> {rep.rows_out} bar (silinen {rep.bars_deleted}, "
              f"eklenen {rep.bars_added}) | kesinti penceresi {len(rep.outage_windows)} | "
              f"non-tradable {rep.n_non_tradable} | gecersiz getiri {rep.n_return_invalid} | "
              f"buyuk hareket adayi {rep.n_roll_candidate} (duzeltilen {rep.n_roll_event})")
        evidence.append({"key": key, "spec_symbol": spec.symbol, "mode": spec.mode,
                         "requires_adjustment": spec.requires_adjustment,
                         "report": rep.to_dict(),
                         "log": log.to_dict(),
                         "before_rows": len(before), "after_rows": len(adj),
                         "raw_close_identical": bool(
                             (adj["close_raw"].to_numpy() == before["close"].to_numpy()).all()),
                         "timestamps_identical": bool(
                             list(adj["timestamp_utc"]) == list(before["timestamp_utc"]))})

    _write_evidence_md(evidence, args)
    print(f"\nKanit tablosu: {os.path.join(args.out, 'adjust_evidence.md')}")
    print("Simdi QC'yi yeniden calistirin: python3 scripts/run_data_qc.py")
    return 0


def build_evidence_md(evidence: List[Dict[str, Any]], apply_roll_correction: bool = False,
                      roll_atr_multiple: float = 3.0) -> str:
    """Kanit tablosunu markdown olarak uretir (hem CLI hem run_data_qc.py kullanir)."""
    L: List[str] = []
    L.append("# adjust.py Kanit Tablosu (KARAR 2 & KARAR 3)")
    L.append("")
    L.append(f"*Uretim: {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}* · "
             f"`apply_roll_correction={apply_roll_correction}` · "
             f"`roll_atr_multiple={roll_atr_multiple}`")
    L.append("")
    L.append("## 1) Degismezler (hard rules)")
    L.append("")
    L.append("| Varlik | bar once | bar sonra | SILINEN | EKLENEN | timestamp ayni | close_raw ayni |")
    L.append("|---|---:|---:|---:|---:|---|---|")
    for e in evidence:
        r = e["report"]
        L.append(f"| {e['key']} | {e['before_rows']} | {e['after_rows']} | "
                 f"**{r['bars_deleted']}** | **{r['bars_added']}** | "
                 f"{'EVET' if e['timestamps_identical'] else 'HAYIR'} | "
                 f"{'EVET' if e['raw_close_identical'] else 'HAYIR'} |")
    L.append("")
    L.append("> Bar silinmedi, bar uydurulmadi, ham fiyatlar bayt bayt ayni. "
             "Yalnizca **isaret** kolonlari eklendi.")
    L.append("")
    L.append("## 2) Kesinti / islem-disi isaretleme")
    L.append("")
    L.append("| Varlik | kesinti penceresi | pencere ici bar | devami gelen bar | ince bar | non-tradable TOPLAM | gecersiz getiri |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for e in evidence:
        r, a = e["report"], e["report"]["attrs"]
        L.append(f"| {e['key']} | {len(r['outage_windows'])} | {a.get('outage_window_bars', 0)} | "
                 f"{a.get('outage_resumption_bars', 0)} | {r['n_thin_non_tradable']} | "
                 f"**{r['n_non_tradable']}** | **{r['n_return_invalid']}** |")
    L.append("")
    L.append("## 3) Getiri duzeltmesi: once / sonra")
    L.append("")
    L.append("| Varlik | max\\|log getiri\\| HAM | max\\|log getiri\\| GECERLI | fark | yorum |")
    L.append("|---|---:|---:|---:|---|")
    for e in evidence:
        r = e["report"]
        diff = r["max_raw_abs_return"] - r["max_valid_abs_return"]
        note = ("sahte getiri seriye girmiyor" if diff > 1e-9
                else "ham seride de sahte getiri yok")
        L.append(f"| {e['key']} | {r['max_raw_abs_return']:.4f} | "
                 f"{r['max_valid_abs_return']:.4f} | {diff:+.4f} | {note} |")
    L.append("")
    L.append("## 4) Buyuk hareket siniflandirmasi (DURUST SINIR)")
    L.append("")
    L.append("| Varlik | requires_adjustment | aday | bad-print sezgisi | fiyati DUZELTILEN | close_adjusted |")
    L.append("|---|---|---:|---:|---:|---|")
    for e in evidence:
        r, a = e["report"], e["report"]["attrs"]
        L.append(f"| {e['key']} | {e['requires_adjustment']} | {r['n_roll_candidate']} | "
                 f"{a.get('bad_print_flagged_bars', 0)} | {r['n_roll_event']} | "
                 f"{'== close_raw' if not a.get('roll_correction_applied') else 'back-adjusted'} |")
    L.append("")
    L.append("> Yahoo on-ay serisinde **kontrat ayi kimligi yoktur**; bu yuzden bir roll ile "
             "gercek bir ekstrem hareket fiyattan KESIN olarak ayirt edilemez. Varsayilan "
             "politika bu yuzden **FLAG ONLY**'dir: fiyatlar duzeltilmez, adaylar insan "
             "incelemesine birakilir. Kalıcılık testi bad print'i ayirt ETMEZ (print sonrasi "
             "seviye kaymis gorunur); ayirt edici sezgi **hacim**dir ve bu da bir kanit "
             "degildir. Kesin cozum: kontrat ayi kimligi olan bir continuous future kaynagi.")
    L.append("")
    L.append("## 5) Tespit edilen kesinti pencereleri (ilk 8, varlik basina)")
    L.append("")
    for e in evidence:
        wins = e["report"]["outage_windows"]
        if not wins:
            continue
        L.append(f"**{e['key']}** — {len(wins)} pencere")
        L.append("")
        L.append("| onceki bar (UTC) | devam bari (UTC) | kayip saat | bosluk (bar) | tipik (bar) | boslugu atlayan getiri |")
        L.append("|---|---|---:|---:|---:|---:|")
        for w in sorted(wins, key=lambda x: -x["missing_hours"])[:8]:
            L.append(f"| {w['prev_bar_utc'][:16]} | {w['resumed_bar_utc'][:16]} | "
                     f"{w['missing_hours']:.0f} | {w['gap_bars']:.0f} | "
                     f"{w['modal_gap_bars']:.0f} | {w['return_across_gap_pct']:+.2f}% |")
        L.append("")
    L.append("## 6) KARAR 3 vakasi: SILVER 2026-02-02")
    L.append("")
    L.append("`tests/test_adjust.py::test_real_silver_2026_02_02_event_is_flagged_and_preserved` "
             "bu vakayi GERCEK veri uzerinden sabitler: bar SILINMEDI, `gap_anomaly=True`, "
             "`outage_resumption=True`, `non_tradable=True`, `return_valid=False`, "
             "`close_to_close_return=NaN`, `roll_candidate=False`. Yani ne roll ne bad print: "
             "**veri kesintisini atlayan sahte getiri.**")
    L.append("")
    return "\n".join(L)


def _write_evidence_md(evidence: List[Dict[str, Any]], args: argparse.Namespace) -> None:
    md = build_evidence_md(evidence, args.apply_roll_correction, args.roll_atr_multiple)
    path = os.path.join(args.out, "adjust_evidence.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(md)


if __name__ == "__main__":
    raise SystemExit(main())
