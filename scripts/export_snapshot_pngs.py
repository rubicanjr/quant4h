"""EKİM MAINT(2): PNG snapshot — equity eğrileri + cadence şablon örneği.

Çıktılar (deterministik; zaman damgası YOK): reports/snapshot/
  - equity_<ASSET>.png  : trades_<ASSET>.csv'den (start equity + kümülatif net)
  - cadence_template_example.png : ops_runbook §A aylık şablon iskeleti

Kullanım:
    .venv/bin/python scripts/export_snapshot_pngs.py [--out reports/snapshot]
Hüküm/parametre DEĞİŞTİRMEZ; yalnızca görsel snapshot üretir.
"""
from __future__ import annotations

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
import pandas as pd                                              # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ASSETS = ("GOLD", "SILVER", "BTC", "BIST30")
START_EQ = 100_000.0

TEMPLATE = (
    "AYLIK İZLEME RAPORU — <YYYY-AA> (v1.0)\n"
    "========================================\n"
    "1) Veri/QC durumu: fetch YOK (pasif) · QC RED mi?\n"
    "2) Kadans: BIST 14:00/18:00 · core 03/07/11/15/19/23 (UTC+3)\n"
    "   son raporlar + QC bayrağı (RED → ⛔ SORUN NOTU, exit 3)\n"
    "3) Sinyaller: yeni sinyal var/yok (watch_only — emir YOK)\n"
    "4) Risk metrikleri (M13): max ardışık kayıp · uyma oranı\n"
    "5) Look bütçesi: kalan look · sıradaki pencere (≥2026-12-17)\n"
    "6) Sapma/olaylar: protokol ihlali, veri anomalisi\n"
    "7) Karar: izleme devam / aksiyon önerisi YOK (hüküm değişmez)\n"
)


def equity_png(asset: str, out_dir: str) -> str:
    fname = ("trades_bist30_basket.csv" if asset == "BIST30"
             else f"trades_{asset}.csv")
    p = os.path.join(ROOT, "reports", fname)
    df = pd.read_csv(p)
    eq = START_EQ + df["net_pnl"].cumsum()
    fig, ax = plt.subplots(figsize=(9, 4), dpi=110)
    ax.plot(range(len(eq)), eq.values, lw=1.1, color="#1f77b4")
    ax.axhline(START_EQ, color="#888", lw=0.6, ls="--")
    ax.set_title(f"quant4h — equity (capped, 1R=1%) · {asset}", fontsize=10)
    ax.set_xlabel("trade #", fontsize=8)
    ax.set_ylabel("equity", fontsize=8)
    ax.grid(alpha=0.25, lw=0.5)
    fig.tight_layout()
    out = os.path.join(out_dir, f"equity_{asset}.png")
    fig.savefig(out)
    plt.close(fig)
    return out


def cadence_png(out_dir: str) -> str:
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=110)
    ax.axis("off")
    ax.text(0.01, 0.99, TEMPLATE, va="top", ha="left", family="monospace",
            fontsize=9.5)
    ax.set_title("Cadence/§A şablon örneği (snapshot)", fontsize=10, loc="left")
    fig.tight_layout()
    out = os.path.join(out_dir, "cadence_template_example.png")
    fig.savefig(out)
    plt.close(fig)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "reports", "snapshot"))
    args = ap.parse_args(argv)
    out_dir = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(out_dir, exist_ok=True)
    made = [equity_png(a, out_dir) for a in ASSETS] + [cadence_png(out_dir)]
    for m in made:
        print(f"  [png] {os.path.relpath(m, ROOT)} ({os.path.getsize(m)} B)")
    print(f"snapshot: {len(made)} PNG → {os.path.relpath(out_dir, ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
