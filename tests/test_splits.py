"""Tests for the split pre-registration (Aşama 1c).

The whole point of pre-registration is that it must be impossible to cheat by
accident, so these tests pin the structural guarantees:
  * train / valid / test never overlap in TIME
  * the purge + embargo gap really exists between the blocks
  * test is the MOST RECENT period
  * sample counts are computed on TRADABLE bars only
  * verify() detects a changed source file (sha256 mismatch)
  * an asset with too few bars is marked insufficient_for_oos
  * FROZEN SNAPSHOT DOKUNULMAZLIĞI (2026-09-17 onaylı bakım): hiçbir test
    gerçek `data/frozen/` altına YAZMAZ — build_split çağrıları tmp'ye
    yönlendirilir, tamper testleri TMP KOPYALAR üzerinde koşar (fake yaml'a
    mutlak yol yazılır; `os.path.join(ROOT, abs) == abs`). Her testin
    BAŞINDA ve SONUNDA frozen sha256 haritası assert edilir (runner guard).

Run: python3 -W ignore tests/test_splits.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

import pandas as pd
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import register_splits as RS  # noqa: E402

PREREG = os.path.join(RS.ROOT, "configs", "splits_preregistered.yaml")
FROZEN_DIR_REAL = os.path.join(RS.ROOT, "data", "frozen")


def _frozen_shas() -> dict:
    """Gerçek frozen snapshot'ların sha256 haritası (dokunulmazlık bekçisi)."""
    return {f: RS._sha256(os.path.join(FROZEN_DIR_REAL, f))
            for f in sorted(os.listdir(FROZEN_DIR_REAL)) if f.endswith(".parquet")}


_FROZEN_BASELINE = _frozen_shas()


def _doc() -> dict:
    assert os.path.exists(PREREG), f"{PREREG} yok - once scripts/register_splits.py calistirin"
    with open(PREREG, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --------------------------------------------------------------------------

def test_preregistration_file_is_valid_yaml_with_policy() -> None:
    doc = _doc()
    assert doc["policy_version"] == RS.POLICY_VERSION
    assert doc["policy"]["test_is_most_recent"] is True
    assert doc["policy"]["no_shuffle"] is True
    assert doc["policy"]["counting_basis"] == "tradable_bars_only"
    assert len(doc["hard_rules"]) >= 6
    assert set(doc["assets"]) == {"BTC", "GOLD", "SILVER", "BIST30"}
    for a, r in doc["assets"].items():
        assert r["frozen_sha256"] and len(r["frozen_sha256"]) == 64, a
        assert r["live_sha256_at_registration"] and len(r["live_sha256_at_registration"]) == 64, a
        assert os.path.exists(os.path.join(RS.ROOT, r["frozen_file"])), a


def test_blocks_never_overlap_and_purge_is_real() -> None:
    doc = _doc()
    purge, embargo = doc["policy"]["purge_bars"], doc["policy"]["embargo_bars"]
    for a, r in doc["assets"].items():
        tr, va, te = r["train"]["used"], r["valid"]["used"], r["test"]["used"]
        assert tr["n_raw"] > 0 and va["n_raw"] > 0 and te["n_raw"] > 0, a
        # zaman siralamasi: train < valid < test
        assert pd.Timestamp(tr["last_utc"]) < pd.Timestamp(va["first_utc"]), (a, "train/valid")
        assert pd.Timestamp(va["last_utc"]) < pd.Timestamp(te["first_utc"]), (a, "valid/test")
        # pozisyon bazinda purge+embargo boslugu GERCEKTEN var
        assert va["first_pos"] - tr["last_pos"] - 1 >= purge + embargo, (a, "train|valid purge")
        assert te["first_pos"] - va["last_pos"] - 1 >= purge + embargo, (a, "valid|test purge")


def test_test_is_the_most_recent_period() -> None:
    doc = _doc()
    for a, r in doc["assets"].items():
        src = os.path.join(RS.ROOT, r["live_file_at_registration"])
        df = pd.read_parquet(src)
        last = pd.to_datetime(df["timestamp_utc"], utc=True).max()
        assert pd.Timestamp(r["test"]["used"]["last_utc"]) <= last, a
        # test blogunun son bari verinin sonuna YAKIN olmali. Siki esik
        # kullanilamaz cunku son barlar non_tradable (henuz olusuyor / kesinti
        # devami / ince bar) olup sayimdan DUSULUYOR; metallerde tatil +
        # bakim molasi nedeniyle bu fark 1 gunu asabilir.
        delta = last - pd.Timestamp(r["test"]["used"]["last_utc"])
        assert pd.Timedelta(0) <= delta <= pd.Timedelta(hours=72), (a, delta)


def test_counts_exclude_non_tradable_bars() -> None:
    doc = _doc()
    for a, r in doc["assets"].items():
        assert r["rows_tradable"] + r["rows_non_tradable"] == r["rows_total"], a
        used = (r["train"]["used"]["n_raw"] + r["valid"]["used"]["n_raw"]
                + r["test"]["used"]["n_raw"])
        assert used <= r["rows_tradable"], (a, used, r["rows_tradable"])
    # BIST30: ince barlar artik HIC URETILMIYOR (min_source_bars_per_target=3),
    # bu yuzden non_tradable sayisi kucuktur ama SIFIR DEGILDIR (kesinti devam
    # barlari + henuz olusan bar). Asil iddia: sayimlar tutarli olmali.
    b = doc["assets"]["BIST30"]
    assert b["rows_non_tradable"] >= 1, b["rows_non_tradable"]
    assert b["rows_tradable"] == b["rows_total"] - b["rows_non_tradable"]
    # BTC'de de en az 'henuz olusan son bar' non_tradable olmali
    assert doc["assets"]["BTC"]["rows_non_tradable"] >= 1


def test_fixed_bar_policy_not_fractions() -> None:
    """Policy is fixed bar counts, so TEST size is comparable across assets
    (that was the whole point: metals have 4x less history than BTC)."""
    doc = _doc()
    tests = [r["test"]["raw"]["n_raw"] for r in doc["assets"].values()]
    assert max(tests) <= RS.POLICY["test_bars"]
    # BTC (19.9k) ile metaller (3.6k) ayni TEST bar sayisini almali
    assert doc["assets"]["BTC"]["test"]["raw"]["n_raw"] == \
           doc["assets"]["GOLD"]["test"]["raw"]["n_raw"]


def test_low_power_assets_are_warned() -> None:
    doc = _doc()
    for a, r in doc["assets"].items():
        joined = " ".join(r["warnings"])
        if r["test"]["calendar_days"] < doc["policy"]["min_test_calendar_days"]:
            assert "takvim günü" in joined, a
        if r["test"]["sessions"] < doc["policy"]["min_test_sessions"]:
            assert "İSTATİSTİKSEL GÜÇ" in joined, a
        if r["mode"] == "watch_only":
            assert "watch_only" in joined, a


def test_verify_detects_tampered_source() -> None:
    """If the underlying parquet changes, the pre-registration is INVALID and
    verify() must say so - that is what stops a silent re-split after results.

    2026-09-17 bakım: test GERÇEK frozen/live dosyalara ARTIK YAZMAZ. TMP
    kopyalar + fake yaml'a MUTLAK yollar yazılır (`os.path.join(ROOT, abs)`
    ROOT'u düşürür) — verify/drift_report aynı kod yoluyla tmp üzerinde koşar.
    """
    assert RS.verify(PREREG) == [], RS.verify(PREREG)
    tmp = tempfile.mkdtemp()
    try:
        with open(PREREG, "r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        btc = doc["assets"]["BTC"]
        real_frozen = os.path.join(RS.ROOT, btc["frozen_file"])
        real_live = os.path.join(RS.ROOT, btc["live_file_at_registration"])
        tmp_frozen = os.path.join(tmp, "btc_4h_frozen.parquet")
        tmp_live = os.path.join(tmp, "btc_live.parquet")
        shutil.copy(real_frozen, tmp_frozen)
        shutil.copy(real_live, tmp_live)
        btc["frozen_file"] = tmp_frozen                 # MUTLAK yol -> ROOT devre dışı
        btc["live_file_at_registration"] = tmp_live
        fake_out = os.path.join(tmp, "splits.yaml")
        with open(fake_out, "w", encoding="utf-8") as fh:
            yaml.safe_dump(doc, fh, allow_unicode=True)

        # 1) TMP kopya bozulur -> kayıt GEÇERSİZ olmalı
        df = pd.read_parquet(tmp_frozen)
        df.loc[df.index[0], "close"] = float(df.loc[df.index[0], "close"]) * 1.01
        df.to_parquet(tmp_frozen, index=False)
        problems = RS.verify(fake_out)
        assert any("UYUŞMUYOR" in p for p in problems), problems
        # 2) kopya geri yüklenir -> temiz
        shutil.copy(real_frozen, tmp_frozen)
        assert RS.verify(fake_out) == [], "geri yukleme sonrasi temiz olmali"
        # 3) CANLI dosyanin buyumesi bir HATA DEGILDIR: drift olarak raporlanir
        lf = pd.read_parquet(tmp_live)
        last_ts = pd.to_datetime(lf["timestamp_utc"], utc=True).max()
        extra = lf.iloc[[-1]].copy()
        extra["timestamp_utc"] = last_ts + pd.Timedelta(hours=4)
        pd.concat([lf, extra], ignore_index=True).to_parquet(tmp_live, index=False)
        assert RS.verify(fake_out) == [], "canli drift kaydi GECERSIZ kilamaz"
        notes = RS.drift_report(fake_out)
        assert any("canlı veri büyüdü" in n for n in notes), notes
        # 4) cakisma kontrolu de calisiyor mu?
        doc["assets"]["BTC"]["test"]["used"]["first_utc"] = \
            doc["assets"]["BTC"]["valid"]["used"]["first_utc"]
        with open(fake_out, "w", encoding="utf-8") as fh:
            yaml.safe_dump(doc, fh, allow_unicode=True)
        problems = RS.verify(fake_out)
        assert any("çakışıyor" in p for p in problems), problems
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_build_split_handles_missing_asset() -> None:
    rec = RS.build_split("YOKBOYLE", "4h")
    assert "error" in rec


def test_split_is_deterministic() -> None:
    """Ayni canli veriyle iki kez calistirinca ayni on-kayit cikmali.

    2026-09-17 bakım (VAKA 3 regressyonu): `build_split` → `_freeze` frozen
    snapshot'ı YENİDEN YAZAR; bu test eskiden GERÇEK frozen üzerine yazardı
    (live==frozen iken no-op, drift altında DESTRÜKTİF). Artık `RS.FROZEN_DIR`
    test süresince TMP dizine yönlendirilir; gerçek frozen'a dokunulmaz
    (runner'daki sha bekçisi ayrıca assert eder)."""
    real_dir = RS.FROZEN_DIR
    tmp = tempfile.mkdtemp()
    try:
        RS.FROZEN_DIR = tmp
        a = RS.build_split("BTC", "4h")
        b = RS.build_split("BTC", "4h")
    finally:
        RS.FROZEN_DIR = real_dir
        shutil.rmtree(tmp, ignore_errors=True)
    for k in ("rows_tradable", "frozen_sha256"):
        assert a[k] == b[k], k
    assert a["train"]["used"]["first_utc"] == b["train"]["used"]["first_utc"]
    assert a["test"]["used"]["last_utc"] == b["test"]["used"]["last_utc"]


def test_build_split_never_writes_real_frozen() -> None:
    """REGRESYON (2026-09-17 incident-3): FROZEN_DIR tmp'ye yönlendirilmişken
    build_split koşuları GERÇEK frozen snapshot'ları bayt-bayt DEĞİŞTİRMEMELİ;
    çıktı tmp'de üretilmeli ve kaydı kendi tmp dosyasına bağlanmalı."""
    before = _frozen_shas()
    real_dir = RS.FROZEN_DIR
    tmp = tempfile.mkdtemp()
    try:
        RS.FROZEN_DIR = tmp
        rec = RS.build_split("BTC", "4h")
        assert "error" not in rec, rec
        rec2 = RS.build_split("GOLD", "4h")
        assert "error" not in rec2, rec2
        tmp_btc = os.path.join(tmp, "btc_4h_frozen.parquet")
        assert os.path.exists(tmp_btc) and os.path.exists(os.path.join(tmp, "gold_4h_frozen.parquet"))
        # kayıt, tmp'de üretilen snapshot'ın sha'sına bağlanır (öz tutarlılık)
        assert rec["frozen_sha256"] == RS._sha256(tmp_btc)
    finally:
        RS.FROZEN_DIR = real_dir
        shutil.rmtree(tmp, ignore_errors=True)
    assert _frozen_shas() == before, "GERÇEK frozen değişti — build_split sızıntısı!"


# --------------------------------------------------------------------------

def test_bist30_basket_split_is_a_single_common_window() -> None:
    """KARAR 1: hisse başına AYRI split YOK. Tüm sepet TEK ortak takvim
    penceresini paylaşır; purge/embargo ve frozen-snapshot kuralı core ile aynı."""
    doc = _doc()
    b = doc.get("bist30_basket")
    assert isinstance(b, dict) and "error" not in b, b
    assert b["type"] == "basket" and b["weighting"] == "equal_risk"
    assert b["signal_level"] == "per_stock"
    assert b["n_stocks"] == 28, b["n_stocks"]
    assert len(b["stocks"]) == 28
    # elenenler sepette DEĞİL ama kayıtta GÖRÜNÜR
    assert "DSTKF" not in b["stocks"] and "TRALT" not in b["stocks"]
    assert "DSTKF" in b["excluded_from_basket"] and "TRALT" in b["excluded_from_basket"]
    # tek ortak pencere: blok sınırları takvim damgası, hisse bazlı değil
    tr, va, te = b["train"]["used"], b["valid"]["used"], b["test"]["used"]
    assert pd.Timestamp(tr["last_utc"]) < pd.Timestamp(va["first_utc"])
    assert pd.Timestamp(va["last_utc"]) < pd.Timestamp(te["first_utc"])
    gap = b["purge_bars"] + b["embargo_bars"]
    assert b["grid_bars"] > 0
    # ızgara üzerindeki purge boşluğu (takvim damgası indexi üzerinden)
    assert te["grid_bars"] > 0 and tr["grid_bars"] > 0
    assert b["test_calendar_days"] > 0
    # her hisse TEST bloğunda benzer sayıda tradable bara sahip olmalı
    per = list(te["stocks"].values())
    assert len(per) == 28
    assert max(per) - min(per) <= 20, (min(per), max(per))
    assert min(per) >= RS.POLICY["min_test_bars"] // 2, min(per)
    # frozen snapshot (H17) + survivorship caveat'i
    assert os.path.exists(os.path.join(RS.ROOT, b["frozen_file"]))
    assert len(b["frozen_sha256"]) == 64
    assert any("SURVIVORSHIP" in w for w in b["warnings"])
    assert any("LONG-ONLY" in w for w in b["warnings"])
    # frozen snapshot uzun form: 28 hisse x pencere içi barlar
    assert b["frozen_rows"] >= 28 * 1000, b["frozen_rows"]


def test_basket_split_verify_catches_tampering() -> None:
    # 2026-09-17 bakım: GERÇEK basket frozen'ına yazılmaz; TMP kopya + fake yaml
    # (mutlak yol) üzerinde koşar.
    doc = _doc()
    b = doc["bist30_basket"]
    assert RS.verify(PREREG) == [], RS.verify(PREREG)
    tmp = tempfile.mkdtemp()
    try:
        real_fz = os.path.join(RS.ROOT, b["frozen_file"])
        tmp_fz = os.path.join(tmp, "basket_frozen.parquet")
        shutil.copy(real_fz, tmp_fz)
        doc["bist30_basket"]["frozen_file"] = tmp_fz     # MUTLAK yol -> ROOT devre dışı
        fake = os.path.join(tmp, "splits.yaml")
        with open(fake, "w", encoding="utf-8") as fh:
            yaml.safe_dump(doc, fh, allow_unicode=True)
        df = pd.read_parquet(tmp_fz)
        df.loc[df.index[0], "tradable"] = not bool(df.loc[df.index[0], "tradable"])
        df.to_parquet(tmp_fz, index=False)
        problems = RS.verify(fake)
        assert any("BIST30_BASKET" in p and "UYUŞMUYOR" in p for p in problems), problems
        shutil.copy(real_fz, tmp_fz)
        assert RS.verify(fake) == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run_all() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    # BEKÇİ: suite başlamadan frozen baseline ile tutarlı olmalı
    if _frozen_shas() != _FROZEN_BASELINE:
        print("FAIL  [guard] suite BAŞLANGICINDA frozen sha baseline'dan farklı — "
              "önce `git checkout -- data/frozen/` ile geri yükle")
        return 1
    for fn in fns:
        before = _frozen_shas()          # test BAŞI: frozen sha değişmezliği
        try:
            fn()
            after = _frozen_shas()       # test SONU: frozen sha değişmezliği
            if after != before:
                changed = sorted(k for k in set(after) | set(before)
                                 if after.get(k) != before.get(k))
                raise AssertionError(
                    f"FROZEN snapshot test sırasında DEĞİŞTİ: {changed} — "
                    f"testler gerçek frozen'a ASLA yazmamalı (tmp kopya kullan)")
            print(f"PASS  {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {fn.__name__}: {exc}")
        except Exception as exc:                                     # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
            if _frozen_shas() != before:
                print("      !! UYARI: ERROR sonrası frozen DEĞİŞMİŞ — "
                      "hemen `git checkout -- data/frozen/`")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    if _frozen_shas() != _FROZEN_BASELINE:
        print("FAIL  [guard] suite SONUNDA frozen baseline'dan farklı — suite GEÇERSİZ")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
