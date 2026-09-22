# quant4h — RİSK SİCİLİ (risk register)

*Üretim: 2026-09-17 · Tür: **SALT-OKUNUR RİSK DENETİMİ** (kod değişikliği YOK, hüküm YOK, tune YOK) · Kapsam: repo taraması + DR tatbikatı + tohum risk listesinin doğrulanması/genişletilmesi · Statü değiştirmez: proje watch_only/araştırma-kapalı.*

> **GÜNCELLEME (2026-09-17, maint-riskfix patch'i — kullanıcı onaylı):** R01 → CI eklendi (`.github/workflows/ci.yml`) · R02 → scipy pin + pytest + `requirements.lock` · R03 → runbook v1.2 alpha-spending tarifesi · R04 → aylık raw-drift hash logu (ara azaltım; fetch-log kodu hâlâ açık) · R05 → look başına üniverse dondurma (§B.1 v1.2) · R06 → kullanıcı kararı: PUBLIC kalır + `data/raw/` untrack + README provenans · R09 → 224/224 senkron (test iğnesiyle). **AÇIK KALAN:** R07 (kadans — CI cron önerisi), R08 (metals kontrat-ay → quant4h-M), R10–R15 (P3 kuyruğu; R11 test matrisi gelecek ayın maint'i).

Ölçekler: **Önem** = gerçekleşirse projeye etkisi (Y/O/D) · **Olasılık** = önlem alınmazsa görülme sıklığı (Y/O/D) · **Öncelik**: P1 (hemen/ilk fırsatta) · P2 (bir sonraki bakım penceresi) · P3 (fırsat buldukça). **Sahip**: K=kullanıcı, A=ajan (onayla), O=ortak.

---

## A) Tarama bulguları (kanıtlı)

| alan | sonuç | kanıt |
|---|---|---|
| Secret/.env sızıntısı | **TEMİZ** | HEAD üzerinde `git grep -iE "api[_-]?key\|secret\|passw\|token\|bearer\|PRIVATE KEY"` → 0 eşleşme; tüm history'de `.env/credentials/*.pem/*.key/netrc` dosya eklenmesi → 0. `.git/config` gibi hassas yollar sandbox snapshot'ı dışında (platform davranışı). Not: commit author e-postası placeholder (`senin-email@gmail.com`) → R14 |
| Requirements pin durumu | **İYİ (1 istisna)** | 10 paketin 9'u `==` ile tam pinli; **`scipy>=1.14` gevşek** (kurulan 1.17.1); hash/lock dosyası YOK; `pytest` bilinçli olarak listede değil (house runner — README/NOT 3 belgeli) |
| .gitignore kapsamı | **ÇELİŞKİ var, çalışıyor** | `data/` + `*.parquet` ignore'da AMA 306 data dosyası force-add ile tracked → YENİ data artefaktları `git add`'i SESSİZCE atlar (kanıt: basket attrs `-f` gerektirmişti). Dosya başındaki UTF-8 BOM (EF BB BF) git tarafından TOLERE ediliyor (`check-ignore --no-index` ile doğrulandı: `data/` kuralı eşleşiyor) → kozmetik. `patches/` ne tracked ne ignore (bilinçli teslimat kanalı) |
| Veri/boyut hijyeni | **SAĞLIKLI** | `.git` pack 77 MiB · `data/` 85 MB · 406 tracked dosya · en büyük tek dosya 4.6 MB (BTC signals parquet) · GitHub limitlerinin altında; watch_only'de büyüme hızı düşük |
| Doküman drift'i | **2 bayat canlı sayaç** | README §1 "Testler **223/223**" ve model_card (başlık + §8) "223/223" → fiilî **224/224** (maint-testfix sonrası). `final_verdict.md`/PROGRESS tarihî bloklarındaki 217/223 damgalı kayıttır, drift DEĞİL. **Kuplaj:** `test_deliverables.py` README'de "223/223" iğnesini assert ediyor → README düzeltmesi test iğnesiyle BİRLİKTE yapılmalı (ayrı maint patch, onay gerekir) |
| Test matrisi boşlukları | **5 somut boşluk** | (1) **çift taraflı gap + çakışma**: aynı barda `open < stop` VE `high ≥ TP` kombinasyonu test edilmemiş (mevcut çakışma testi gap'siz open ile; gap testi çakışmasız) — engine `worse_open` dalı kodsuz-doğrulanmış ama kilitsiz; (2) **sıfır-aralık bar** (o=h=l=c; BIST'te gerçek: DSTKF'de 68 adet ölçülmüştü) engine fill davranışı testsiz; (3) **tavan sınır durumu**: ısı == tavan (1e-12 toleransın tam üstü/altı) testsiz; (4) **equity ≤ 0 (iflas) yolu**: units≤0 → `invalid_price` reddi kodda var, testsiz; (5) **yıl sınırında ISO hafta rollover** + aynı varlıkta L+S ortak fren sayacı testsiz |
| Veri kaynağı lisans/ToS | **MARUZİYET** (bkz. R06) | **Binance** spot klines: halka açık API, kişisel kullanım; ticari yeniden dağıtım kısıtlı. **Yahoo Finance** (yfinance 1.7.0, resmî OLMAYAN istemci; kütüphane Apache-2.0 ama VERİ Yahoo ToS'a tabi: kişisel kullanım, **yeniden dağıtım yasak**). **Investing.com / TradingView / Midas / HangiKredi / Uzmanpara**: üniversal listesi web'den derlendi (universe yaml'da kayıtlı) — scraping çoğunun ToS'unda kısıtlı. Veriler **PUBLIC repoda commit'li** → R06 |

## B) DR TATBİKATI (kanıt — 2026-09-17)

| adım | sonuç |
|---|---|
| `git clone` (temiz, /tmp) | ✓ HEAD `2789bcf` |
| `python3 -m venv` (sıfır) | ✓ 3.8s |
| `pip install -r requirements.txt` | ✓ EXIT 0 · 44s · pandas 3.0.5/numpy 2.4.6 tam pinlerle |
| `pytest -q` (talimat gereği, olduğu gibi) | ❌ **"No module named pytest"** — pytest requirements'ta YOK (bilinçli tasarım: her test dosyası kendi çalıştırıcısını içerir; README NOT 3). DR için otorite house runner'dır |
| House suite (`for t in tests/test_*.py`) | ✓ **224/224**, 0 fail dosya (~29s) |
| `register_splits.py --check` | ✓ EXIT 0 "DOĞRULAMA OK" |
| Frozen bütünlüğü | ✓ suite bekçisi 5/5 sha doğruladı |

**DR hükmü:** ortam sıfırdan ~1 dakikada TAM kurulabilir ve tüm kilitler yeşil dönüyor. Tek sürtünme: `pytest -q` beklentisi ile house-runner gerçekliği arasındaki fark (dokümante; sorun değil, talimat şablonu notu).

## C) RİSK SİCİLİ

### Tohum liste doğrulaması (8/8 DOĞRULANDI, 2'si genişletildi)

| # | Tohum madde | Doğrulama |
|---|---|---|
| 1 | "yerel suite hiç koşulmadı" | DOĞRULANDI (genişletildi): suite yalnız sandbox'ta/elle koşuluyor; **hiçbir otomatik koşulma kaydı yok** (CI yok, cron yok) → R01 |
| 2 | "CI yok" | DOĞRULANDI: `.github/workflows` yok, badge yok → R01 |
| 3 | "lock dosyası yok" | DOĞRULANDI: requirements pinli ama hashes/lock yok; `scipy>=1.14` gevşek → R02 |
| 4 | "look çokluğu alpha-spending politikasız" | DOĞRULANDI: runbook §B look sayısını sınırlıyor (4/yıl) ama **tekrarlanan OOS bakışlarının çoklu-test yükünü** düzelten istatistiksel politika YOK (eşikler look'lar arası sabit → her look false-positive riskini büyütür) → R03 |
| 5 | "raw satıcı drift'i loglanmıyor" | DOĞRULANDI: raw cache her fetch'te ÜZERİNE yazılır; fetch zamanı/satır/sha/kaynak meta verisi loglanmaz (processed attrs var, raw'da yok; git yalnız commit'li anı saklar) → R04 |
| 6 | "look'ta üniverse versioning yok" | DOĞRULANDI: `bist30_universe.yaml` sürümlü (2026-09-16.v1) ama §B protokolü look öncesi üniversal sürümünü **doğrulamayı/yeniden sabitlemeyi GEREKTİRMİYOR** (üyelik değişirse eski look'la kıyas bozulur) → R05 |
| 7 | "public repo IP notu" | DOĞRULANDI: repo PUBLIC + Yahoo/scrape kaynaklı veri commit'li → R06 |
| 8 | "insan-bağımlı kadans" | DOĞRULANDI: aylık/çeyreklik koşular insan tetikli; kaçan pencereyi TESPİT eden mekanizma yok → R07 |
| 9 | "metaller kontrat metadata'sı" | DOĞRULANDI: GC=F/SI=F ön-ay; feed'de kontrat ayı YOK → roll/bad-print ayırt edilemez (FLAG-ONLY politika; PROGRESS teşhis 6) → R08 |

### Sicil (yeni maddeler dahil)

| ID | Risk | Önem | Olasılık | Öncelik | Azaltma (mevcut → önerilen) | Sahip |
|---|---|---|---|---|---|---|
| **R06** | **Public repo + veri lisansı/ToS maruziyeti**: Yahoo verisi (yeniden dağıtım yasağı) + scraping kaynakları + Binance klines PUBLIC repoda; frozen snapshot'lar türev veri içerir | **Y** | O | **P1** | Mevcut: kapsam "araştırma", ticari kullanım yok. Önerilen: (a) repoyu PRIVATE yap, VEYA (b) veri dosyalarını repodan çıkar (frozen'lar kullanıcıda özel kalsın; kod+raporlar public kalır; sha kayıtları doğrulamayı sürdürür), VEYA (c) lisanslı kaynağa geç. Karar KULLANICININ | K |
| **R01** | **CI yok; suite insan tetikli**: regresyonlar commit'ler arasında SESSİZCE birikebilir (224 test + frozen bekçisi + --check otomatik hiç koşmuyor) | O | **Y** | **P1** | Önerilen: GitHub Actions: push/PR'da `pip install -r requirements.txt` + house suite + `register_splits --check` + frozen sha bekçisi (~2 dk). Workflow dosyası onayla eklenir | O |
| **R03** | **Alpha-spending politikası yok**: 4 look/yıl × sabit eşikler → tekrarlanan testlerle GEÇTİ'nin false-positive olasılığı şişer; "eşik avcılığı" riski yapısal | **Y** | O | **P1** | Önerilen: Look-2'den ÖNCE runbook §B v2 eki: look başına sıkılaşan eşik veya bonferroni-tarzı düzeltme (ör. CI altı > 0 yerine > look-sayısına bağlı pozitif marj) + her look'un alpha bütçesinden düşülmesi; kullanıcı onayıyla | O |
| **R11** | **Test matrisi boşlukları**: çift taraflı gap+çakışma, sıfır-aralık bar fill'i, ısı==tavan sınırı, equity≤0, yıl-sınırı hafta rollover, L+S ortak fren (bkz. §A) | O | O | **P2** | Önerilen: tek maint patch'te 6-8 yeni test (engine/simulator davranışı DEĞİŞMEZ, yalnız kilitlenir; davranış değişikliği gerekirse ayrıca onaya sunulur) | A (onayla) |
| **R04** | **Raw satıcı drift'i loglanmıyor**: fetch üzerine-yazar; "hangi bar ne zaman hangi kaynaktan geldi" izi yok → sessiz veri değişimi geriye dönük araştırılamaz | O | **Y** | **P2** | Önerilen: adaptöre append-only `data/raw/FETCH_LOG.jsonl` (zaman, ticker, rows, sha256, venue) — küçük kod değişikliği, onayla; ara çözüm: monitor raporuna raw sha256 tablosu (kod değişikliği gerektirmez) | A (onayla) |
| **R08** | **Metaller kontrat metadata'sı yok**: roll ile gerçek ekstrem hareket ayırt edilemez; GOLD 10 + SILVER 6 aday insan incelemesi bekliyor | O | **Y** | **P2** | Mevcut: FLAG-ONLY + return_valid dışlama. Önerilen: kontrat aylı continuous future kaynağı (ücretli) veya CME takviminden roll tarihlerinin elle işaretlenmesi; karar kullanıcıda | K |
| **R12** | **Tek kanallı teslim + sandbox geçiciliği**: `.git`/`.venv` turlar arası kalıcı DEĞİL; local commit'ler uçar; kalıcı taşıyıcı yalnız `patches/*.patch` (tek kopya) | O | **Y** | **P2** | Mevcut: KURAL md.5 (her tur re-clone) + patch doğrulama. Önerilen: kullanıcı patch'i alır almaz `git am`+push etsin (gecikme = kayıp penceresi); agent her tur başında remote'u doğrular | O |
| **R13** | **Vendor API kırılganlığı**: Yahoo aynı gün 2 kez boş yanıt/rate-limit verdi (2026-09 monitor vakası); yfinance pin'i upstream değişikliğinde kırılabilir | O | **Y** | **P2** | Mevcut: cache + retry + runbook "aynı gün 2. `--no-cache` YASAK". Önerilen: başarısız fetch'te bir önceki cache'e düşüşün açık log'u (R04 ile birleşir); metals için alternatif kaynak değerlendirmesi | O |
| **R02** | **Lock/hash yok; `scipy>=1.14` gevşek**: transitive çözümü ortamdan ortama kayabilir (DR'da 1.17.1 kuruldu) | D | O | **P3** | Önerilen: `scipy==1.17.1` pin + `requirements.lock` (pip freeze) veya pip-tools hash modu; onayla | A (onayla) |
| **R05** | **Look'ta üniverse versioning yok**: üyelik değişirse look'lar arası kıyas bozulur | O | D | **P3** | Önerilen: §B.1 ön-kayıt adımına "universe version doğrula/değiştirme; değiştiyse YENİ version + karşılaştırılabilirlik notu" maddesi (runbook v1.2, onayla) | O |
| **R07** | **İnsan-bağımlı kadans**: aylık/çeyreklik pencere kaçarsa tespit eden yok | D | O | **P3** | Önerilen: takvim hatırlatıcısı (kullanıcı) veya CI cron'unun "bu ayın monitor raporu yok" uyarısı (R01 ile birleşir) | K |
| **R09** | **Doküman drift'i (canlı sayaçlar)**: README/model_card "223/223" → fiilî 224/224; `test_deliverables` iğnesi README'ye kilitli → ikisi BİRLİKTE güncellenmeli | D | **Y** (oldu) | **P3** | Önerilen: maint patch: README+model_card+test iğnesi 224'e; kural: canlı test sayacı YALNIZ PROGRESS'te tutulur, diğer belgeler "bkz. PROGRESS" der | A (onayla) |
| **R10** | **gitignore/tracked çelişkisi**: `data/`+`*.parquet` ignore ama 306 dosya force-add'li → yeni data artefaktı sessizce commitsiz kalabilir; BOM kozmetik (git tolere ediyor, test edildi) | D | O | **P3** | Önerilen: `.gitignore`'a açık whitelist (`!data/frozen/`, `!data/processed/…`) veya runbook'a "data artefaktı `git add -f` ile eklenir" maddesi; BOM temizliği | A (onayla) |
| **R14** | **Git metadata hijyeni**: public repoda placeholder author e-postası (`senin-email@gmail.com`) | D | Y (oldu) | **P3** | Önerilen: kullanıcı `git am --reset-author` (kendi kimliği) veya GitHub noreply e-postası; agent tarafı patch üretiminde nötr kimlik kullanabilir | K |
| **R15** | **Ölü bağlam verisi**: dxy/usdtry/spx/vix/funding çekiliyor ama sinyal zincirinde TÜKETİLMİYOR → faydasız ToS maruziyeti + ağırlık | D | Y | **P3** | Önerilen: ya yeni hipotezde (YENİ PROJE, §F) kullan ya çekimi durdur; mevcut hâliyle yalnız "malzeme" olarak kayıtlı | K |

## D) TOP-5 AKSİYON LİSTESİ

| # | Öncelik | Aksiyon | Madde | Sahip | Not |
|---|---|---|---|---|---|
| 1 | **P1** | Repo görünürlüğü/veri lisansı KARARI: private'a çek VEYA veri dosyalarını repodan ayır VEYA lisanslı kaynağa geç | R06 | K | Hukuki/IP maruziyeti; tek taraflı çözülemez |
| 2 | **P1** | Minimal CI: house suite + `register_splits --check` + frozen bekçisi (push'ta otomatik) | R01, R07 | O | Workflow dosyası onayla eklenir; ~2 dk/koşu |
| 3 | **P1** | Look-2'den ÖNCE alpha-spending politikası (runbook §B v2 eki) | R03 | O | Çoklu-test disiplininin istatistiksel ayağı |
| 4 | **P2** | Test matrisi maint patch'i: çift-gap+çakışma, sıfır-aralık bar, ısı==tavan, equity≤0, hafta rollover, L+S fren | R11 | A (onayla) | Davranış DEĞİŞTİRMEZ, kilitler; bulgu çıkarsa ayrıca onaya gelir |
| 5 | **P2** | Veri izlenebilirliği: append-only fetch logu (raw sha/satır/kaynak/zaman) + metals kontrat-ayı kaynak araştırması | R04, R08, R13 | O | Küçük kod değişikliği onayla; metals kararı kullanıcıda |

*P3 kuyruğu (fırsat buldukça): R02 scipy pin+lock · R05 universe-versioning §B.1'e · R09 doc/test iğnesi senkronu · R10 gitignore whitelist · R14 author kimliği · R15 ölü ctx verisi.*

## E) Kapsam ve sınırlar (dürüstlük notu)

- Bu denetim SALT-OKUNUR yapıldı: hiçbir kod/config/veri dosyası değiştirilmedi; suite 224/224 yeşil doğrulandı (DR klonunda + yerelde).
- Secret taraması desen-bazlıdır (bilinen anahtar sızıntısı desenleri); %100 garanti DEĞİLDİR.
- ToS/lisans notları mühendislik değerlendirmesidir, HUKUKİ TAVSİYE değildir.
- Bu belge yatırım tavsiyesi değildir; watch_only statüsünü ve Aşama 9 hükmünü (GEÇTİ=0) DEĞİŞTİRMEZ.

## 8. On maddelik çapraz kontrol (M13 — her patch/look/§A döngüsünde)
1. Suite sayısı dört yerde aynı: README + model_card + PROGRESS başlığı + `test_deliverables` iğnesi.
2. `register_splits.py --check` EXIT 0; frozen sha256'lar `data/frozen/SHA256SUMS.txt` ile birebir.
3. `configs/selected_cells.yaml` hücreleri kilitli set içinde (TS/TP/buffer) ve Stage 9 OOS seçimi.
4. Golden fixture'lar üreteç çıktısıyla byte-eşit (`test_viz_generator`); taahhütlü pine şablonları lint + yasak-kelime temiz (`test_pine_lint`).
5. `reports/stage9_oos_verdict.json` ↔ `reports/final_verdict.md` ↔ `models/model_card.md` hüküm cümleleri aynı (GEÇTİ=0 → watch_only).
6. trades CSV ↔ XLSX satır/sayım tutarlı (`test_trade_xlsx`); equity = START_EQ + Σ net_pnl.
7. Kadans raporu QC RED içeriyorsa ⛔ SORUN NOTU + exit 3 (fail-closed) — rapor normal görünmüyor.
8. `reports/cadence/.state.json` son_fetch ile ≥200 dk kapısı; aynı gün çift `--no-cache` fetch YOK.
9. PROGRESS son blok: teslim edilen patch dosyası `patches/` altında var ve temiz klonda `git am` + suite doğrulanmış.
10. Look-log (§C) satır sayısı = kullanılan look sayısı (1) + bütçe/tarih alanları güncel; ONAY↔TESLİM eşleme tablosu son özetde mevcut.
