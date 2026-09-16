#!/usr/bin/env python3
"""
PRE-REGISTRATION of the train / validation / test splits (Aşama 1c).

    python3 scripts/register_splits.py                 # yaz
    python3 scripts/register_splits.py --check         # sadece dogrula, yazma

Why this file exists
--------------------
The split must be frozen BEFORE any model, indicator or threshold is looked at.
If the split is chosen after seeing results, "out-of-sample" is a fiction. So
this script writes `configs/splits_preregistered.yaml` containing exact bar
indices, exact UTC timestamps and a SHA-256 of the source data, and the file is
treated as immutable: changing it after results exist invalidates every number
in the report.

Policy (deliberately simple, deliberately fixed)
-----------------------------------------------
* TEST is the MOST RECENT period, per asset (walk-forward compatible).
* Fixed BAR COUNTS, not fractions, because asset histories differ by 4x
  (BTC 19.9k bars vs metals 3.6k). Fractions would give metals a ~120-day test
  window, which is too small to say anything.
* PURGE removes the last ``purge_bars`` bars of TRAIN and the first
  ``purge_bars`` bars of VALID/TEST, because a label with horizon H uses H
  future bars: without purging, train and valid share information.
* EMBARGO additionally removes ``embargo_bars`` after every boundary to absorb
  overlapping-feature leakage (rolling windows).
* Counts are computed on the **tradable** subset (``non_tradable == False``),
  so BIST30's 721 opening-snapshot bars and the metals' outage bars cannot
  inflate the sample size.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from quant4h.config import DEFAULT_ASSETS, UTC  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_PATH = os.path.join(ROOT, "configs", "splits_preregistered.yaml")
FROZEN_DIR = os.path.join(ROOT, "data", "frozen")

# ---------------------------------------------------------------------------
# POLICY — frozen. Changing these numbers after results exist is a new
# pre-registration, not an edit; bump `policy_version` and keep the old file.
# ---------------------------------------------------------------------------
POLICY_VERSION = "1.1"
POLICY: Dict[str, Any] = {
    "test_bars": 1000,          # en yeni 1000 islem-uygun bar
    "valid_bars": 800,          # test'ten onceki 800 bar
    "purge_bars": 30,           # >= max label horizon (30 x 4h = 5 gun)
    "embargo_bars": 12,         # rolling-window sizintisi icin ek tampon
    "min_test_bars": 400,       # altinda -> varlik OOS degerlendirmeye ALINMAZ
    "counting_basis": "tradable_bars_only",   # non_tradable == False
    "test_is_most_recent": True,
    "no_shuffle": True,
    "test_used_exactly_once": True,
    "min_test_calendar_days": 365,   # altinda -> ayrica uyari
    "min_test_sessions": 200,        # BIST30 gibi az seansli varliklar icin
    "version_note": (
        "v1.1 (2026-09-16): BIST grid tanimi DEGISTI. Ince 'acilis ani' bari "
        "(06:00-10:00 lokal, n_src=1) artik URETILMIYOR cunku non_tradable oldugu "
        "icin anchor olamiyordu ve k=3 fraktal HICBIR swing'i onaylayamiyordu "
        "(28 hissede swing=0/Donchian=0/stop=0). Yeni grid: gunde 2 TAM bar "
        "(07/11 UTC). v1.0 configs/splits_preregistered.v1.0.archived.yaml "
        "icinde SAKLANDI, silinmedi."),
    "rationale": (
        "Sabit BAR SAYISI (yuzde degil) secildi, cunku varlik gecmisleri 4 kat "
        "fark ediyor (BTC 19.9k bar / metaller 3.6k). Yuzde (60/20/20) "
        "kullanilsaydi metallerin test penceresi ~167 bar = ~28 gun olurdu ve "
        "hicbir sey soylemezdi. Bedeli: BTC test penceresi kisa kalir "
        "(~958 bar = ~159 gun). Bu bedel KABUL EDILDI cunku BTC icin asil OOS "
        "araci tek bir test penceresi degil, Asama 9'daki WALK-FOLD katlanacak "
        "walk-forward analizidir. Politika degistirmek istenirse policy_version "
        "artirilir ve YENI dosya yazilir; eskisi silinmez."),
}


def _sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _load(asset: str, timeframe: str) -> Optional[pd.DataFrame]:
    """Prefer the adjusted frame (it carries non_tradable / return_valid)."""
    proc = os.path.join(ROOT, "data", "processed", f"{asset.lower()}_{timeframe}_adjusted.parquet")
    side = proc.replace(".parquet", ".attrs.json")
    interim = os.path.join(ROOT, "data", "interim", f"{asset.lower()}_{timeframe}.parquet")
    if os.path.exists(proc):
        df = pd.read_parquet(proc)
        if os.path.exists(side):
            with open(side, "r", encoding="utf-8") as fh:
                df.attrs.update(json.load(fh))
        return df
    if os.path.exists(interim):
        return pd.read_parquet(interim)
    return None


def _load_stock(code: str, timeframe: str = "4h") -> Optional[pd.DataFrame]:
    path = os.path.join(ROOT, "data", "processed", "bist30",
                        f"{code}_{timeframe}_adjusted.parquet")
    if not os.path.exists(path):
        path = os.path.join(ROOT, "data", "interim", "bist30", f"{code}_{timeframe}.parquet")
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    side = path.replace(".parquet", ".attrs.json")
    if os.path.exists(side):
        with open(side, "r", encoding="utf-8") as fh:
            df.attrs.update(json.load(fh))
    return df


def included_stock_codes(report_path: Optional[str] = None) -> List[str]:
    """Aşama 1.5 QC raporundan SEPETE GİREN hisseleri oku (elenenler girmez)."""
    p = report_path or os.path.join(ROOT, "reports", "bist30_universe_qc.json")
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return sorted(r["code"] for r in doc.get("stocks", [])
                  if r.get("status") == "INCLUDED")


def build_basket_split(timeframe: str = "4h",
                       report_path: Optional[str] = None) -> Dict[str, Any]:
    """BIST30 hisse sepeti için TEK ORTAK TAKVİM PENCERESİ ön-kaydı.

    KARAR 1 (2026-09-16): hisse başına AYRI split YOK. Tüm sepet aynı takvim
    penceresini paylaşır; bu sayede walk-forward katları hisse bazında
    kaymaz ve portföy düzeyinde OOS ölçümü anlamlı kalır.

    Pencere, sepetin ORTAK kesişim aralığıdır (en geç başlayan → en erken
    biten). Blok sınırları ORTAK TAKVİM IZGARASI üzerinde bar sayısıyla
    belirlenir; her hissenin o bloktaki GERÇEK (tradable) bar sayısı ayrıca
    raporlanır. Purge/embargo ve frozen-snapshot kuralı (H17) core varlıklarla
    birebir aynıdır.
    """
    codes = included_stock_codes(report_path)
    if not codes:
        return {"error": "sepete giren hisse bulunamadı (reports/bist30_universe_qc.json yok mu?)"}
    frames: Dict[str, pd.DataFrame] = {}
    missing: List[str] = []
    for c in codes:
        f = _load_stock(c, timeframe)
        if f is None or not len(f):
            missing.append(c)
            continue
        frames[c] = f
    if not frames:
        return {"error": "hiçbir hisse verisi okunamadı"}

    stamps = {c: pd.to_datetime(f["timestamp_utc"], utc=True) for c, f in frames.items()}
    start = max(t.min() for t in stamps.values())
    end = min(t.max() for t in stamps.values())
    if end <= start:
        return {"error": "ortak pencere boş", "start": str(start), "end": str(end)}

    # ortak takvim ızgarası: tüm hisselerin damgalarının BİRLEŞİMİ, pencereyle sınırlı
    grid = sorted(set().union(*[set(t[(t >= start) & (t <= end)]) for t in stamps.values()]))
    grid_ts = pd.DatetimeIndex(grid)
    n_grid = len(grid_ts)

    # her hisse için pencere içi 'tradable' damga kümesi
    trad: Dict[str, set] = {}
    for c, f in frames.items():
        t = stamps[c]
        m = (t >= start) & (t <= end)
        nt = f["non_tradable"] if "non_tradable" in f.columns else pd.Series(False, index=f.index)
        keep = m & ~pd.to_numeric(nt, errors="coerce").fillna(False).astype(bool).to_numpy()
        trad[c] = set(t[keep])

    purge, embargo = POLICY["purge_bars"], POLICY["embargo_bars"]
    n_test = min(POLICY["test_bars"], n_grid // 3)
    n_valid = min(POLICY["valid_bars"], (n_grid - n_test) // 2)
    n_train = n_grid - n_test - n_valid

    def _block(a: int, b: int) -> Dict[str, Any]:
        if b <= a:
            return {"grid_bars": 0, "first_utc": None, "last_utc": None,
                    "median_tradable_bars_per_stock": 0, "min_tradable_bars_per_stock": 0,
                    "stocks": {}}
        sub = grid_ts[a:b]
        per = {c: sum(1 for x in sub if x in trad[c]) for c in trad}
        vals = list(per.values())
        return {"grid_bars": int(len(sub)), "first_utc": str(sub[0]), "last_utc": str(sub[-1]),
                "median_tradable_bars_per_stock": float(np.median(vals)) if vals else 0.0,
                "min_tradable_bars_per_stock": int(min(vals)) if vals else 0,
                "max_tradable_bars_per_stock": int(max(vals)) if vals else 0,
                "stocks": {k: int(v) for k, v in sorted(per.items())}}

    train = _block(0, max(0, n_train - purge - embargo))
    valid = _block(min(n_grid, n_train + purge + embargo), max(0, n_train + n_valid - purge - embargo))
    test = _block(min(n_grid, n_train + n_valid + purge + embargo), n_grid)

    # frozen snapshot: sepetin uzun formu (H17 kuralı)
    os.makedirs(FROZEN_DIR, exist_ok=True)
    long_rows = []
    for c, f in frames.items():
        t = stamps[c]
        m = (t >= start) & (t <= end)
        nt = f["non_tradable"] if "non_tradable" in f.columns else pd.Series(False, index=f.index)
        long_rows.append(pd.DataFrame({
            "stock": c, "timestamp_utc": t[m].to_numpy(),
            "tradable": (~pd.to_numeric(nt, errors="coerce").fillna(False).astype(bool))[m].to_numpy(),
        }))
    basket = pd.concat(long_rows, ignore_index=True).sort_values(["timestamp_utc", "stock"])
    frozen = os.path.join(FROZEN_DIR, f"bist30_basket_{timeframe}_frozen.parquet")
    basket.to_parquet(frozen, index=False)

    test_days = (pd.Timestamp(test["last_utc"]) - pd.Timestamp(test["first_utc"])).days \
        if test["first_utc"] else 0
    warnings: List[str] = [
        "SURVIVORSHIP BIAS: sepet yalnızca BUGÜN BIST30'da olan 28 hisseyi içerir; "
        "geçmişte endekste olup çıkanlar YOKTUR. Sonuçlar YUKARI yönlü çarpıktır.",
        "BIST30 hisseleri LONG-ONLY'dir ve XU030 bağlam filtresine tabidir; bu split "
        "o filtre UYGULANMADAN önceki ham pencereyi tanımlar.",
        f"DSTKF ve TRALT ünivers üyesi olduğu hâlde sepette DEĞİL (Aşama 1.5'te elendi) "
        f"→ sepet BIST30'u TAM temsil etmez.",
    ]
    if test["min_tradable_bars_per_stock"] < POLICY["min_test_bars"]:
        warnings.append(
            f"TEST bloğunda hisse başına medyan {test['median_tradable_bars_per_stock']:.0f} "
            f"tradable bar var (min {test['min_tradable_bars_per_stock']}). "
            f"Bar sayısı yeterli görünse de bağımsız SEANS sayısı düşüktür.")
    if test_days < POLICY["min_test_calendar_days"]:
        warnings.append(f"TEST penceresi {test_days} takvim günü (< {POLICY['min_test_calendar_days']}).")

    return {
        "type": "basket",
        "name": "bist30_basket",
        "asset": "BIST30_BASKET",
        "symbol": f"BIST30 basket ({len(frames)} hisse, eşit-risk)",
        "mode": "core",
        "timeframe": timeframe,
        "universe_version": "2026-09-16.v1",
        "weighting": "equal_risk",
        "signal_level": "per_stock",
        "stocks": sorted(frames),
        "n_stocks": len(frames),
        "excluded_from_basket": sorted(set(codes) - set(frames)) + ["DSTKF", "TRALT"],
        "missing_data": missing,
        "common_window": {"start_utc": str(start), "end_utc": str(end)},
        "grid_bars": n_grid,
        "frozen_file": os.path.relpath(frozen, ROOT),
        "frozen_sha256": _sha256(frozen),
        "frozen_rows": int(len(basket)),
        "live_file_at_registration": "data/processed/bist30/",
        "live_sha256_at_registration": "",
        "train": {"used": train}, "valid": {"used": valid}, "test": {"used": test},
        "test_calendar_days": int(test_days),
        "purge_bars": purge, "embargo_bars": embargo,
        "warnings": warnings,
        "sufficient_for_oos": bool(test["min_tradable_bars_per_stock"] >= POLICY["min_test_bars"]),
    }


def _freeze(asset: str, timeframe: str, src: str) -> str:
    """Copy the source frame into data/frozen/ and return the frozen path.

    WHY: the live feed keeps growing (a new intraday bar appears every run), so
    a sha256 over the live file would invalidate the pre-registration on the
    very next download. The pre-registration is therefore pinned to a FROZEN
    snapshot; the live file is allowed to drift and the drift is reported.
    """
    import shutil
    os.makedirs(FROZEN_DIR, exist_ok=True)
    dst = os.path.join(FROZEN_DIR, f"{asset.lower()}_{timeframe}_frozen.parquet")
    shutil.copyfile(src, dst)
    side = src.replace(".parquet", ".attrs.json")
    if os.path.exists(side):
        shutil.copyfile(side, dst.replace(".parquet", ".attrs.json"))
    return dst


def build_split(asset: str, timeframe: str = "4h") -> Dict[str, Any]:
    if asset not in DEFAULT_ASSETS:
        return {"asset": asset, "error": f"bilinmeyen varlik; tanimli olanlar: {sorted(DEFAULT_ASSETS)}"}
    spec = DEFAULT_ASSETS[asset]
    live = os.path.join(ROOT, "data", "processed", f"{asset.lower()}_{timeframe}_adjusted.parquet")
    if not os.path.exists(live):
        live = os.path.join(ROOT, "data", "interim", f"{asset.lower()}_{timeframe}.parquet")
    df = _load(asset, timeframe)
    if df is None or not len(df):
        return {"asset": asset, "error": f"veri bulunamadi: {live}"}
    frozen = _freeze(asset, timeframe, live)
    df = pd.read_parquet(frozen)
    side = frozen.replace(".parquet", ".attrs.json")
    if os.path.exists(side):
        with open(side, "r", encoding="utf-8") as fh:
            df.attrs.update(json.load(fh))

    df = df.sort_values("timestamp_utc").reset_index(drop=True)
    ts = pd.to_datetime(df["timestamp_utc"], utc=True)

    tradable = pd.Series(True, index=df.index)
    if "non_tradable" in df.columns:
        tradable = ~pd.to_numeric(df["non_tradable"], errors="coerce").fillna(False).astype(bool)
    idx = df.index[tradable].to_numpy()
    n_trad = len(idx)

    n_test = min(POLICY["test_bars"], max(0, n_trad // 3))
    n_valid = min(POLICY["valid_bars"], max(0, (n_trad - n_test) // 2))
    n_train = n_trad - n_test - n_valid
    purge, embargo = POLICY["purge_bars"], POLICY["embargo_bars"]

    def _block(start: int, stop: int) -> Dict[str, Any]:
        """[start, stop) over the tradable index, with purge/embargo applied."""
        if stop <= start:
            return {"n_raw": 0, "n_used": 0, "first": None, "last": None,
                    "first_utc": None, "last_utc": None}
        raw = idx[start:stop]
        return {"n_raw": int(len(raw)), "first_pos": int(raw[0]), "last_pos": int(raw[-1]),
                "first_utc": str(ts.iloc[int(raw[0])]), "last_utc": str(ts.iloc[int(raw[-1])])}

    train_raw = _block(0, n_train)
    valid_raw = _block(n_train, n_train + n_valid)
    test_raw = _block(n_train + n_valid, n_trad)

    # purge + embargo: train'in SONU ve valid/test'in BASI budanir
    train_used = _block(0, max(0, n_train - purge - embargo))
    valid_used = _block(min(n_trad, n_train + purge + embargo),
                        max(0, n_train + n_valid - purge - embargo))
    test_used = _block(min(n_trad, n_train + n_valid + purge + embargo), n_trad)

    warnings: List[str] = []
    years = (ts.iloc[-1] - ts.iloc[0]) / pd.Timedelta(days=365.25)
    test_days = (pd.Timestamp(test_used["last_utc"]) - pd.Timestamp(test_used["first_utc"])).days \
        if test_used["first_utc"] else 0
    # seans sayisi: BIST30 gibi cok barli ama az seansli serilerde bar sayisi yaniltir
    _tstart = min(n_trad, n_train + n_valid + purge + embargo)
    _tpos = idx[_tstart:]
    if "session_date" in df.columns and len(_tpos):
        n_sessions = int(pd.to_datetime(df["session_date"].astype(str))
                         .iloc[_tpos].nunique())
    elif len(_tpos):
        n_sessions = int(pd.DatetimeIndex(ts.iloc[_tpos]).tz_convert(UTC).normalize().nunique())
    else:
        n_sessions = 0
    if test_used["n_raw"] < POLICY["min_test_bars"]:
        warnings.append(
            f"TEST yalnızca {test_used['n_raw']} bar (< {POLICY['min_test_bars']}): "
            f"bu varlık OOS değerlendirmeye ALINMAMALI; sonuçları yalnızca tanımlayıcıdır.")
    if test_used["first_utc"] and test_days < POLICY["min_test_calendar_days"]:
        warnings.append(
            f"TEST penceresi yalnızca {test_days} takvim günü "
            f"(< {POLICY['min_test_calendar_days']}): tek başına OOS sonucuna "
            f"güvenmek için KISA. Bu varlıkta asıl OOS aracı walk-forward olmalıdır.")
    if spec.mode == "watch_only":
        warnings.append("watch_only: sinyal üretilir ama portföy performansına ZORLA SOKULMAZ.")
    if n_sessions < POLICY["min_test_sessions"]:
        warnings.append(
            f"TEST dönemi yalnızca {n_sessions} ayrı seans/gün içeriyor "
            f"(< {POLICY['min_test_sessions']}): İSTATİSTİKSEL GÜÇ ÇOK DÜŞÜK. "
            f"'sufficient_for_oos=True' olsa bile sonuçlar yalnızca YÖN GÖSTERİR.")
    if not bool(tradable.all()):
        warnings.append(
            f"{int((~tradable).sum())} bar non_tradable (kesinti/ince bar/henüz oluşuyor) "
            f"-> örneklem sayımları bunlar HARİÇ tutularak yapıldı.")
    if spec.requires_adjustment:
        warnings.append(
            "ön-ay vadeli seri: roll KESİN tespit edilemez (feed'de kontrat ayı kimliği yok). "
            "close_adjusted == close_raw; roll adayları yalnızca işaretli.")

    return {
        "asset": asset,
        "symbol": spec.symbol,
        "mode": spec.mode,
        "frozen_file": os.path.relpath(frozen, ROOT),
        "frozen_sha256": _sha256(frozen),
        "live_file_at_registration": os.path.relpath(live, ROOT),
        "live_sha256_at_registration": _sha256(live),
        "timeframe": timeframe,
        "rows_total": int(len(df)),
        "rows_tradable": int(n_trad),
        "rows_non_tradable": int(len(df) - n_trad),
        "history_years": round(float(years), 3),
        "train": {"raw": train_raw, "used": train_used},
        "valid": {"raw": valid_raw, "used": valid_used},
        "test": {"raw": test_raw, "used": test_used,
                 "calendar_days": int(test_days), "sessions": int(n_sessions)},
        "purge_bars": purge,
        "embargo_bars": embargo,
        "warnings": warnings,
        "sufficient_for_oos": bool(test_used["n_raw"] >= POLICY["min_test_bars"]),
    }


def register(assets: List[str], timeframe: str = "4h", write: bool = True) -> Dict[str, Any]:
    doc: Dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "preregistered_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
        "purpose": ("Bu dosya bir ON-KAYITTIR (pre-registration). Test dönemi, "
                    "herhangi bir model/indikatory/eşik SONUCU GÖRÜLMEDEN sabitlenir. "
                    "Sonuçlar görüldükten sonra bu dosyayı DEĞİŞTİRMEK tüm OOS "
                    "iddialarını geçersiz kılar; gerekiyorsa policy_version artırılıp "
                    "YENİ bir dosya yazılır, eskisi silinmez."),
        "policy": POLICY,
        "hard_rules": [
            "TEST dönemi hiçbir eğitim, hyperparameter araması veya eşik seçiminde KULLANILMAZ.",
            "TEST tam olarak BİR KEZ, tüm kararlar dondurulduktan sonra çalıştırılır.",
            "Hyperparameter araması yalnızca VALID üzerinde yapılır.",
            "Purge ve embargo atlanamaz: label horizon'u kadar bar her sınırda budanır.",
            "Örneklem sayımları non_tradable barlar HARİÇ tutularak yapılır.",
            "Bu dosya değiştikçe frozen_sha256 uyuşmazlığı kontrol edilir; uyuşmazsa "
            "kayıt GEÇERSİZ sayılır ve yeniden üretilmesi gerekir.",
        ],
        "assets": {},
    }
    for a in assets:
        doc["assets"][a] = build_split(a, timeframe)
    # KARAR 1: BIST30 hisse sepeti icin TEK ORTAK TAKVIM PENCERESI
    # (hisse basina ayri split YOK). Ayni policy, ayni purge/embargo, ayni
    # frozen-snapshot kurali.
    doc["bist30_basket"] = build_basket_split(timeframe)
    if write:
        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as fh:
            yaml.safe_dump(doc, fh, allow_unicode=True, sort_keys=False, width=110)
    return doc


def verify(path: str = OUT_PATH) -> List[str]:
    """Ön-kaydın hâlâ geçerli olduğunu doğrula.

    Kontrol edilen: DONDURULMUŞ snapshot'ın sha256'sı (değişmişse kayıt
    GEÇERSİZDİR) ve blok çakışmaları. Canlı dosyanın büyümesi (yeni bar) bir
    HATA DEĞİLDİR; ``drift_report`` ile bilgi olarak döner.
    """
    problems: List[str] = []
    if not os.path.exists(path):
        return [f"{path} yok"]
    with open(path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    entries = list((doc.get("assets") or {}).items())
    if isinstance(doc.get("bist30_basket"), dict):
        entries.append(("BIST30_BASKET", doc["bist30_basket"]))
    for asset, rec in entries:
        if "error" in rec:
            problems.append(f"{asset}: {rec['error']}")
            continue
        fz = os.path.join(ROOT, rec["frozen_file"])
        if not os.path.exists(fz):
            problems.append(f"{asset}: dondurulmuş snapshot YOK ({rec['frozen_file']}) — "
                            f"ön-kayıt doğrulanamaz, register_splits.py yeniden çalıştırılmalı")
            continue
        actual = _sha256(fz)
        if actual != rec["frozen_sha256"]:
            problems.append(
                f"{asset}: frozen_sha256 UYUŞMUYOR — dondurulmuş veri DEĞİŞTİRİLMİŞ, "
                f"ön-kayıt GEÇERSİZ (kayıtlı {rec['frozen_sha256'][:12]}…, gerçek {actual[:12]}…)")
        t, v, tr = rec["test"]["used"], rec["valid"]["used"], rec["train"]["used"]
        if not t.get("first_utc"):
            continue
        if t["first_utc"] and v["last_utc"] and pd.Timestamp(t["first_utc"]) <= pd.Timestamp(v["last_utc"]):
            problems.append(f"{asset}: TEST ve VALID çakışıyor")
        if v["first_utc"] and tr["last_utc"] and pd.Timestamp(v["first_utc"]) <= pd.Timestamp(tr["last_utc"]):
            problems.append(f"{asset}: VALID ve TRAIN çakışıyor")
        if t["last_utc"] and v["first_utc"] and pd.Timestamp(v["first_utc"]) >= pd.Timestamp(t["last_utc"]):
            problems.append(f"{asset}: blok sıralaması bozuk (valid >= test)")
    return problems


def drift_report(path: str = OUT_PATH) -> List[str]:
    """Canlı veri ile dondurulmuş snapshot arasındaki farkı raporla (hata değil)."""
    notes: List[str] = []
    if not os.path.exists(path):
        return notes
    with open(path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    for asset, rec in (doc.get("assets") or {}).items():
        if "error" in rec:
            continue
        live = os.path.join(ROOT, rec["live_file_at_registration"])
        if not os.path.exists(live):
            notes.append(f"{asset}: canlı dosya yok ({rec['live_file_at_registration']})")
            continue
        if _sha256(live) != rec["live_sha256_at_registration"]:
            try:
                now_df = pd.read_parquet(live)
                frozen_df = pd.read_parquet(os.path.join(ROOT, rec["frozen_file"]))
                notes.append(
                    f"{asset}: canlı veri büyüdü {len(frozen_df)} -> {len(now_df)} bar "
                    f"(son bar {pd.to_datetime(now_df['timestamp_utc'], utc=True).max():%Y-%m-%d %H:%M}). "
                    f"Ön-kayıt DONDURULMUŞ snapshot'a bağlıdır, bu yüzden hâlâ GEÇERLİ; "
                    f"yeni barlar ancak YENİ bir ön-kayıtla (policy_version artırılarak) çalışmaya girer.")
            except Exception as exc:                                   # noqa: BLE001
                notes.append(f"{asset}: canlı veri okunamadı ({exc})")
    return notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets", nargs="*", default=list(DEFAULT_ASSETS))
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--check", action="store_true", help="yazma, sadece doğrula")
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    if args.check:
        problems = verify(args.out)
        if problems:
            print("DOĞRULAMA BAŞARISIZ:")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(f"DOĞRULAMA OK: {args.out} dondurulmuş snapshot ile uyumlu, çakışma yok.")
        for n in drift_report(args.out):
            print(f"  [drift] {n}")
        return 0

    doc = register(args.assets, args.timeframe, write=True)
    print(f"yazıldı: {OUT_PATH}\n")
    hdr = f"{'VARLIK':8s} {'TOPLAM':>7s} {'TRADE':>7s} | {'TRAIN':>6s} {'VALID':>6s} {'TEST':>6s} | {'TEST GÜN':>8s} {'OOS':>4s}"
    print(hdr)
    print("-" * len(hdr))
    for a, r in doc["assets"].items():
        if "error" in r:
            print(f"{a:8s} HATA: {r['error']}")
            continue
        print(f"{a:8s} {r['rows_total']:7d} {r['rows_tradable']:7d} | "
              f"{r['train']['used']['n_raw']:6d} {r['valid']['used']['n_raw']:6d} "
              f"{r['test']['used']['n_raw']:6d} | {r['test']['calendar_days']:8d} "
              f"{'EVET' if r['sufficient_for_oos'] else 'HAYIR':>4s}")
    b = doc.get("bist30_basket") or {}
    if b and "error" not in b:
        print(f"\nBIST30 SEPET (ortak takvim penceresi, {b['n_stocks']} hisse, {b['weighting']}):")
        print(f"  pencere {b['common_window']['start_utc'][:10]} → {b['common_window']['end_utc'][:10]}"
              f" | ızgara {b['grid_bars']} bar | frozen {b['frozen_rows']} satır")
        for k in ("train", "valid", "test"):
            u = b[k]["used"]
            print(f"  {k.upper():5s} ızgara {u['grid_bars']:5d} | hisse başına tradable "
                  f"medyan {u['median_tradable_bars_per_stock']:6.0f} "
                  f"(min {u['min_tradable_bars_per_stock']}, max {u['max_tradable_bars_per_stock']})"
                  f" | {str(u['first_utc'])[:10]} → {str(u['last_utc'])[:10]}")
        print(f"  TEST takvim günü: {b['test_calendar_days']} | OOS yeterli: {b['sufficient_for_oos']}")
    elif b:
        print(f"\nBIST30 SEPET: HATA {b['error']}")

    print("\nUYARILAR:")
    for a, r in doc["assets"].items():
        for w in r.get("warnings", []):
            print(f"  [{a}] {w}")
    for w in (b or {}).get("warnings", []):
        print(f"  [BIST30_BASKET] {w}")
    problems = verify(args.out)
    print("\nDOĞRULAMA:", "OK" if not problems else problems)
    for n in drift_report(args.out):
        print(f"  [drift] {n}")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
