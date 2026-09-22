"""Tests for M14/M21 — multi pine yapısal testleri (DESCOPE sonrası).

M21 ile trade-review overlay KALDIRILDI: trade dizileri (trETs/trEPx/trXTs/
trXPx/trR), R etiketleri, kümülatif R ve TRADE-REVIEW toggle ÜRETİLMEZ.
Kalan: giriş/çıkış marker'ları (▲/✖ = sinyal kaydı, close'a çizilir) +
EMA200/seviyeler toggle'ları + SABİT banner. Trade verisi KAYBEDİLMEDİ:
kaynak = reports/trades_*.csv (durur).

Run: python3 -W ignore tests/test_viz_multi.py
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MULTI = os.path.join(ROOT, "viz", "quant4h_viz_multi_2026-09.pine")
FUNC = ("ts", "ema200", "stopLong", "swingLow", "swingHigh",
        "donHigh", "donLow", "sigLong", "sigShort")


def _read() -> str:
    if not os.path.exists(MULTI):
        # M18 (EKİM MAINT): viz/ çıktıları untracked — test kendi girdisini üretir
        import subprocess
        r = subprocess.run([sys.executable, "-W", "ignore",
                            os.path.join(ROOT, "scripts", "export_viz_payload.py"),
                            "--out", os.path.join(ROOT, "viz")],
                           capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, r.stderr[-800:]
    assert os.path.exists(MULTI), "multi pine yok — export_viz_payload.py koşulmalı"
    with open(MULTI, encoding="utf-8") as fh:
        return fh.read()


def test_multi_blocks_and_declaration_uniqueness() -> None:
    t = _read()
    for pre in ("a0_", "a1_", "a2_", "a3_"):
        for name in FUNC:
            n = len(re.findall(rf"^f_{re.escape(pre)}{name}\(\)\s*=>", t, re.M))
            assert n == 1, f"f_{pre}{name} x{n}"
        for name in ("payloadMeta", "payloadOK"):
            n = len(re.findall(rf"^{re.escape(pre)}{name}\s*=", t, re.M))
            assert n == 1, f"{pre}{name} x{n}"
    assert t.count("indicator(") == 1


def test_no_array_literals_in_main_body() -> None:
    t = _read()
    assert not re.search(r"^[A-Za-z_]\w*\s*=\s*array\.from<", t, re.M), \
        "M23/T15: dizi literal'i main body'de tanımlanamaz"
    assert "m_ts := f_a0_ts()" in t and "m_sigS := f_a3_sigShort()" in t


def test_descope_no_trade_review_artifacts() -> None:
    t = _read()
    for needle in ("trETs", "trEPx", "trXTs", "trXPx", "trR ", "label.new",
                   "cumR", "show_trades", "sigPrice"):
        assert needle not in t, f"descope ihlali: {needle!r} hâlâ üretiliyor"
    # marker'lar	close'a çizilir (sinyal kaydı)
    assert "sigL == 1 ? close : na" in t and "sigS == 1 ? close : na" in t
    assert "AL koşulu oluştu (sinyal kaydı)" in t and "SAT koşulu (sinyal kaydı)" in t
    # trade verisi kaybedilmedi: kaynak CSV'ler duruyor
    for k, n in (("BTC", 187), ("GOLD", 30), ("SILVER", 34)):
        p = os.path.join(ROOT, "reports", f"trades_{k}.csv")
        assert os.path.exists(p), f"kaynak CSV eksik: {p}"
        with open(p, encoding="utf-8") as fh:
            assert sum(1 for _ in fh) - 1 == n, f"{k} CSV satır sayısı değişti"


def test_fixed_banners_and_toggle_defaults() -> None:
    t = _read()
    for needle in ("UNTESTED-VIZ", "PAYLOAD YOK", "watch_only",
                   "doğruluk kaynağı DEĞİL", "payload ufku",
                   "marker'lar SİNYAL kaydıdır"):
        assert needle in t, f"banner iğnesi eksik: {needle}"
    assert 'show_ema    = input.bool(false' in t
    assert 'show_levels = input.bool(false' in t
    assert "show_trades" not in t and "simple_mode" not in t
    code = "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("//"))
    assert "strategy(" not in code and "alertcondition(" not in code
    assert not re.search(r"^\s*alert\(", code, re.M)


def test_symbol_mapping_and_payload_guard() -> None:
    t = _read()
    for sym in ("BTCUSDT", "GC1!", "GC=F", "XAUUSD", "SI1!", "SI=F", "XAGUSD", "XU030"):
        assert sym in t, f"sembol eşlemesi eksik: {sym}"
    assert "active = isBTC ? 0 : isGOLD ? 1 : isSILV ? 2 : isBIST ? 3 : -1" in t


def test_markers_use_close_not_payload_price() -> None:
    t = _read()
    assert "plotshape(sigL == 1 ? close : na" in t
    assert "plotshape(sigS == 1 ? close : na" in t
    assert "m_sigPx" not in t and "sigPx" not in t


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
