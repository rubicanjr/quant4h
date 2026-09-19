"""Tests for M15 — üreteç golden-file + lint kural testleri.

GOLDEN-FILE: dondurulmuş fixture (checkpoint verisi) üzerinde üreteç çıktısı
.pine dosyaları BAYT-BAYT golden ile eşleşmelidir. Golden'lar TÜRETİLMİŞTİR
(veri restore'unda yeniden üretilir):
    python3 scripts/export_viz_payload.py --out tests/fixtures/_gen
    cp tests/fixtures/_gen/quant4h_viz_multi_2026-09.pine tests/fixtures/golden_viz_multi.pine
    cp tests/fixtures/_gen/quant4h_viz_BTC_2026-09.pine  tests/fixtures/golden_viz_BTC.pine

LİNT KURALLARI (M15): array.from >=1 arg ZORUNLU (boş küme -> array.new) ·
dizi uzunlukları == ts uzunluğu · strategy(/alert( yok · PAYLOAD-BEGIN/END
dengeli · boş dizi -> array.new. Pencere: --bars varsayılan 750 (varlık veri
tavanı + kaynak bütçesi 90 KB ile sınırlı; multi oto-daraltır).

Run: python3 -W ignore tests/test_viz_generator.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import export_viz_payload as E  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FIX = os.path.join(ROOT, "tests", "fixtures")
GOLD_MULTI = os.path.join(FIX, "golden_viz_multi.pine")
GOLD_BTC = os.path.join(FIX, "golden_viz_BTC.pine")


def _gen() -> str:
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, "-W", "ignore",
                            os.path.join(ROOT, "scripts", "export_viz_payload.py"),
                            "--out", td], capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, r.stderr[-800:]
        return td, {f: open(os.path.join(td, f), encoding="utf-8").read()
                    for f in os.listdir(td)}


def test_golden_multi_bytes_match() -> None:
    _, out = _gen()
    golden = open(GOLD_MULTI, encoding="utf-8").read()
    assert out["quant4h_viz_multi_2026-09.pine"] == golden, \
        "multi pine golden'dan sapmış (üreteç/veri değişimi) — golden'ı bilinçli yenile"


def test_golden_btc_bytes_match() -> None:
    _, out = _gen()
    golden = open(GOLD_BTC, encoding="utf-8").read()
    assert out["quant4h_viz_BTC_2026-09.pine"] == golden, \
        "BTC pine golden'dan sapmış — golden'ı bilinçli yenile"


def test_lint_rules_hold_on_generated() -> None:
    _, out = _gen()
    txt = out["quant4h_viz_multi_2026-09.pine"]
    E.lint_multi(txt)                                   # deklarasyon + banner + ortak
    E._lint_common(txt, ("a0_", "a1_", "a2_", "a3_"))   # uzunluk/denge/boş-from/yasak
    assert not re.search(r"array\.from<[^>]+>\(\s*\)", txt), "boş array.from yasak"
    assert txt.count("PAYLOAD-BEGIN") == txt.count("PAYLOAD-END") == 4


def test_window_default_and_budget() -> None:
    _, out = _gen()
    btc = out["quant4h_viz_BTC_2026-09.pine"]
    mts = re.search(r"^f_ts\(\) => array\.from<int>\(([^\n]*)\)$", btc, re.M)
    assert mts, "ts dizisi bulunamadı"
    n_ts = mts.group(1).count(",") + 1
    assert n_ts == E.DEFAULT_BARS, f"varsayılan pencere {E.DEFAULT_BARS} bar olmalı, {n_ts}"
    assert len(btc.encode("utf-8")) < E.BUDGET_BYTES, "tek dosya bütçeyi aşmış"
    multi = out["quant4h_viz_multi_2026-09.pine"]
    mm = re.search(r"^f_a0_ts\(\) => array\.from<int>\(([^\n]*)\)$", multi, re.M)
    n_multi = mm.group(1).count(",") + 1
    assert 200 <= n_multi <= E.DEFAULT_BARS, f"multi pencere beklenmedik: {n_multi}"
    assert len(multi.encode("utf-8")) < E.BUDGET_BYTES, "multi bütçeyi aşmış"


def test_descope_no_trade_arrays_generated() -> None:
    _, out = _gen()
    for name in ("multi", "BTC"):
        f = out[f"quant4h_viz_{name}_2026-09.pine"] if name != "multi" else out["quant4h_viz_multi_2026-09.pine"]
        for needle in ("trETs", "trEPx", "trXTs", "trXPx", "label.new", "cumR"):
            assert needle not in f, f"{name}: descope ihlali {needle}"
        assert not re.search(r"array\.from<[^>]+>\(\s*\)", f), f"{name}: boş array.from"
        assert not re.search(r"^[A-Za-z_]\w*\s*=\s*array\.from<", f, re.M), \
            f"{name}: main body'de dizi literal'i (T15/M23)"


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
