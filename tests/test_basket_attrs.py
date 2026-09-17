"""Tests for scripts/make_basket_attrs.py (Aşama 6 denetimi, madde 2d).

Kilitlenen garantiler:
  * üretim DETERMİNİSTİK: aynı girdiler -> bayt-bayt aynı sidecar
  * commit'lenmiş sidecar yeniden üretimle birebir aynı (--check bunu korur)
  * rows / stock_list / tradable_rows frozen parquet'in GERÇEK içeriğiyle uyumlu
  * frozen_sha256 hem dosyaya hem splits_preregistered.yaml kilidine eşit (H17)
  * per-stock bayrak toplamları 28 sidecar'ın bağımsız yeniden toplamıyla eşit
  * --check modu: bozulmuş/eksik sidecar'da exit 1 (sessiz geçiş yok)

Run: python3 -W ignore tests/test_basket_attrs.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import make_basket_attrs as MBA  # noqa: E402


def test_regeneration_is_byte_identical() -> None:
    a = MBA.dumps(MBA.build_attrs())
    b = MBA.dumps(MBA.build_attrs())
    assert a == b, "üretim deterministik değil"


def test_committed_sidecar_matches_regeneration() -> None:
    assert os.path.exists(MBA.FROZEN_ATTRS), "sidecar commit'lenmemiş: önce script çalıştırılmalı"
    with open(MBA.FROZEN_ATTRS, "r", encoding="utf-8") as fh:
        existing = fh.read()
    assert existing == MBA.dumps(MBA.build_attrs()), "sidecar yeniden üretimle aynı değil"


def test_rows_and_stocks_match_frozen_parquet() -> None:
    attrs = MBA.build_attrs()
    df = pd.read_parquet(MBA.FROZEN_PARQUET)
    assert attrs["rows"] == len(df)
    assert attrs["stock_list"] == sorted(df["stock"].unique().tolist())
    assert attrs["n_stocks"] == df["stock"].nunique() == 28
    trad = pd.to_numeric(df["tradable"], errors="coerce").fillna(False).astype(bool).sum()
    assert attrs["tradable_rows"] == int(trad)
    assert sum(attrs["per_stock_rows"].values()) == len(df)


def test_frozen_sha256_matches_file_and_prereg_lock() -> None:
    import yaml
    attrs = MBA.build_attrs()
    sha = MBA._sha256(MBA.FROZEN_PARQUET)
    with open(MBA.SPLITS_YAML, "r", encoding="utf-8") as fh:
        pre = yaml.safe_load(fh)
    assert attrs["frozen_sha256"] == sha
    assert pre["bist30_basket"]["frozen_sha256"] == sha, "H17 kilidi kırık"
    assert attrs["frozen_sha256_matches_prereg"] is True


def test_aggregates_match_independent_recount() -> None:
    attrs = MBA.build_attrs()
    df = pd.read_parquet(MBA.FROZEN_PARQUET, columns=["stock"])
    stocks = sorted(df["stock"].unique().tolist())
    recount = {k: 0 for k in MBA._SUM_KEYS}
    for s in stocks:
        side = os.path.join(MBA.PROC_DIR, f"{s}_4h_adjusted.attrs.json")
        assert os.path.exists(side), f"hisse sidecar'ı yok: {s}"
        with open(side, "r", encoding="utf-8") as fh:
            a = json.load(fh)
        for k in MBA._SUM_KEYS:
            recount[k] += int(a.get(k, 0))
    assert attrs["per_stock_flag_sums_full_history"] == dict(sorted(recount.items()))
    assert attrs["missing_stock_sidecars"] == []


def test_check_mode_fails_on_missing_or_tampered() -> None:
    assert MBA.main(["--check"]) == 0, "--check mevcut sidecar'da 0 dönmeli"
    with tempfile.TemporaryDirectory() as td:
        bad = os.path.join(td, "tampered.attrs.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write('{"rows": 1}')
        assert MBA.main(["--check", "--out", bad]) == 1, "bozuk sidecar'da --check 1 dönmeli"
        missing = os.path.join(td, "yok.json")
        assert MBA.main(["--check", "--out", missing]) == 1, "eksik sidecar'da --check 1 dönmeli"


def _run_all() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {fn.__name__}: {exc}")
        except Exception as exc:                                     # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
