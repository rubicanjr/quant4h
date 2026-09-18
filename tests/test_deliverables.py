"""Tests for AŞAMA 11 — teslim artefaktları (final_verdict + model_card + runbook + README).

Kilitlenen garantiler:
  * üç teslim belgesi + README kapanış bölümü MEVCUT ve zorunlu içeriklerle dolu
  * final_verdict'teki seçim/split hash'leri GERÇEK dosyaların sha256'sı ile birebir
    (belge, artefakta canlı bağlı — hash kırılırsa test patlar)
  * look log'u ilk kaydı Aşama 9 hükmüyle tutarlı (look=1, TEST yalnız GOLD/SILVER)
  * watch_only / ML gate KAPALI / canlı emir YOK ifadeleri bağlayıcı belgelerde geçer
  * runbook protokol değişmezleri: maks 4 look/yıl, ön-kayıt zorunlu, ihlal tanımı

Run: python3 -W ignore tests/test_deliverables.py
"""
from __future__ import annotations

import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _read(rel: str) -> str:
    p = os.path.join(ROOT, rel)
    assert os.path.exists(p), f"EKSİK teslim: {rel}"
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def _sha(rel: str) -> str:
    h = hashlib.sha256()
    with open(os.path.join(ROOT, rel), "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def test_final_verdict_content_and_live_hashes() -> None:
    doc = _read("reports/final_verdict.md")
    for needle in ("GEÇTİ = 0", "watch_only", "KALDI", "ZAYIF (örneklem)",
                   "ölüm nedeni", "EDGE", "ÖRNEKLEM", "look sayısı (TEST)",
                   "P2xA2", "TEST KOŞULMADI", "bir bakış daha"):
        assert needle in doc, f"final_verdict'te yok: {needle!r}"
    # belge hash'leri GERÇEK dosyalara bağlı (canlı doğrulama)
    sel_sha = _sha("configs/selected_cells.yaml")
    splits_sha = _sha("configs/splits_preregistered.yaml")
    assert sel_sha in doc, "selected_cells.yaml sha256 final_verdict'te değil/bayat"
    assert splits_sha in doc, "splits yaml sha256 final_verdict'te değil/bayat"


def test_final_verdict_per_asset_verdicts() -> None:
    doc = _read("reports/final_verdict.md")
    for needle in ("| **BTC** |", "| **GOLD** |", "| **SILVER** |", "| **BIST30 sepet** |"):
        assert needle in doc, f"varlık satırı yok: {needle}"
    # BTC ve basket: EDGE ölümü (VALID negatif); GOLD/SILVER: ÖRNEKLEM
    assert "VALID beklenen değeri NEGATİF" in doc
    assert "OOS n=16 < min 100" in doc and "OOS n=19 < min 100" in doc


def test_model_card_what_it_is_and_is_not() -> None:
    doc = _read("models/model_card.md")
    for needle in ("Bu sistem NEDİR", "Bu sistem NE DEĞİLDİR",
                   "watch_only TANIMI", "ml_policy_gate: **KAPALI**",
                   "Canlı işlem sistemi DEĞİLDİR", "Yatırım tavsiyesi DEĞİLDİR",
                   "Kanıtlanmış edge DEĞİLDİR", "GEÇTİ=0",
                   "yatırım tavsiyesi değildir"):
        assert needle in doc, f"model_card'da yok: {needle!r}"


def test_runbook_protocol_invariants() -> None:
    doc = _read("ops_runbook.md")
    for needle in ("watch_only", "trade YOK", "AYLIK SİNYAL İZLEME",
                   "maksimum 4 look", "ÖN-KAYIT", "policy_version",
                   "LOOK LOG", "PROTOKOL İHLALİ", "HÜKÜMSÜZDÜR",
                   "YENİ PROJE", "erken look YASAK".upper(),
                   # v1.2 (maint M3, 2026-09-17): alpha-spending + universe + raw-drift
                   "ALPHA-SPENDING TARİFESİ", "%97.5", "%99",
                   "ÜNİVERSE DONDURMA", "üyelik değişim logu", "Raw hash logu"):
        assert needle.upper() in doc.upper(), f"runbook'ta yok: {needle!r}"
    # look log ilk kayıt: Aşama 9 hükmüyle tutarlı
    assert "2026-09-17" in doc and "GEÇTİ=0" in doc
    assert "GOLD, SILVER" in doc and "KOŞULMADI" in doc
    # alpha-spending: look 1-4 %95 bandı Aşama 9 (look #1) ile tutarlı olmalı
    assert "1–4" in doc and "%95" in doc


def test_readme_research_closed_section() -> None:
    doc = _read("README.md")
    for needle in ("ARAŞTIRMA-KAPALI", "watch_only", "GEÇTİ = 0",
                   "Bu repo neyi KANITLADI", "Kanıtlanmadı (edge)",
                   "final_verdict.md", "model_card.md", "ops_runbook.md",
                   "224/224", "Veri provenansı ve ToS notu"):
        assert needle in doc, f"README'de yok: {needle!r}"


def test_verdict_documents_match_stage9_json() -> None:
    import json
    v = json.load(open(os.path.join(ROOT, "reports", "stage9_oos_verdict.json"),
                       encoding="utf-8"))
    doc = _read("reports/final_verdict.md")
    assert v["assets"]["BTC"]["verdict"] == "KALDI" and "BTC" in doc
    assert v["assets"]["GOLD"]["verdict"].startswith("ZAYIF")
    assert v["assets"]["SILVER"]["verdict"].startswith("ZAYIF")
    assert v["assets"]["BIST30_BASKET"]["verdict"] == "KALDI"
    assert v["assets"]["BTC"]["test"] is None          # TEST koşulmadı kaydı
    assert v["assets"]["BIST30_BASKET"]["test"] is None
    assert "16" in doc and "19" in doc                 # GOLD/SILVER OOS n


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
