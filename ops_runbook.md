# ops_runbook.md — quant4h watch_only operasyon el kitabı

*Sürüm: **v1.4** (2026-09-18, M14 kullanıcı onaylı: §A-cadence kural 7 "viz tazeleme". v1.3 2026-09-18: §A-cadence BIST slotları v1.1 ızgara kapanışlarına hizalandı 14:00/18:00 + `pine/` görselleştirme eki notu. v1.2 2026-09-17: §B alpha-spending tarifesi + look başına üniverse dondurma + üyelik değişim logu · §A.3b aylık raw-drift hash logu. v1.1 2026-09-17: §A komut düzeltmesi — `--start` eklendi + veri çekim/cache politikası; 2026-09 izleme vakaları §A.2'de. v1 2026-09-17 kullanıcı onaylı) · Statü: **watch_only / araştırma-kapalı** · Bağlayıcı kaynaklar: `PROGRESS.md`, `configs/user_decisions.yaml`, `reports/final_verdict.md`*

> **KURAL 0:** Bu runbook trade üretmez. Her çıktının üzerinde `watch_only — trade YOK, emir YOK, tavsiye YOK` başlığı bulunur. Sistem edge KANITLAYAMADI (GEÇTİ=0); hiçbir izleme çıktısı "sistem çalışıyor/kazanıyor" şeklinde YORUMLANAMAZ.

---

## A) AYLIK SİNYAL İZLEME RAPORU (trade YOK)

**Amaç:** veri hattının canlı olduğunu ve sinyal zincirinin fail-closed davranışını doğrulamak; edge izlenimi vermek DEĞİL.

**Ne zaman:** her ayın ilk iş günü (veri tazeliği QC'den geçtikten sonra).

**Adımlar (mevcut script'ler — YENİ kod yazılmaz):**
1. `python3 -W ignore scripts/run_data_qc.py --assets BTC GOLD SILVER BIST30 --start 2017-08-17 --timeframe 4h --min-rows 1500` → QC kararı RED olan varlık varsa rapor **YAYIMLANMAZ** (fail-closed), sorun notu düşülür. (H14: resample→adjust→QC tek komutta; `run_adjust.py` ayrıca ÇALIŞTIRILMAZ.)
   **Veri çekim politikası (v1.1):** `--start 2017-08-17` ZORUNLUDUR — eksikse Binance adaptörü yalnız son ~1.000 barı çeker ve BTC raw cache'ini KIRPAR (2026-09 vakası). Varsayılan mod cache'lidir; ayın İLK canlı çekimi `--no-cache --start 2017-08-17` ile YALNIZ 1 KEZ yapılır, **aynı gün ikinci `--no-cache` YASAK** (Yahoo rate-limit → geçici RED üretir; 2026-09 vakası). Çekim başarısızsa taze cache'e dönülür ve sapma notuna yazılır. Raw cache üzerine yazılması normaldir (yeni snapshot); **frozen snapshot'lara asla dokunulmaz** — koşu sonrası `register_splits.py --check` EXIT 0 + drift BİLGİ notu doğrulanır.
2. `run_regime_report.py` → `run_levels_report.py` → `run_momentum_report.py` → `run_signal_report.py` (sıra bağlayıcı; zincir kolonları bir öncekine dayanır).
3. Elle derleme (rapor şablonu §A1): son 30 günün ham/final sinyal sayaçları (strict/capped/cooldown_only akışları), rejim dağılımı, XU030 bağlam durumu, `rejected_no_valid_stop` ve `non_tradable` sayaçları, veri kesintisi/roll adayları.
3b. **Raw-drift hash logu (v1.2, ZORUNLU):** `data/raw/` altındaki HER ham dosyanın sha256'sı + satır sayısı raporun "Raw hash logu" alanına yazılır ve ÖNCEKİ AYIN raporuyla karşılaştırılır; **değişen her hash için** tek satır: varlık, eski→yeni satır sayısı, çekim tarihi. Bu log, satıcı drift'inin (vendor'ın geçmişi sessizce yeniden yazması) TEK izleme kanalıdır (R04 azaltımı; `data/raw/` artık repoda tracked DEĞİL — M4 kararı, hash izi bu yüzden raporlarda yaşar).
4. `git` hijyeni: aylık rapor `reports/monitor/YYYY-MM.md` olarak commit edilir (patch senkron kuralı PROGRESS'te).
5. **Restore (v1.1, ZORUNLU SIRA):** aylık raporun sayıları derlendikten SONRA `git checkout -- data/ reports/` ile canlı drift ve ara raporlar checkpoint durumuna geri alınır (`reports/monitor/` HARİÇ — o ayın artefaktıdır). Gerekçe: (a) repoda "commit'li veri == commit'li rapor" tutarlılığı; (b) **drift varken test suite KOŞULMAZ** — `test_splits.py` determinizm testi frozen snapshot'ı canlı verinin üzerine yazar (live==frozen iken no-op, drift altında DESTRÜKTİF; 2026-09 vakasında sha kilidi yakaladı, teknik borç kayıtlı: test tmp dizine alınmalı, onay bekliyor); (c) yeni barlar araştırmaya yalnız §B.1 yeni ön-kayıtla girer (H17). Suite ancak restore SONRASI koşulur.

**YASAK:** aylık raporda P&L, "şu sinyali izleseydin kazanç" hesabı, pozisyon önerisi, eşik/parametre değişikliği, sinyallerin kağıt-portföye bağlanması. İhlal = protokol ihlali (bkz. §D).

**Kapsam notu (v1.1):** §A zinciri 4 varlığı (BTC/GOLD/SILVER/XU030) tazeler; 28 hissenin canlı çekimi KAPSAM DIŞIDIR (hisse frame'leri son `run_bist_universe.py` snapshot'ıyla kalır, rapor dipnotunda tazeliği yazılır). Hisse refresh'i ayrı iş + onay gerektirir.

**Aylık koşu log'u:**

| ay | koşu tarihi | QC kararları | olay/sapma | rapor |
|---|---|---|---|---|
| 2026-09 | 2026-09-17 | 4× AMBER, 0 ERROR | 2 vaka (eksik `--start` → BTC cache kırpıldı, geri yüklendi; Yahoo rate-limit → geçici RED, aşıldı) — kalıcı hasar YOK, frozen etkilenmedi | `reports/monitor/2026-09.md` |

### A1) Aylık rapor şablonu (asgari alanlar)
```
# watch_only aylık izleme — <YYYY-MM>  (trade YOK, emir YOK, tavsiye YOK)
- QC kararları: BTC/GOLD/SILVER/BIST30 (AMBER/RED) + veri tazelik
- Rejim: her varlıkta son barın durumu (6'lı) + bağlam (XU030 EMA200 üstü/altı)
- Sinyal sayaçları (30 gün): ham → final (akış bazında), bastırılan (pozisyon/cooldown)
- Reddedilen girişler: no_valid_stop / not_tradable / geometry
- Veri olayları: kesinti penceresi, roll/bad-print adayları, kurumsal aksiyon bayrakları
- Raw hash logu (v1.2): data/raw/ dosya başına sha256 + satır sayısı · önceki aya göre DEĞİŞENLER (değişim yoksa "yok")
- Sapma notu: bu ay protokol dışı HİÇBİR şey yapıldı mı? (varsayılan: HAYIR)
```

## A-cadence) 4H MUM KAPANIŞI DURUM BİLDİRİMLERİ (M9, direktif 2026-09-18 — manuel tetik, scheduler YOK)

**Amaç:** watch_only izlemeye mum-kapanışı ritmi kazandırmak. **Trade YOK · emir YOK · tavsiye YOK · hüküm YOK · look hakkı TÜKETMEZ.**

**Slotlar (Europe/Istanbul = UTC+3, DST yok) — M9b revizyonu (2026-09-18, kullanıcı onaylı): BIST slotları v1.1 ızgara KAPANIŞLARINA hizalandı; CORE değişmedi:**

| grup | slotlar | mum |
|---|---|---|
| BIST30 (XU030 bağlam) | **14:00** | 4H kapanış (10:00–14:00 mumu, etiket 07:00 UTC) |
| BIST30 | **18:00** | 4H kapanış (14:00–18:00 mumu, etiket 11:00 UTC) + seans sonu (1H kaynak) |
| BTC · GOLD · SILVER | 03:00 · 07:00 · 11:00 · 15:00 · 19:00 · 23:00 | 4H |

*(Eski 11:00/15:00 BIST slotları v1.1 kapanışlarıyla çakışmıyordu; 2026-09-18 demo dosyaları tarihî kayıttır. 11:00/15:00 artık YALNIZ core slotudur.)*

**Zamanlama:** her bildirim son mum TAMAMLANDIĞINDA (15 dk tolerans). 11:00/15:00 slotları her iki tabloda ortaktır → tek bildirim dosyası iki grubu da içerir.

**Komut (manuel):**
```bash
python3 -W ignore scripts/cadence_4h_status.py                      # en yakın geçmiş slot
python3 -W ignore scripts/cadence_4h_status.py --slot 15:00 --date 2026-09-18
python3 -W ignore scripts/cadence_4h_status.py --fetch              # canlı çekim + TAM zincir (rate-kapılı)
```
Çıktı: `reports/cadence/YYYY-MM-DD_HHMM.md` (her bildirim ayrı dosya) + stdout. Şablon (direktif B, sabit): **SAĞLIK** (QC + tazelik + X bar) → **REJİM** → **SEVİYE** → **MOMENTUM (σ)** → **SİNYAL** (ham→kapılar→final, capped) → **EYLEM: YOK**.

**Kurallar:**
1. `--fetch` rate kapısı: son fetch'ten **≥200 dk** geçmeden ÇEKİLMEZ (`reports/cadence/.state.json`; Yahoo rate-limit dersi, runbook v1.1). Fetch = TAM zincir, §A sırasıyla: `run_data_qc --no-cache --start 2017-08-17` → regime → levels → momentum → signal (**M9 demo2 dersi:** yalnız QC frame'leri tazelemez).
2. **QC RED → bildirim YAYIMLANMAZ**; yerine ⛔ SORUN NOTU üretilir (exit 3) — §A fail-closed kuralının cadence karşılığı.
3. **BAYAT bayrağı:** referans mumun slot'a yaşı eşiği aşarsa (BTC 6h · metaller/XU030 28h; takvim-duyarsız) bildirim "piyasa durumu İDDİASI içermez" damgasıyla yayımlanır.
4. **Restore (§A.5 cadence'e uygulanır):** fetch'li koşu sonrası `git checkout -- data/ reports/` (yalnız `reports/cadence/` KORUNUR) + `.state.json → assets` frozen baseline'a sıfırlanır (`last_fetch_utc` korunur — rate kapısı). Bildirim dosyaları günün kanıtı olarak kalır.
5. **Slot-ızgara hizası (M9b ile ÇÖZÜLDÜ):** BIST30 slotları artık v1.1 ızgara kapanışlarıyla birebir (14:00/18:00); referans mum kuralı aynıdır: "slot anında KAPALI olan son mum" + yaşı açıkça yazılır. Slot tablosu değişikliği kullanıcı onayı gerektirir (`scripts/cadence_4h_status.py → SLOTS_*`).
6. **XLSX paketi (M22, 2026-09-18):** zincir sonunda `python3 -W ignore scripts/export_trade_report_xlsx.py` → `reports/xlsx/trades_<asset>.xlsx` (TRADES/OZET/EGRI; kaynak reports/trades_*.csv, yeni analiz YOK). Aylık paketin parçası.
7. `reports/cadence/last_fetch.log` yerel operasyon logudur, commit EDİLMEZ (.gitignore).
8. **Viz tazeleme (M14/M15):** her `--fetch`'li cadence/§A koşusu zincirin sonunda
   `scripts/export_viz_payload.py` ile `viz/quant4h_viz_multi_<AY>.pine`
   (4 blok gömülü) ve varlık başına hazır `.pine` dosyalarını YENİLER. Pencere:
   `--bars N` (varsayılan 750 ≈ 4 ay, varlık veri tavanı + 90 KB kaynak bütçesiyle
   sınırlı; multi oto-daraltır); `--month YYYY-MM` opsiyonel override.
   Manuel: aynı komut. Payload ufku = son --fetch'li koşu; eski dosya = eski veri
   (pine banner'ında "payload ufku" satırı görünür). TAM geçmiş Pine'a GİREMEZ —
   yeri reports/CSV/run_dash (skills/pine/PINE_STYLE.md §4).
9. **Ajan skor kartı (M24, 2026-09-18):** aylık pakete `python3 -W ignore
   scripts/run_agent_eval.py` → `reports/eval/YYYY-MM-DD.md` (5 kriter; QUALITY
   insan rubric 1-5, `--quality N` ile PROGRESS'e işlenir; LLM-judge YOK).

**İlk koşu kanıtı (2026-09-18, 3 dosya):** `2026-09-18_1500.md` (fetch'siz → BAYAT yolu) · `2026-09-18_1900.md` (fetch'li: BTC +14 bar taze, referans yaş 0.0h, canlı final LONG sinyali YAKALANDI — EYLEM yine YOK; aynı fetch'te Yahoo rate-limit → GOLD/SILVER RED+BAYAT satırları dürüstçe basıldı, kapı öncesi koşu) · `2026-09-18_1800.md` (RED kapısı → ⛔ SORUN NOTU, exit 3).

## B) ÇEYREKLİK ÖN-KAYITLI YENİDEN DEĞERLENDİRME — PROTOKOL v1

**Amaç:** yeni veri biriktikçe hükmü ÇOKLU-TEST DİSİPLİNİYLE tazelemek. Bu, "bir bakış daha" serbestliği DEĞİL; sayılan, ön-kayıtlı ve loglanan tek yoldur.

**Frekans tavanı:** yılda **maksimum 4 look** (çeyreklik). Erken look YASAK (yeni çeyrek kapanmadan veri birikmez). Look hakkı DEVREDİLEMEZ/birikmez (kullanılmayan çeyrek yanar).

**Her look'un ZORUNLU sırası (sıra ihlali = hüküm geçersiz):**
1. **ÖN-KAYIT (koşudan ÖNCE, commit'li):** `register_splits.py` policy_version ARTIRILARAK (v2, v3, …) YENİ `configs/splits_preregistered.yaml` üretilir; eski sürüm SİLİNMEZ (arşiv geleneği v1.0'daki gibi). Yeni frozen snapshot'lar + sha256'lar yazılır. Look'un kapsamı (hangi varlıklar, hangi hücre kümesi — değişmez: {P0..P3}×{A0..A2}, a-priori hücreler ve önceki look'un seçimi) ve hipotez NOTU ön-kayıt dosyasına işlenir. **ÜNİVERSE DONDURMA (v1.2):** `configs/bist30_universe.yaml` sürümü look için doğrulanır ve ön-kayda `universe_version` + dosya sha256'sı yazılır; üyelik DEĞİŞMİŞSE yeni tarih damgalı sürüm eklenir (eski silinmez), **üyelik değişim logu** (çıkan/giren + gerekçe + kaynak) ön-kayda işlenir ve look raporunda "önceki look'la karşılaştırılabilirlik" notu ZORUNLUDUR.
2. **SEÇİM (yalnız yeni TRAIN):** `run_stage9.py --phase select` → seçim `selected_cells.yaml`'a YENİ hash'lerle dondurulur (eski seçim dosyası `selected_cells.v<N-1>.yaml` olarak arşivlenir, silinmez).
3. **VERDICT:** `run_stage9.py --phase verdict` — aynı kilitli eşikler (`go_no_go`: n≥100 core/150 basket · expR>0 · CI altı>0 · PF≥1.2 · maxDD≤%25) ANCAK CI düzeyi aşağıdaki **alpha-spending tarifesine** göre hesaplanır; aynı VALID sağduyu kuralı (negatifse TEST KOŞULMAZ), TEST **bu look'ta 1 kez**.
4. **LOG (§C) + PROGRESS bloğu + patch** (senkron kuralı).

**ALPHA-SPENDING TARİFESİ (v1.2, bağlayıcı — R03 azaltımı; kullanıcı onayı 2026-09-17):**
Tekrarlanan OOS bakışları çoklu-test yükü biriktirir; go/no-go'nun "CI altı > 0" koşulundaki güven düzeyi KÜMÜLATİF look sayısıyla SIKILAŞIR (gevşetilmez):

| kümülatif look (§C log'una göre) | bootstrap CI düzeyi |
|---|---|
| 1–4 | %95 (mevcut `bootstrap_ci` çıktısı) |
| 5–8 | **%97.5** |
| 9+ | **%99** |

Kurallar: (a) look numarası §C log'undan OKUNUR (beyan değil, kayıt); (b) Aşama 9 (2026-09-17) look **#1**'dir ve %95 ile koştu — tutarlı; (c) düzey değişikliği `run_stage9.py`'de kod güncellemesi gerektirir ve look ÖNCESİ commit'lenir (sonradan düzey seçmek YASAK); (d) bu tarife yalnız SIKILAŞTIRIR — `user_decisions.yaml → go_no_go` eşiklerinin gevşetilmesi hiçbir look'ta yapılamaz.

**Eşik/küme DEĞİŞİKLİĞİ YASAĞI:** go/no-go eşikleri, aday kümeleri, fill kuralları ve maliyet modelleri look'lar arasında DEĞİŞTİRİLEMEZ (değişiklik ancak kullanıcı onayı + yeni protokol sürümü v2 ile; eski hükümler yeniden yorumlanamaz).

**Hüküm kuralları:** GEÇTİ çıkarsa → varlık `paper_observe_candidate` olur; statü değişikliği YALNIZ kullanıcı onayıyla ve PROGRESS'e işlenerek (canlı emir HER HALÜKARDA kapsam dışı). KALDI/ZAYIF → watch_only devam; aynı varlık için bir sonraki look'tan önce EK analiz YASAK.

## C) LOOK LOG'U (zincirleme, silinmez, her look'ta 1 satır)

| # | tarih | ön-kayıt | seçili hücreler | TEST koşulan varlıklar | hükümler | look hakkı kaynağı |
|---|---|---|---|---|---|---|
| 1 | 2026-09-17 | v1.1 (`9e1cf2fe…`) · seçim `d7282b30…` | BTC `P2xA2`; GOLD/SILVER/BASKET a-priori `P0xA0` | GOLD, SILVER (BTC/basket: VALID reddi → KOŞULMADI) | GEÇTİ=0; BTC KALDI, basket KALDI, GOLD/SILVER ZAYIF | Aşama 9 (ilk mahkeme) |
| 2 | *(erken: ≥2026-12-17 çeyrek kapanışı)* | v2 (look ÖNCESİ yazılacak) | — | — | — | çeyreklik hak 1/4 |

*Yıllık look sayacı: 2026 → 1/4 kullanıldı (Aşama 9). 2027 takvim yılında sayaç sıfırlanır.*

**Look başına ZORUNLU kayıt alanları (v1.2):** kümülatif look no + uygulanan alpha-spending düzeyi (CI%) · `universe_version` + sha256 (değiştiyse üyelik değişim logu referansı) · ön-kayıt policy sürümü + dosya sha256'sı · seçim dosyası sha256'sı · TEST koşulan varlıklar ve hükümler.

## D) PROTOKOL İHLALİ TANIMI VE YAPTIRIMI

**İhlal:** ön-kayıtsız look · TEST'e ikinci bakış · eşik/küme/fill değişikliğiyle yeniden koşum · seçim dosyasının hash'i kırıkken verdict · aylık raporda P&L/pozisyon üretimi · look tavanının aşımı.
**Yaptırım:** ihlalle üretilen TÜM sayılar **HÜKÜMSÜZDÜR** (raporlara "PROTOKOL İHLALİ — hüküm üretmez" damgası vurulur), ihlal PROGRESS'e DÜZELTME bloğuyla işlenir, meşru hüküm yalnız ihlal ÖNCESİ son geçerli kayıttır (şu an: `reports/final_verdict.md`, 2026-09-17).

## E) VERİ HİJYENİ (watch_only sırasında)

- Canlı veri büyür: `drift_report` BİLGİDİR; frozen snapshot'lara DOKUNULMAZ. Yeni barlar ancak §B.1 ön-kaydıyla çalışmaya girer.
- QC RED → o varlıkta izleme raporu yayımlanmaz (fail-closed). AMBER → caveat'lerle yayımlanır.
- Kesinti hijyeni: her iş parçası PROGRESS'ten takip edilir; kaldığı yerden devam eder, ASLA baştan başlamaz (≤25 satırlık parçalar).
- Senkron: her teslim = local commit + `patches/stageN.patch` (`git format-patch <son-senkron>..HEAD --stdout`); kullanıcı `git am` + push yapar (token sohbete girmez).

## F) YENİ HİPOTEZLER

Bu proje araştırma-kapalıdır. Yeni hipotez (yeni varlık, yeni kural, yeni mimari) bu repoda AÇILMAZ; **YENİ PROJE** olarak aynı kapı pipeline'ına girer: ön-kayıt → inşa → OOS hüküm. quant4h'un protokol varlıkları (split politikası, go/no-go, look disiplini) şablon olarak KULLANILABİLİR; sonuçları yeni projeye kanıt olarak TAŞINAMAZ.

---
*Bu runbook yatırım tavsiyesi değildir. watch_only statüsü, kullanıcı onayı + PROGRESS kaydı olmadan değiştirilemez.*
