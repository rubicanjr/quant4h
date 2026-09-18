"""M9b/M9c — TradingView görselleştirme eki için PAYLOAD + HAZIR PINE üretici (watch_only).

`pine/quant4h_viz.pine` YALNIZ bu script'in ihraç ettiği değerleri çizer;
Pine tarafında HİÇBİR şey yeniden hesaplanmaz (drift riski yok). Payload,
Python'daki TEK doğruluk kaynağından (capped akış, P0×A0, data/processed
frame'leri) üretilir.

Çıktılar (`viz/`):
  * `quant4h_viz_<ASSET>_<YYYY-MM>.pine`  ← **KULLANIN BUNU**: şablon + payload
    GÖMÜLÜ TAM dosya. TradingView'da yeni indikatör sekmesi aç → dosyanın
    TÜMÜNÜ kopyala-yapıştır → kaydet → grafiğe ekle. Bölge ameliyatı YOK.
  * `payload_YYYY-MM.txt` — birleşik referans dökümü (4 varlık); DOĞRUDAN
    PINE'A YAPIŞTIRMAYIN (M9c vakası: txt başlık yorumları `payloadMeta =`
    satırına karışıp 'end of line without line continuation' hatası verdi;
    dört varlık bloğu birlikte yapıştırılınca duplicate-declaration hatası verdi).

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
import re
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
TEMPLATE = os.path.join(ROOT, "pine", "quant4h_viz.pine")
DECL_NAMES = ["ts", "ema200", "stopLong", "swingLow", "swingHigh", "donHigh",
              "donLow", "sigLong", "sigShort", "sigPrice", "payloadMeta", "payloadOK"]


def lint_pine(txt: str) -> None:
    """M9c yapısal lint: her payload tanımı TAM 1 kez; strategy()/alert() YASAK.
    Yasak-kelime taraması YALNIZ KOD satırlarında yapılır (yorumlar soyulur —
    H29/H33 deseni; şablonun kendi belge yorumları 'strategy() YOK' der)."""
    lines = txt.splitlines()
    for name in DECL_NAMES:
        n = sum(1 for l in lines if re.match(rf"^{re.escape(name)}\s*=", l))
        if n != 1:
            raise RuntimeError(f"pine lint HATA: '{name}' bildirim sayısı {n} (beklenen 1) — "
                               f"bölge birleştirme/paste hatası")
    code = [l for l in lines if not l.lstrip().startswith("//")]
    joined = "\n".join(code)
    if "strategy(" in joined or re.search(r"^\s*alert\(", joined, re.M) or "alertcondition(" in joined:
        raise RuntimeError("pine lint HATA: strategy()/alert()/alertcondition() YASAK (M9b sınırı)")


def assemble_pine(asset_block: str) -> str:
    """Şablonun boş payload bölgesini (BEGIN..END dahil) TEK varlık bloğuyla
    değiştirir → TradingView'a OLDUĞU GİBİ yapıştırılabilir TAM dosya (M9c)."""
    with open(TEMPLATE, encoding="utf-8") as fh:
        tpl = fh.read().splitlines()
    i0 = next(i for i, l in enumerate(tpl) if "PAYLOAD-BEGIN" in l)
    i1 = next(i for i, l in enumerate(tpl) if i > i0 and "PAYLOAD-END" in l)
    out = tpl[:i0] + asset_block.rstrip("\n").splitlines() + tpl[i1 + 1:]
    txt = "\n".join(out) + "\n"
    lint_pine(txt)
    return txt


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
        "// UYARI: BU TXT'YI PINE'A DOGRUDAN YAPISTIRMAYIN (M9c vakasi: baslik yorumlari",
        "//   `payloadMeta =` satirina karisir; cok-varlik bloklari duplicate-declaration verir).",
        f"//   HAZIR DOSYA: viz/quant4h_viz_<ASSET>_{tag}.pine -> TAMAMINI kopyala-yapistir.",
        "// AKIŞ: capped · hücre: P0xA0 (Aşama 9 kilidi) · kaynak: data/processed frame'leri",
        "// UNTESTED-VIZ — DOĞRULUK KAYNAĞI DEĞİLDİR (kaynak: repo raporları/parquet'leri).",
        "// watch_only: trade YOK · emir YOK · tavsiye YOK · icra open[t+1] burada gösterilmez.",
        "",
    ]
    ok = 0
    os.makedirs(args.out, exist_ok=True)
    for key in args.assets:
        sec = export_asset(key, args.timeframe, month_start, month_end)
        if sec is None:
            print(f"  [{key}] frame yok — atlandı")
            continue
        sections.append(f"// ================= {key} =================\n{sec}")
        pine_txt = assemble_pine(sec)
        ppath = os.path.join(args.out, f"quant4h_viz_{key}_{tag}.pine")
        with open(ppath, "w", encoding="utf-8") as fh:
            fh.write(pine_txt)
        ok += 1
        print(f"  [{key}] payload + HAZIR pine: {os.path.relpath(ppath, ROOT)}")
    if not ok:
        print("HATA: hiçbir varlık için payload üretilemedi")
        return 1
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"payload_{tag}.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(header) + "\n" + "\n".join(sections))
    print(f"\nreferans döküm: {os.path.relpath(path, ROOT)} ({ok} varlık)")
    print(f"TRADINGVIEW: viz/quant4h_viz_<ASSET>_{tag}.pine dosyasının TÜMÜNÜ yeni "
          "indikatör sekmesine yapıştırın (bölge ameliyatı YOK).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
