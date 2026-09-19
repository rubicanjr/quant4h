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
DEFAULT_BARS = 750          # ~4 ay 4H; TAM geçmiş Pine'a GİREMEZ (bkz. PINE_STYLE)
BEGIN = "// ---- PAYLOAD-BEGIN (export_viz_payload.py — otomatik; elle düzenlemeyin)"
END = "// ---- PAYLOAD-END"
TEMPLATE = os.path.join(ROOT, "pine", "quant4h_viz.pine")
DECL_NAMES = ["ts", "ema200", "stopLong", "swingLow", "swingHigh", "donHigh",
              "donLow", "sigLong", "sigShort", "payloadMeta", "payloadOK"]
TEMPLATE_MULTI = os.path.join(ROOT, "pine", "quant4h_viz_multi.pine")
# endeks trade edilmez


BUDGET_BYTES = 90 * 1024   # TradingView kaynak limiti ~100 KB; 10 KB marj — PINE_STYLE.md
MULTI_MIN_BARS = 120       # multi oto-daraltma alt sınırı
FUNC_NAMES = ("ts", "ema200", "stopLong", "swingLow", "swingHigh",
              "donHigh", "donLow", "sigLong", "sigShort")
ASSIGN_NAMES = ("payloadMeta", "payloadOK")


def _lint_common(txt: str, prefixes) -> None:
    """Ortak lint (M15/M15b/M15c/M21/M23):
    (1) array.from >=1 arg ZORUNLU, bos kume -> array.new;
    (2) T15/M23: dizi literal'i MAIN BODY'de TANIMLANAMAZ (atama biçimi yasak),
        yalnız fonksiyon govdesinde: `f_<pre><dizi>() => array.from<...>(...)`;
    (3) PAYLOAD-BEGIN/END ciftleri dengeli;
    (4) fonksiyon dizi uzunluklari == ts uzunlugu;
    (5) T11: tipsiz `x = na` YASAK; (6) T13: plot(scale=...) YASAK;
    (7) T14/descope: trade-review artefaktlari YASAK;
    (8) strategy(/alert(/alertcondition( YASAK;
    (9) tanim tekilligi (fonksiyon + meta/OK atamalari)."""
    if re.search(r"array\.from<[^>]+>\(\s*\)", txt):
        raise RuntimeError("lint IHLAL: array.from bos arguman (Pine: 'Wrong number of "
                           "args: 0'); bos kume array.new ile uretilmeli")
    if re.search(r"^[A-Za-z_]\w*\s*=\s*array\.from<", txt, re.M):
        raise RuntimeError("lint IHLAL (T15/M23): dizi literal'i main body'de tanimlanamaz; "
                           "her dizi kendi fonksiyonunda sabit literal olmali")
    if txt.count("PAYLOAD-BEGIN") != txt.count("PAYLOAD-END"):
        raise RuntimeError("lint IHLAL: PAYLOAD-BEGIN/END ciftleri dengesiz")
    if re.search(r"^[A-Za-z_]\w*\s*=\s*na\s*$", txt, re.M):
        raise RuntimeError("lint IHLAL (T11): tipsiz na atamasi (float/int/bool oneki zorunlu)")
    if re.search(r"\bplot\([^)\n]*\bscale\s*=", txt):
        raise RuntimeError("lint IHLAL (T13): plot(scale=...) Pine v5'te yok")
    for needle in ("trETs", "trEPx", "trXTs", "trXPx", "trR", "label.new", "cumR", "show_trades"):
        if needle in txt:
            raise RuntimeError(f"lint IHLAL (T14/descope): '{needle}' uretilemez")
    code = "\n".join(l for l in txt.splitlines() if not l.lstrip().startswith("//"))
    if "strategy(" in code or re.search(r"^\s*alert\(", code, re.M) or "alertcondition(" in code:
        raise RuntimeError("lint IHLAL: strategy()/alert()/alertcondition() YASAK")
    for pre in prefixes:
        for name in FUNC_NAMES:
            n = len(re.findall(rf"^f_{re.escape(pre)}{name}\(\)\s*=>", txt, re.M))
            if n != 1:
                raise RuntimeError(f"lint IHLAL: f_{pre}{name} fonksiyonu x{n} (beklenen 1)")
        for name in ASSIGN_NAMES:
            n = len(re.findall(rf"^{re.escape(pre)}{name}\s*=", txt, re.M))
            if n != 1:
                raise RuntimeError(f"lint IHLAL: {pre}{name} atamasi x{n} (beklenen 1)")
        mts = re.search(rf"^f_{re.escape(pre)}ts\(\) => array\.from<int>\(([^\n]*)\)$", txt, re.M)
        if not mts:
            continue
        n_ts = mts.group(1).count(",") + 1
        for m in re.finditer(rf"^f_{re.escape(pre)}(\w+)\(\) => array\.from<[^>]+>\(([^\n]*)\)$",
                             txt, re.M):
            name, body = m.group(1), m.group(2)
            if name == "ts":
                continue
            if body.count(",") + 1 != n_ts:
                raise RuntimeError(f"lint IHLAL: f_{pre}{name} uzunlugu != ts uzunlugu {n_ts}")


def lint_pine(txt: str) -> None:
    """Tek-dosya pine lint'i (M23: fonksiyon-biçimi payload)."""
    _lint_common(txt, [""])


def lint_multi(txt: str) -> None:
    """Multi pine lint'i (M23: 4 blok x fonksiyon-biçimi payload + banner iğneleri)."""
    _lint_common(txt, ("a0_", "a1_", "a2_", "a3_"))
    for needle in ("UNTESTED-VIZ", "PAYLOAD YOK", "watch_only",
                   "doğruluk kaynağı DEĞİL", "payload ufku"):
        if needle not in txt:
            raise RuntimeError(f"multi lint HATA: banner iğnesi eksik: {needle}")


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
    if len(txt.encode("utf-8")) > BUDGET_BYTES:
        raise RuntimeError(f"kaynak butcesi asildi: {len(txt)//1024} KB > "
                           f"{BUDGET_BYTES//1024} KB (TV limiti payi) — --bars ile daraltin; "
                           f"TAM gecmis Pine'a GIREMEZ (reports/CSV/dash kullanin)")
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


def export_asset(key: str, tf: str, month_start: Optional[pd.Timestamp] = None,
                 month_end: Optional[pd.Timestamp] = None, prefix: str = "",
                 bars: Optional[int] = None) -> Optional[str]:
    frame = G._signals_for(key, tf, False, None, "A0")     # BIST30 = endeks (tanısal)
    if frame is None or not len(frame):
        return None
    ts = pd.to_datetime(frame["timestamp_utc"], utc=True)
    if month_start is not None and month_end is not None:
        d = frame.loc[(ts >= month_start) & (ts < month_end)]
    else:
        nb = min(int(bars or DEFAULT_BARS), len(frame))   # varlık veri tavanı
        d = frame.iloc[-nb:]
    if not len(d):
        return (f"{BEGIN}\n"
                f'{prefix}payloadMeta = "{key} {month_start:%Y-%m}: pencere BOS (veri yok)"\n'
                f"{prefix}payloadOK   = false\n{END}\n")
    tsd = pd.to_datetime(d["timestamp_utc"], utc=True)
    # epoch MİLİSANİYE (pine `time`): çözünürlükten bağımsız kesin hesap
    # (pandas 3.0 datetime64[us/ms] tuzaklarına karşı — M9b demo bulgusu).
    ms = ((tsd - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(milliseconds=1)).tolist()
    sig_l = d["long_signal"].astype(bool).astype(int).tolist()
    sig_s = d["short_signal"].astype(bool).astype(int).tolist() if "short_signal" in d else [0] * len(d)
    close = pd.to_numeric(d["close"], errors="coerce")
    sig_px = [(float(c) if (sl or ss) and np.isfinite(c) else np.nan)
              for c, sl, ss in zip(close.tolist(), sig_l, sig_s)]
    n_sig = sum(sig_l) + sum(sig_s)
    win_tag = f"{pd.to_datetime(d['timestamp_utc'], utc=True).iloc[-1]:%Y-%m}"
    meta = (f"{key} · {win_tag} · {len(d)} bar · capped P0xA0 · "
            f"final sinyal: {n_sig} · son bar {str(tsd.iloc[-1])[:16]} UTC · "
            f"UNTESTED-VIZ — dogruluk kaynagi DEGIL")
    lines = [
        BEGIN,
        f'{prefix}payloadMeta = "{meta}"',
        f"{prefix}payloadOK   = true",
        f"f_{prefix}ts() => array.from<int>({_pine_ints(ms)})",
        f"f_{prefix}ema200() => array.from<float>({_pine_floats(d.get('ema_trend'))})",
        f"f_{prefix}stopLong() => array.from<float>({_pine_floats(d.get('stop_long'))})",
        f"f_{prefix}swingLow() => array.from<float>({_pine_floats(d.get('last_swing_low'))})",
        f"f_{prefix}swingHigh() => array.from<float>({_pine_floats(d.get('last_swing_high'))})",
        f"f_{prefix}donHigh() => array.from<float>({_pine_floats(d.get('donchian_high'))})",
        f"f_{prefix}donLow() => array.from<float>({_pine_floats(d.get('donchian_low'))})",
        f"f_{prefix}sigLong() => array.from<int>({_pine_ints(sig_l)})",
        f"f_{prefix}sigShort() => array.from<int>({_pine_ints(sig_s)})",
    ]
    lines.append(END)
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--month", default=None, help="YYYY-MM takvim penceresi (opsiyonel override)")
    ap.add_argument("--bars", type=int, default=DEFAULT_BARS,
                    help=f"pencere: son N bar (varsayılan {DEFAULT_BARS} ~= 4 ay; varlık veri tavanıyla sınırlı)")
    ap.add_argument("--assets", nargs="*", default=list(DEFAULT_ASSETS))
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--out", default=os.path.join(ROOT, "viz"))
    args = ap.parse_args()

    if args.month:
        month_start = pd.Timestamp(f"{args.month}-01", tz="UTC")
        month_end = month_start + pd.offsets.MonthBegin(1)
        tag = f"{month_start:%Y-%m}"
        win_kw = {"month_start": month_start, "month_end": month_end}
    else:
        probe = G._signals_for("BTC", args.timeframe, False, None, "A0")
        last = pd.to_datetime(probe["timestamp_utc"], utc=True).max()
        tag = f"{last:%Y-%m}"
        win_kw = {"bars": args.bars}

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
    multi_blocks: List[str] = []
    os.makedirs(args.out, exist_ok=True)
    for ai, key in enumerate(args.assets):
        sec = export_asset(key, args.timeframe, prefix="", **win_kw)
        if sec is None:
            print(f"  [{key}] frame yok — atlandı")
            continue
        sections.append(f"// ================= {key} =================\n{sec}")
        pine_txt = assemble_pine(sec)
        ppath = os.path.join(args.out, f"quant4h_viz_{key}_{tag}.pine")
        with open(ppath, "w", encoding="utf-8") as fh:
            fh.write(pine_txt)
        multi_blocks.append(export_asset(key, args.timeframe, prefix=f"a{ai}_", **win_kw))
        ok += 1
        print(f"  [{key}] payload + HAZIR pine: {os.path.relpath(ppath, ROOT)}")
    if len(multi_blocks) == 4:
        mbars = win_kw.get("bars")
        mtxt = None
        while True:
            try:
                mtxt = assemble_multi(multi_blocks)
                break
            except RuntimeError as e:
                if "butcesi" not in str(e) or mbars is None or mbars <= MULTI_MIN_BARS:
                    raise
                mbars = int(mbars * 0.8)
                multi_blocks = [export_asset(k, args.timeframe, prefix=f"a{i}_", bars=mbars)
                                for i, k in enumerate(args.assets)]
                print(f"  [MULTI] butce icin pencere daraltildi: {mbars} bar/blok")
        mpath = os.path.join(args.out, f"quant4h_viz_multi_{tag}.pine")
        with open(mpath, "w", encoding="utf-8") as fh:
            fh.write(mtxt)
        print(f"  [MULTI] 4 blok gömülü: {os.path.relpath(mpath, ROOT)}")
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




def lint_multi(txt: str) -> None:
    """Multi pine lint'i (M23: 4 blok × fonksiyon-biçimi payload + banner iğneleri)."""
    _lint_common(txt, ("a0_", "a1_", "a2_", "a3_"))
    for needle in ("UNTESTED-VIZ", "PAYLOAD YOK", "watch_only",
                   "doğruluk kaynağı DEĞİL", "payload ufku"):
        if needle not in txt:
            raise RuntimeError(f"multi lint HATA: banner iğnesi eksik: {needle}")
    for needle in ("UNTESTED-VIZ", "PAYLOAD YOK", "AL koşulu oluştu (sinyal kaydı)",
                   "SAT koşulu (sinyal kaydı)", "watch_only"):
        if needle not in txt:
            raise RuntimeError(f"multi lint HATA: banner iğnesi eksik: {needle}")


def assemble_multi(blocks: List[str]) -> str:
    with open(TEMPLATE_MULTI, encoding="utf-8") as fh:
        tpl = fh.read().splitlines()
    i0 = next(i for i, l in enumerate(tpl) if "PAYLOAD-BEGIN" in l)
    i1 = next(i for i, l in enumerate(tpl) if i > i0 and "PAYLOAD-END" in l)
    body: List[str] = []
    for b in blocks:
        body += b.rstrip("\n").splitlines()
    out = tpl[:i0] + body + tpl[i1 + 1:]
    txt = "\n".join(out) + "\n"
    lint_multi(txt)
    if len(txt.encode("utf-8")) > BUDGET_BYTES:
        raise RuntimeError(f"multi kaynak butcesi asildi: {len(txt)//1024} KB > "
                           f"{BUDGET_BYTES//1024} KB — --bars ile daraltin")
    return txt


if __name__ == "__main__":
    raise SystemExit(main())


def lint_multi(txt: str) -> None:
    """Multi pine lint'i (M23: 4 blok × fonksiyon-biçimi payload + banner iğneleri)."""
    _lint_common(txt, ("a0_", "a1_", "a2_", "a3_"))
    for needle in ("UNTESTED-VIZ", "PAYLOAD YOK", "watch_only",
                   "doğruluk kaynağı DEĞİL", "payload ufku"):
        if needle not in txt:
            raise RuntimeError(f"multi lint HATA: banner iğnesi eksik: {needle}")
    for needle in ("UNTESTED-VIZ", "PAYLOAD YOK", "AL koşulu oluştu (sinyal kaydı)",
                   "SAT koşulu (sinyal kaydı)", "watch_only"):
        if needle not in txt:
            raise RuntimeError(f"multi lint HATA: banner iğnesi eksik: {needle}")


def assemble_multi(blocks: List[str]) -> str:
    with open(TEMPLATE_MULTI, encoding="utf-8") as fh:
        tpl = fh.read().splitlines()
    i0 = next(i for i, l in enumerate(tpl) if "PAYLOAD-BEGIN" in l)
    i1 = next(i for i, l in enumerate(tpl) if i > i0 and "PAYLOAD-END" in l)
    body: List[str] = []
    for b in blocks:
        body += b.rstrip("\n").splitlines()
    out = tpl[:i0] + body + tpl[i1 + 1:]
    txt = "\n".join(out) + "\n"
    lint_multi(txt)
    if len(txt.encode("utf-8")) > BUDGET_BYTES:
        raise RuntimeError(f"multi kaynak butcesi asildi: {len(txt)//1024} KB > "
                           f"{BUDGET_BYTES//1024} KB — --bars ile daraltin")
    return txt


if __name__ == "__main__":
    raise SystemExit(main())
