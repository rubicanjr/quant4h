"""Tests for M14-VIZ2 — multi pine yapısal parite testleri (renderer/üretici tarafı).

Pine derlemesi bu ortamda doğrulanamaz (UNTESTED-VIZ); burada ÜRETİCİnin
yapısal garantileri kilitlenir: 4 gömülü blok × tanım tekilliği, trade dizisi
paritesi (CSV satır sayısı), sabit banner iğneleri, strategy/alert yasağı,
BIST30 trade-review YOK, SADE MOD varsayılan toggle'ları.

Run: python3 -W ignore tests/test_viz_multi.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MULTI = os.path.join(ROOT, "viz", "quant4h_viz_multi_2026-09.pine")


def _read() -> str:
    assert os.path.exists(MULTI), "multi pine yok — export_viz_payload.py koşulmalı"
    with open(MULTI, encoding="utf-8") as fh:
        return fh.read()


def test_multi_blocks_and_declaration_uniqueness() -> None:
    t = _read()
    for pre in ("a0_", "a1_", "a2_", "a3_"):
        for name in ("ts", "ema200", "stopLong", "sigLong", "sigPrice",
                     "trETs", "trEPx", "trXTs", "trXPx", "trR", "payloadOK"):
            n = len(re.findall(rf"^{re.escape(pre + name)}\s*=", t, re.M))
            assert n == 1, f"{pre}{name} x{n}"
    assert t.count("indicator(") == 1


def test_trade_array_parity_with_csv() -> None:
    t = _read()
    for pre, key in (("a0_", "BTC"), ("a1_", "GOLD"), ("a2_", "SILVER"), ("a3_", "BIST30")):
        m_new = re.search(rf"^{pre}trETs  = array\.new<int>\(\)$", t, re.M)
        m = re.search(rf"^{pre}trETs  = array\.from<int>\((.*?)\)$", t, re.M | re.S)
        assert m_new or m, f"{pre}trETs yok"
        n = 0 if m_new else m.group(1).count(",") + 1
        csv = os.path.join(ROOT, "reports", f"trades_{key}.csv")
        rows = len(pd.read_csv(csv)) if os.path.exists(csv) else 0
        assert n == rows, f"{key}: pine {n} != csv {rows}"


def test_fixed_banners_and_simple_mode_defaults() -> None:
    t = _read()
    for needle in ("UNTESTED-VIZ", "PAYLOAD YOK", "watch_only",
                   "AL koşulu oluştu (sinyal kaydı)", "SAT koşulu (sinyal kaydı)",
                   "doğruluk kaynağı DEĞİL", "payload ufku"):
        assert needle in t, f"banner iğnesi eksik: {needle}"
    assert 'simple_mode = input.bool(true' in t, "SADE MOD varsayılan TRUE olmalı"
    assert 'show_ema    = input.bool(false' in t
    assert 'show_levels = input.bool(false' in t
    assert 'show_trades = input.bool(false' in t, "TRADE-REVIEW toggle'lı, varsayılan kapalı"
    code = "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("//"))
    assert "strategy(" not in code and "alertcondition(" not in code
    assert not re.search(r"^\s*alert\(", code, re.M)


def test_bist30_block_has_no_trade_review() -> None:
    t = _read()
    m = re.search(r"^a3_trR    = array\.new<float>\(\)$", t, re.M)
    assert m, "BIST30 trade-review dizileri BOŞ (array.new) olmalı"
    assert not re.search(r"array\.from<[^>]+>\(\s*\)", t), "boş array.from KALMIŞ (M15)"


def test_exporter_regenerates_multi_deterministically() -> None:
    with tempfile.TemporaryDirectory() as td:
        r1 = subprocess.run([sys.executable, "-W", "ignore",
                             os.path.join(ROOT, "scripts", "export_viz_payload.py"),
                             "--out", td],
                            capture_output=True, text=True, cwd=ROOT)
        assert r1.returncode == 0, r1.stderr[-500:]
        a = open(os.path.join(td, "quant4h_viz_multi_2026-09.pine"), encoding="utf-8").read()
        b = _read()
        # üretim zaman damgası yok → bayt-bayt determinizm
        assert a == b, "multi pine deterministik değil"


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
