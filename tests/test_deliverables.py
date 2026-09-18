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
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _read(rel: str) -> str:
    p = os.path.join(ROOT, rel)
    assert os.path.exists(p), f"EKSİK teslim: {rel}"
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def _normalize_hash(data: bytes) -> str:
    """İçerik-normalize sha256 (maint M7): UTF-8 BOM soyulur, CRLF→LF.
    `final_verdict.md`'deki kayıtlı hash'ler LF içerik üzerinden üretilmiştir
    (dokunulmaz); normalize okuma testi platform-bağımsız yapar — Windows
    CRLF checkout'unda da aynı hash çıkar (yerel-kırmızı/CI-yeşil vakasının kökü)."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _sha(rel: str) -> str:
    p = os.path.join(ROOT, rel)
    with open(p, "rb") as fh:
        return _normalize_hash(fh.read())


def test_final_verdict_content_and_live_hashes() -> None:
    doc = _read("reports/final_verdict.md")
    for needle in ("GEÇTİ = 0", "watch_only", "KALDI", "ZAYIF (örneklem)",
                   "ölüm nedeni", "EDGE", "ÖRNEKLEM", "look sayısı (TEST)",
                   "P2xA2", "TEST KOŞULMADI", "bir bakış daha"):
        assert needle in doc, f"final_verdict'te yok: {needle!r}"
    # belge hash'leri GERÇEK dosyalara bağlı (canlı doğrulama; normalize sha — M7)
    sel_sha = _sha("configs/selected_cells.yaml")
    splits_sha = _sha("configs/splits_preregistered.yaml")
    assert sel_sha in doc, ("selected_cells.yaml sha256 final_verdict'te değil/bayat — "
                            f"hesaplanan(normalize)={sel_sha} · beklenen=doc'ta kayıtlı "
                            f"sha256 (LF üzerinden, dokunulmaz)")
    assert splits_sha in doc, ("splits yaml sha256 final_verdict'te değil/bayat — "
                               f"hesaplanan(normalize)={splits_sha} · beklenen=doc'ta kayıtlı sha256")


def test_sha_normalization_crlf_bom_regression() -> None:
    """REGRESYON (maint M7 + M8 yeniden tasarım): platform-bağımsız hash zinciri.

    M8 gerekçesi: kaynak içeriğin working-tree'den okunup "kaynak LF" assert
    edilmesi smudge durumuna bağlıydı — Windows + OneDrive smudge'ında dosya
    CRLF yazılabiliyor (kanıt: `checkout-index -a -f` sonrası working tree
    CRLF, `git status` TEMİZ, blob LF). Bu yüzden:
      (a) kaynak içerik working tree'den DEĞİL **git blob'undan** okunur
          (`git show HEAD:configs/selected_cells.yaml`, bayt olarak) ve
          blob sha256 == final_verdict.md kayıtlı hash (LF, dokunulmaz) assert edilir;
      (b) CRLF+BOM normalizasyon assert'i SENTETİK tmp kopya üzerinde kalır
          (gerçek regresyon niyeti budur; fixture bayatlarsa test patlar);
      (c) working-tree smudge durumu assert DEĞİL, INFO rapor satırıdır
          (canlı dosyanın normalize hash kilidi ayrıca
          `test_final_verdict_content_and_live_hashes` içindedir).
    Not: test bir git checkout'ta koşmayı gerektirir (CI'da her zaman geçerli).
    """
    doc = _read("reports/final_verdict.md")
    # (a) otorite = git blob (smudge'dan bağımsız)
    blob = subprocess.run(["git", "show", "HEAD:configs/selected_cells.yaml"],
                          cwd=ROOT, capture_output=True, check=True).stdout
    blob_sha = hashlib.sha256(blob).hexdigest()
    assert blob_sha in doc, ("blob sha256 final_verdict'te değil/bayat — "
                             f"hesaplanan(blob)={blob_sha} · beklenen=doc'ta kayıtlı sha256 (LF)")
    # (b) sentetik CRLF+BOM kopya (kaynak: blob) → normalize sha == blob/doc hash
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "selected_cells.crlf.bom.yaml")
        crlf = b"\xef\xbb\xbf" + blob.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        with open(p, "wb") as fh:
            fh.write(crlf)
        with open(p, "rb") as fh:
            data = fh.read()
        # fixture gerçekten CRLF+BOM mu (testin kendisi bayatlamasın)
        assert data.startswith(b"\xef\xbb\xbf") and data.count(b"\r\n") > 100
        got = _normalize_hash(data)
        assert got == blob_sha, ("CRLF+BOM normalize sha uyuşmadı — "
                                 f"hesaplanan={got} · beklenen(blob/doc LF)={blob_sha}")
        # normalize EDİLMEMİŞ hash farklıdır → normalizasyon gerçekten şart
        assert hashlib.sha256(data).hexdigest() != blob_sha
    # (c) working-tree smudge durumu: YALNIZ BİLGİ (assert değil)
    with open(os.path.join(ROOT, "configs", "selected_cells.yaml"), "rb") as fh:
        wt = fh.read()
    eol = "CRLF içeriyor" if b"\r\n" in wt else "saf LF"
    bom = "BOM var" if wt.startswith(b"\xef\xbb\xbf") else "BOM yok"
    print(f"INFO  working-tree smudge: {eol} · {bom} · "
          f"normalize(sha) == blob(sha): {_normalize_hash(wt) == blob_sha}")


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
                   "225/225", "Veri provenansı ve ToS notu"):
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
