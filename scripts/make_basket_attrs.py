"""Basket frozen snapshot'ının EKSİK sidecar attrs dosyasını üret (Aşama 6 denetimi, madde 2d).

Gerekçe
-------
`register_splits.py` tek varlıklarda `*_frozen.attrs.json` sidecar'ını işlenmiş
katmandan KOPYALAR (_freeze, satır ~284); `build_basket_split` ise basket
parquet'ini yazar ama sidecar ÜRETMEZ. Bu yüzden 5 frozen snapshot'ın 4'ünde
attrs varken `bist30_basket_4h_frozen.attrs.json` yoktu.

Bu script o dosyayı DETERMİNİSTİK olarak üretir:

    girdiler : configs/splits_preregistered.yaml  (bist30_basket bölümü)
               data/frozen/bist30_basket_4h_frozen.parquet   (YALNIZ OKUNUR)
               data/processed/bist30/<SYM>_4h_adjusted.attrs.json  (28 sidecar)
    çıktı    : data/frozen/bist30_basket_4h_frozen.attrs.json

Kurallar
--------
* Zaman damgası/üretilme tarihi İÇERMEZ -> aynı girdiler bayt-bayt aynı çıktıyı
  verir (`tests/test_basket_attrs.py` kilitler).
* Frozen parquet ASLA yazılmaz (sha256 kilidi, H17). Script yalnız okur.
* `--check`: dosyayı YAZMAZ; mevcut sidecar ile yeniden üretim bayt-bayt
  aynı mı doğrular (farklı/eksik ise exit 1).

Çalıştırma:  python3 scripts/make_basket_attrs.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict

import pandas as pd
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROZEN_PARQUET = os.path.join(ROOT, "data", "frozen", "bist30_basket_4h_frozen.parquet")
FROZEN_ATTRS = os.path.join(ROOT, "data", "frozen", "bist30_basket_4h_frozen.attrs.json")
SPLITS_YAML = os.path.join(ROOT, "configs", "splits_preregistered.yaml")
PROC_DIR = os.path.join(ROOT, "data", "processed", "bist30")

# hisse sidecar'larından TOPLANAN bayrak sayıları (tam geçmiş üzerinden;
# frozen basket penceresiyle SINIRLI DEĞİLDİR — çıktıdaki notta da yazar)
_SUM_KEYS = ("non_tradable_bars", "return_invalid_bars", "corporate_action_marked_bars",
             "halt_or_limit_bars", "outage_resumption_bars", "thin_bars",
             "roll_flagged_bars", "bad_print_flagged_bars")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_attrs() -> Dict[str, Any]:
    """Tüm sidecar içeriğini mevcut kaynaklardan deterministik olarak kur."""
    with open(SPLITS_YAML, "r", encoding="utf-8") as fh:
        pre = yaml.safe_load(fh)
    b = pre["bist30_basket"]

    df = pd.read_parquet(FROZEN_PARQUET)          # YALNIZ OKUMA
    ts = pd.to_datetime(df["timestamp_utc"], utc=True)
    stocks = sorted(df["stock"].unique().tolist())

    per_stock_rows = {s: int(v) for s, v in df["stock"].value_counts().items()}
    per_stock_rows = {s: per_stock_rows[s] for s in stocks}

    sums: Dict[str, int] = {k: 0 for k in _SUM_KEYS}
    missing_sidecars = []
    for s in stocks:
        side = os.path.join(PROC_DIR, f"{s}_4h_adjusted.attrs.json")
        if not os.path.exists(side):
            missing_sidecars.append(s)
            continue
        with open(side, "r", encoding="utf-8") as fh:
            a = json.load(fh)
        for k in _SUM_KEYS:
            sums[k] += int(a.get(k, 0))

    attrs: Dict[str, Any] = {
        "type": "basket_frozen_snapshot_attrs",
        "name": b.get("name", "bist30_basket"),
        "asset": b.get("asset", "BIST30_BASKET"),
        "timeframe": b.get("timeframe", "4h"),
        "schema_note": ("frozen basket snapshot 3 kolonlu TAKVİM/TRADE-EDİLEBİLİRLİK "
                        "tablosudur: stock, timestamp_utc, tradable (OHLCV İÇERMEZ; "
                        "fiyat verisi hisse başına data/processed/bist30/ katmanında)"),
        "policy_version": pre.get("policy_version"),
        "universe_version": b.get("universe_version"),
        "weighting": b.get("weighting"),
        "signal_level": b.get("signal_level"),
        "rows": int(len(df)),
        "n_stocks": int(len(stocks)),
        "stock_list": stocks,
        "excluded_from_basket": list(b.get("excluded_from_basket", [])),
        "per_stock_rows": per_stock_rows,
        "tradable_rows": int(pd.to_numeric(df["tradable"], errors="coerce").fillna(False).astype(bool).sum()),
        "common_window_start_utc": str(ts.min()),
        "common_window_end_utc": str(ts.max()),
        "grid_bars": b.get("grid_bars"),
        "frozen_file": "data/frozen/bist30_basket_4h_frozen.parquet",
        "frozen_sha256": _sha256(FROZEN_PARQUET),
        "frozen_sha256_matches_prereg": _sha256(FROZEN_PARQUET) == b.get("frozen_sha256"),
        "per_stock_flag_sums_full_history": dict(sorted(sums.items())),
        "per_stock_flag_sums_note": ("toplamlar 28 hissenin data/processed/bist30/*_adjusted.attrs.json "
                                     "sidecar'larından; TAM işlenmiş geçmiş üzerinden, frozen ortak "
                                     "pencereyle sınırlı değildir"),
        "missing_stock_sidecars": missing_sidecars,
        "generated_by": "scripts/make_basket_attrs.py (deterministik; tarih damgası içermez)",
        "sources": ["configs/splits_preregistered.yaml -> bist30_basket",
                    "data/frozen/bist30_basket_4h_frozen.parquet (read-only)",
                    "data/processed/bist30/<SYM>_4h_adjusted.attrs.json"],
    }
    return attrs


def dumps(attrs: Dict[str, Any]) -> str:
    return json.dumps(attrs, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="yazma; mevcut sidecar yeniden üretimle bayt-bayt aynı mı doğrula")
    ap.add_argument("--out", default=FROZEN_ATTRS, help="çıktı yolu (varsayılan: frozen sidecar)")
    args = ap.parse_args(argv)

    payload = dumps(build_attrs())
    if args.check:
        if not os.path.exists(args.out):
            print(f"CHECK FAIL: sidecar yok: {args.out}")
            return 1
        with open(args.out, "r", encoding="utf-8") as fh:
            existing = fh.read()
        if existing != payload:
            print(f"CHECK FAIL: {args.out} deterministik yeniden üretimle AYNI DEĞİL")
            return 1
        print(f"CHECK OK: {args.out} deterministik üretimle bayt-bayt aynı")
        return 0
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(payload)
    print(f"YAZILDI: {args.out} ({len(payload)} bayt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
