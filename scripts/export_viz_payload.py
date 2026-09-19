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
              "donLow", "sigLong", "sigShort", "sigPrice", "payloadMeta", "payloadOK",
              "trETs", "trEPx", "trXTs", "trXPx", "trR"]
TEMPLATE_MULTI = os.path.join(ROOT, "pine", "quant4h_viz_multi.pine")
TRADE_CSV = {"BTC": "trades_BTC.csv", "GOLD": "trades_GOLD.csv",
             "SILVER": "trades_SILVER.csv", "BIST30": None}   # endeks trade edilmez


def _ms_series(ts_utc: pd.Series) -> List[int]:
    return ((pd.to_datetime(ts_utc, utc=True) - pd.Timestamp("1970-01-01", tz="UTC"))
            // pd.Timedelta(milliseconds=1)).astype("int64").tolist()


def export_trade_arrays(key: str, prefix: str) -> List[str]:
    """reports/trades_<KEY>.csv (capped P0xA0 backtest kaydı) → gömülü diziler.
    Giriş dizisi giriş zamanına, çıkış dizisi ÇIKIŞ zamanına sıralı (işaretçi
    mantığı O(1) amortize). BIST30/endeks için BOŞ diziler (trade-review YOK)."""
    csv = TRADE_CSV.get(key)
    path = os.path.join(ROOT, "reports", csv) if csv else None
    if path is None or not os.path.exists(path):
        # M15: Pine `array.from<T>()` (0 arg) GEÇERSİZDİR ("Wrong number of
        # args: 0"); boş küme her zaman array.new<T>() ile üretilir.
        return [f"{prefix}trETs  = array.new<int>()",
                f"{prefix}trEPx  = array.new<float>()",
                f"{prefix}trXTs  = array.new<int>()",
                f"{prefix}trXPx  = array.new<float>()",
                f"{prefix}trR    = array.new<float>()"]
    df = pd.read_csv(path)
    de = df.sort_values("entry_timestamp_utc")
    dx = df.sort_values("exit_timestamp_utc")
    return [
        f"{prefix}trETs  = array.from<int>({_pine_ints(_ms_series(de['entry_timestamp_utc']))})",
        f"{prefix}trEPx  = array.from<float>({_pine_floats(de['entry_price'])})",
        f"{prefix}trXTs  = array.from<int>({_pine_ints(_ms_series(dx['exit_timestamp_utc']))})",
        f"{prefix}trXPx  = array.from<float>({_pine_floats(dx['exit_price'])})",
        f"{prefix}trR    = array.from<float>({_pine_floats(dx['r_multiple'])})",
    ]


BUDGET_BYTES = 90 * 1024   # TradingView kaynak limiti ~100 KB; 10 KB marj — PINE_STYLE.md
MULTI_MIN_BARS = 120       # multi oto-daraltma alt sınırı


def _lint_common(txt: str, prefixes) -> None:
    """M15 lint çekirdeği: (1) array.from >=1 arg ZORUNLU, bos kume -> array.new;
    (2) PAYLOAD-BEGIN/END ciftleri dengeli; (3) from-dizi uzunluklari == ts
    uzunlugu (array.new bos oldugu icin muaftir); (4) kod satirlarinda
    strategy(/alert(/alertcondition( YOK."""
    if re.search(r"array\.from<[^>]+>\(\s*\)", txt):
        raise RuntimeError("lint IHLAL: array.from bos arguman (Pine: 'Wrong number of "
                           "args: 0'); bos kume array.new ile uretilmeli")
    if txt.count("PAYLOAD-BEGIN") != txt.count("PAYLOAD-END"):
        raise RuntimeError("lint IHLAL: PAYLOAD-BEGIN/END ciftleri dengesiz")
    for pre in prefixes:
        mts = re.search(rf"^{re.escape(pre)}ts\s*= array\.from<int>\(([^\n]*)\)$", txt, re.M)
        if not mts:
            continue
        n_ts = mts.group(1).count(",") + 1
        for m in re.finditer(rf"^{re.escape(pre)}(\w+)\s*= array\.from<[^>]+>\(([^\n]*)\)$",
                             txt, re.M):
            name, body = m.group(1), m.group(2)
            if name == "ts" or name.startswith("tr"):
                continue   # trade dizileri bilinçli olarak ts'den farklı uzunluktadır
            n = body.count(",") + 1
            if n != n_ts:
                raise RuntimeError(f"lint IHLAL: {pre}{name} uzunlugu {n} != ts uzunlugu {n_ts}")
    code = "\n".join(l for l in txt.splitlines() if not l.lstrip().startswith("//"))
    if "strategy(" in code or re.search(r"^\s*alert\(", code, re.M) or "alertcondition(" in code:
        raise RuntimeError("lint IHLAL: strategy()/alert()/alertcondition() YASAK")


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
    _lint_common(txt, [""])


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
        f"{prefix}ts        = array.from<int>({_pine_ints(ms)})",
        f"{prefix}ema200    = array.from<float>({_pine_floats(d.get('ema_trend'))})",
        f"{prefix}stopLong  = array.from<float>({_pine_floats(d.get('stop_long'))})",
        f"{prefix}swingLow  = array.from<float>({_pine_floats(d.get('last_swing_low'))})",
        f"{prefix}swingHigh = array.from<float>({_pine_floats(d.get('last_swing_high'))})",
        f"{prefix}donHigh   = array.from<float>({_pine_floats(d.get('donchian_high'))})",
        f"{prefix}donLow    = array.from<float>({_pine_floats(d.get('donchian_low'))})",
        f"{prefix}sigLong   = array.from<int>({_pine_ints(sig_l)})",
        f"{prefix}sigShort  = array.from<int>({_pine_ints(sig_s)})",
        f"{prefix}sigPrice  = array.from<float>({_pine_floats(sig_px)})",
    ]
    lines += export_trade_arrays(key, prefix)
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
                mbars //= 2
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
    """M14 lint: 4 blok × 17 tanım TAM 1 kez; kod satırlarında strategy/alert YOK;
    sabit banner iğneleri mevcut."""
    lines = txt.splitlines()
    for pre in ("a0_", "a1_", "a2_", "a3_"):
        for name in DECL_NAMES:
            n = sum(1 for l in lines if re.match(rf"^{re.escape(pre + name)}\s*=", l))
            if n != 1:
                raise RuntimeError(f"multi lint HATA: '{pre}{name}' x{n} (beklenen 1)")
    _lint_common(txt, ("a0_", "a1_", "a2_", "a3_"))
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
    """M14 lint: 4 blok × 17 tanım TAM 1 kez; kod satırlarında strategy/alert YOK;
    sabit banner iğneleri mevcut."""
    lines = txt.splitlines()
    for pre in ("a0_", "a1_", "a2_", "a3_"):
        for name in DECL_NAMES:
            n = sum(1 for l in lines if re.match(rf"^{re.escape(pre + name)}\s*=", l))
            if n != 1:
                raise RuntimeError(f"multi lint HATA: '{pre}{name}' x{n} (beklenen 1)")
    _lint_common(txt, ("a0_", "a1_", "a2_", "a3_"))
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
