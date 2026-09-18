"""M9b — TradingView görselleştirme eki için PAYLOAD üretici (watch_only).

`pine/quant4h_viz.pine` YALNIZ bu script'in ihraç ettiği değerleri çizer;
Pine tarafında HİÇBİR şey yeniden hesaplanmaz (drift riski yok). Payload,
Python'daki TEK doğruluk kaynağından (capped akış, P0×A0, data/processed
frame'leri) üretilir.

Çıktı: `viz/payload_YYYY-MM.txt` — her varlık için PAYLOAD-BEGIN/END bloğu.
Kullanıcı ilgili bloğu kopyalayıp pine dosyasındaki boş payload bölgesiyle
değiştirir (TEST_PLAN.md adım 2-4).

Bu bir GÖRSELLEŞTİRME aracıdır: UNTESTED-VIZ (Pine derlemesi/paritesi otomatik
doğrulanmaz; TEST_PLAN.md manuel kontrol listesine bakın). Doğruluk kaynağı
DEĞİLDİR. strategy()/alert üretmez; icra (open[t+1]) temsil edilmez.

Çalıştırma:
    python3 -W ignore scripts/export_viz_payload.py                 # son barın ayı
    python3 -W ignore scripts/export_viz_payload.py --month 2026-09 --assets BTC GOLD
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))
sys.path.insert(0, _HERE)

import run_exit_grid as G  # noqa: E402  (_signals_for: capped P0xA0 frame'leri — TEK kaynak)

ROOT = G.ROOT
DEFAULT_ASSETS = ("BTC", "GOLD", "SILVER", "BIST30")
BEGIN = "// ---- PAYLOAD-BEGIN (export_viz_payload.py — otomatik; elle düzenlemeyin)"
END = "// ---- PAYLOAD-END"


def _pine_floats(vals) -> str:
    out = []
    for v in vals:
        try:
            f = float(v)
            out.append("na" if not np.isfinite(f) else f"{f:.2f}")
        except (TypeError, ValueError):
            out.append("na")
    return ", ".join(out)


def _pine_ints(vals) -> str:
    return ", ".join(str(int(v)) for v in vals)


def export_asset(key: str, tf: str, month_start: pd.Timestamp,
                 month_end: pd.Timestamp) -> Optional[str]:
    frame = G._signals_for(key, tf, False, None, "A0")     # BIST30 = endeks (tanısal)
    if frame is None or not len(frame):
        return None
    ts = pd.to_datetime(frame["timestamp_utc"], utc=True)
    m = (ts >= month_start) & (ts < month_end)
    d = frame.loc[m]
    if not len(d):
        return (f"{BEGIN}\n"
                f'payloadMeta = "{key} {month_start:%Y-%m}: pencere BOS (veri yok)"\n'
                f"payloadOK   = false\n{END}\n")
    tsd = pd.to_datetime(d["timestamp_utc"], utc=True)
    # epoch MİLİSANİYE (pine `time`): çözünürlükten bağımsız kesin hesap
    # (pandas 3.0 datetime64[us/ms] tuzaklarına karşı — M9b demo bulgusu).
    ms = ((tsd - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(milliseconds=1)).tolist()
    sig_l = d["long_signal"].astype(bool).astype(int).tolist()
    sig_s = d["short_signal"].astype(bool).astype(int).tolist() if "short_signal" in d else [0] * len(d)
    close = pd.to_numeric(d["close"], errors="coerce")
    sig_px = [ (float(c) if (sl or ss) and np.isfinite(c) else np.nan)
               for c, sl, ss in zip(close.tolist(), sig_l, sig_s) ]
    n_sig = sum(sig_l) + sum(sig_s)
    meta = (f"{key} · {month_start:%Y-%m} · {len(d)} bar · capped P0xA0 · "
            f"final sinyal: {n_sig} · son bar {str(tsd.iloc[-1])[:16]} UTC · "
            f"UNTESTED-VIZ — dogruluk kaynagi DEGIL")
    lines = [
        BEGIN,
        f'payloadMeta = "{meta}"',
        "payloadOK   = true",
        f"ts        = array.from<int>({_pine_ints(ms)})",
        f"ema200    = array.from<float>({_pine_floats(d.get('ema_trend'))})",
        f"stopLong  = array.from<float>({_pine_floats(d.get('stop_long'))})",
        f"swingLow  = array.from<float>({_pine_floats(d.get('last_swing_low'))})",
        f"swingHigh = array.from<float>({_pine_floats(d.get('last_swing_high'))})",
        f"donHigh   = array.from<float>({_pine_floats(d.get('donchian_high'))})",
        f"donLow    = array.from<float>({_pine_floats(d.get('donchian_low'))})",
        f"sigLong   = array.from<int>({_pine_ints(sig_l)})",
        f"sigShort  = array.from<int>({_pine_ints(sig_s)})",
        f"sigPrice  = array.from<float>({_pine_floats(sig_px)})",
        END,
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--month", default=None, help="YYYY-MM (varsayılan: BTC frame'inin son barının ayı)")
    ap.add_argument("--assets", nargs="*", default=list(DEFAULT_ASSETS))
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--out", default=os.path.join(ROOT, "viz"))
    args = ap.parse_args()

    if args.month:
        month_start = pd.Timestamp(f"{args.month}-01", tz="UTC")
    else:
        probe = G._signals_for("BTC", args.timeframe, False, None, "A0")
        last = pd.to_datetime(probe["timestamp_utc"], utc=True).max()
        month_start = pd.Timestamp(year=last.year, month=last.month, day=1, tz="UTC")
    month_end = (month_start + pd.offsets.MonthBegin(1))
    tag = f"{month_start:%Y-%m}"

    sections: List[str] = []
    header = [
        f"// quant4h viz payload — {tag} · üretim: {pd.Timestamp.utcnow().isoformat(timespec='seconds')}Z",
        "// AKIŞ: capped · hücre: P0xA0 (Aşama 9 kilidi) · kaynak: data/processed frame'leri",
        "// UNTESTED-VIZ — DOĞRULUK KAYNAĞI DEĞİLDİR (kaynak: repo raporları/parquet'leri).",
        "// KULLANIM: ilgili varlık bloğunu pine/quant4h_viz.pine PAYLOAD bölgesine yapıştırın.",
        "// watch_only: trade YOK · emir YOK · tavsiye YOK · icra open[t+1] burada gösterilmez.",
        "",
    ]
    ok = 0
    for key in args.assets:
        sec = export_asset(key, args.timeframe, month_start, month_end)
        if sec is None:
            print(f"  [{key}] frame yok — atlandı")
            continue
        sections.append(f"// ================= {key} =================\n{sec}")
        ok += 1
        print(f"  [{key}] payload üretildi")
    if not ok:
        print("HATA: hiçbir varlık için payload üretilemedi")
        return 1
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"payload_{tag}.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(header) + "\n" + "\n".join(sections))
    print(f"\nçıktı: {os.path.relpath(path, ROOT)} ({ok} varlık)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
