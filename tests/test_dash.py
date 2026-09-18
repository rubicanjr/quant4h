"""Tests for M11-DASH — panel snapshot testleri (checkpoint frame'leri + sabit 'now').

Yöntem: renderer deterministik olduğu için "snapshot" = aynı sabit `now` ile
iki render'ın BAYT-BAYT aynı olması + panel/boundary iğneleri + yan-etki
yokluğu (state/QC dosyaları değişmez) + ağ varsayılan KAPALI.
Görsel golden-file TUTULMAZ (veri restore'larında kırılgan olurdu); determinizm
+ iğneler snapshot sözleşmesidir.

Run: python3 -W ignore tests/test_dash.py
"""
from __future__ import annotations

import hashlib
import inspect
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import run_dash as D  # noqa: E402

FIXED_NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def test_render_deterministic_snapshot() -> None:
    a = D.render_once(now=FIXED_NOW)
    b = D.render_once(now=FIXED_NOW)
    assert a == b, "render deterministik değil (snapshot sözleşmesi)"
    ha = hashlib.sha256(a.encode()).hexdigest()
    assert ha == hashlib.sha256(b.encode()).hexdigest()
    assert len(a) > 800, "render boş/çorak"


def test_panels_and_watch_only_boundaries_present() -> None:
    t = D.render_once(now=FIXED_NOW)
    for needle in ("watch_only", "EYLEM: YOK", "REJİM / BAĞLAM", "SEVİYE + MOMENTUM",
                   "SİNYAL log", "CADENCE", "LOOK TAKVİMİ",
                   "BTC", "GOLD", "SILVER", "BIST30",
                   "tavsiye YOK", "emir YOK", "ağ: KAPALI"):
        assert needle in t, f"panel/iğne eksik: {needle!r}"


def test_look_countdown_math() -> None:
    t = D.render_once(now=datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc))
    assert "46 gün" in t, "2026-11-01 → 2026-12-17 = 46 gün"
    t2 = D.render_once(now=datetime(2026, 12, 20, 9, 0, tzinfo=timezone.utc))
    assert "0 gün" in t2, "geçmiş tarih -> 0 (negatif gösterilmez)"


def test_render_has_no_side_effects_on_state() -> None:
    p_state = os.path.join(D.ROOT, "reports", "cadence", ".state.json")
    p_qc = os.path.join(D.ROOT, "reports", "qc_report.json")

    def sha(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None

    s1, q1 = sha(p_state), sha(p_qc)
    D.render_once(now=FIXED_NOW)
    assert sha(p_state) == s1, "render state dosyasına yazdı (renderer salt-okunur olmalı)"
    assert sha(p_qc) == q1


def test_network_default_off_and_gated_fetch_path() -> None:
    assert D.NETWORK_DEFAULT is False
    src = inspect.getsource(D.main)
    assert "--fetch" in src and "maybe_fetch" in src and "FETCH_GATE_MIN" in src, \
        "fetch yolu rate kapısına bağlı olmalı (runbook §A-cadence)"


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
