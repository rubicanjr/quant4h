# SKILL — quant4h-ops (M10 · EKİM MAINT)

quant4h oturumlarını (insan veya agent) AYNI yerden başlatan operasyon becerisi.
Kaynak hiyerarşisi: **PROGRESS.md > runbook/TEST_PLAN > bu dosya**. Çelişkide
PROGRESS kazanır. Bu dosya karar DEĞİŞTİRMEZ; yalnızca usul taşır.

## 1) Oturum bootstrap (her yeni oturum/agent — sırayla)
1. Depo: `github.com/rubicanjr/quant4h` (public). Yerel klon yoksa clone.
2. **İlk iş: `PROGRESS.md` son 3 blok okunur** (nerede kalındı, son sayımlar,
   açık bekleyişler). Asla sıfırdan başlanmaz; kaldığı yerden devam edilir.
3. Ortam: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
   (Windows'ta `.venv\Scripts\python`).
4. Doğrulama üçlüsü (beklenen: PROGRESS başlığındaki suite sayısı):
   - `for t in tests/test_*.py tests/eval/test_*.py; do .venv/bin/python -W ignore $t; done`
   - `.venv/bin/python scripts/register_splits.py --check` → EXIT 0 (H17)
   - `.venv/bin/python -m pytest -q tests/` → 0 warning (pytest.ini filtresi:
     pandas log RuntimeWarning — sentez sıfırlı seri, bilinen zararsız)
5. Mod: **ARAŞTIRMA-KAPALI / watch_only** (Stage 9 GEÇTİ=0). Emir yok, tavsiye
   yok, fetch/kırmızı-takım/look ancak kullanıcı ONAYI ile.

## 2) Patch ritmi (checkpoint disiplini)
1. Her birim TEK mantıksal iş → ≤25 satırlık parçalarla çalış → doğrula.
2. PROGRESS.md'ye TAMAMLANDI/DÜZELTME bloğu (sayımlar + hüküm etkisi YOK notu).
3. Test sayısı değiştiyse R09 senkronu: README + model_card + PROGRESS başlığı
   + `tests/test_deliverables.py::test_test_plan_counts_sync` iğnesi.
4. `git add -A && git commit` → `git format-patch -1 HEAD --stdout > patches/<ad>.patch`
   (push kullanıcıdadır; kümülatif gerekiyorsa: tree-delta TEK commit yöntemi —
   `git diff --binary <origin>..HEAD` → temp klon → commit → format-patch).
5. **Temiz klon doğrulaması**: `/tmp` clone → patch `git am` → suite + `--check`.
6. Teslim: patch yolu + ÖZET (satır limiti kullanıcının komutunda) + **DUR**.

## 3) ONAY↔TESLİM eşleme kuralı (zorunlu)
Her patch özetinde, kullanıcı ONAY maddeleri ↔ teslim edilen iş eşleme
tablosu verilmesi ZORUNLUDUR:
```
| # | ONAY maddesi        | Teslim                      | Durum |
|---|---------------------|-----------------------------|-------|
| 1 | ...                 | dosya/test/rapor            | ✓/kısmi/yok+gerekçe |
```
Eşlenemeyen ONAY maddesi "yok + gerekçe" ile AÇIKÇA yazılır; sessiz düşürme
YASAK. Karar gerektiren boş bırakılmış seçenekler (A/B/C) EKLENMEZ, bekleyiş
olarak not edilir.

## 4) Look protokolü (§B özeti — ayrıntı: TEST_PLAN §B + runbook §B)
- Look = mühürlü TEST dilimine bakma hakkı. **Bütçe: 4/yıl; #1 kullanıldı
  (2026-09-17, GEÇTİ=0) → #2 en erken 2026-12-17.** Kayıt: runbook §C look-log.
- Tetik koşulları (ÖN KOŞUL, hepsi birden): ≥90 gün + ≥150 yeni kapanmış bar
  + protokol sapması YOK + **kullanıcının yazılı ONAYI**.
- Sıra: veri dondur → kayıtlı hücre/parametrelerle çalıştır → **M19: go/no-go
  ÖNCESİ kırmızı-takım notu yaz** → §B.7 eşiklerini DEĞİŞTİRMEDEN değerlendir →
  rapora M13 alanlarını işle (max ardışık kayıp + uyma oranı) → look-log +
  PROGRESS + model card güncelle. Eşikler: expR>0, CI alt>0, PF≥1.2, DD≤%25,
  n≥100/150, maxConsecLoss≤8, walk-forward tutarlı.
- Sonuç ne olursa olsun: parametre UYDURMA YOK; yeni look ancak yeni ONAY ile.

## 5) Model/oturum değişim protokolü
Yeni model/agent devralırken: (a) bootstrap §1 aynen; (b) önceki oturumun
ÖZETİ'ne değil PROGRESS.md + repo dosyalarına güvenilir (özet ipucu, kanıt
değildir); (c) ilk çıktıda "devralma doğrulaması" verilir: suite X/X, --check
EXIT 0, son PROGRESS bloğunun 1 cümlelik teyidi; (d) karar/parametre/eşik
değişikliği ÖNERİLEMEZ — ancak kullanıcı ONAYI ile; (e) önceki oturumun
bekleyişleri (patch push, kalite puanı, look #2 tarihi) aynen devralınır.

## 6) Değişmezler kısayolu (tam liste: PROGRESS "Sabitlenen Kararlar")
İcra `open[t+1]` (4H) · aynı barda STOP öncelikli · maliyet iki yönde ·
H35 stopsuz pozisyon YOK · look-ahead sözleşmesi `bar_open − 4h` · fail-closed
(QC RED → DUR) · grid kilitli TS{60,90,120}/TP{2R,3R,4R}/buffer{0.5,1.0,1.5}
(set dışı → ValueError) · seçim yalnız Stage 9 OOS (core) ·
PER_ASSET_IN_SAMPLE_TUNING_ALLOWED=False · BIST30=watch_only ·
kadans BIST 14:00/18:00 + core 03/07/11/15/19/23 (UTC+3), ≥200 dk kapı ·
chart ≤3 görsel öğe sınıfı · yasak indikatörler (lint_forbidden otomatik).

## 7) Şablonlar
- PROGRESS blok: `## [TARİH] <AD> — TAMAMLANDI / DÜZELTME (Rxx)` + Kapsam /
  Yapılanlar / Doğrulama / Notlar (hüküm etkisi YOK + sayımlar).
- §A aylık rapor: runbook §A (M13 alanları dahil).
- Cadence raporu: `scripts/cadence_4h_status.py` çıktısı (QC RED → ⛔, exit 3).
- Snapshot PNG: `scripts/export_snapshot_pngs.py` → `reports/snapshot/`
  (equity + cadence şablon örneği; deterministik).
