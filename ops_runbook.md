# ops_runbook.md — quant4h watch_only operasyon el kitabı

*Sürüm: v1 (2026-09-17, kullanıcı onaylı) · Statü: **watch_only / araştırma-kapalı** · Bağlayıcı kaynaklar: `PROGRESS.md`, `configs/user_decisions.yaml`, `reports/final_verdict.md`*

> **KURAL 0:** Bu runbook trade üretmez. Her çıktının üzerinde `watch_only — trade YOK, emir YOK, tavsiye YOK` başlığı bulunur. Sistem edge KANITLAYAMADI (GEÇTİ=0); hiçbir izleme çıktısı "sistem çalışıyor/kazanıyor" şeklinde YORUMLANAMAZ.

---

## A) AYLIK SİNYAL İZLEME RAPORU (trade YOK)

**Amaç:** veri hattının canlı olduğunu ve sinyal zincirinin fail-closed davranışını doğrulamak; edge izlenimi vermek DEĞİL.

**Ne zaman:** her ayın ilk iş günü (veri tazeliği QC'den geçtikten sonra).

**Adımlar (mevcut script'ler — YENİ kod yazılmaz):**
1. `python3 -W ignore scripts/run_data_qc.py --assets BTC GOLD SILVER BIST30 --timeframe 4h --min-rows 1500` → QC kararı RED olan varlık varsa rapor **YAYIMLANMAZ** (fail-closed), sorun notu düşülür. (H14: resample→adjust→QC tek komutta; `run_adjust.py` ayrıca ÇALIŞTIRILMAZ.)
2. `run_regime_report.py` → `run_levels_report.py` → `run_momentum_report.py` → `run_signal_report.py` (sıra bağlayıcı; zincir kolonları bir öncekine dayanır).
3. Elle derleme (rapor şablonu §A1): son 30 günün ham/final sinyal sayaçları (strict/capped/cooldown_only akışları), rejim dağılımı, XU030 bağlam durumu, `rejected_no_valid_stop` ve `non_tradable` sayaçları, veri kesintisi/roll adayları.
4. `git` hijyeni: aylık rapor `reports/monitor/YYYY-MM.md` olarak commit edilir (patch senkron kuralı PROGRESS'te).

**YASAK:** aylık raporda P&L, "şu sinyali izleseydin kazanç" hesabı, pozisyon önerisi, eşik/parametre değişikliği, sinyallerin kağıt-portföye bağlanması. İhlal = protokol ihlali (bkz. §D).

### A1) Aylık rapor şablonu (asgari alanlar)
```
# watch_only aylık izleme — <YYYY-MM>  (trade YOK, emir YOK, tavsiye YOK)
- QC kararları: BTC/GOLD/SILVER/BIST30 (AMBER/RED) + veri tazelik
- Rejim: her varlıkta son barın durumu (6'lı) + bağlam (XU030 EMA200 üstü/altı)
- Sinyal sayaçları (30 gün): ham → final (akış bazında), bastırılan (pozisyon/cooldown)
- Reddedilen girişler: no_valid_stop / not_tradable / geometry
- Veri olayları: kesinti penceresi, roll/bad-print adayları, kurumsal aksiyon bayrakları
- Sapma notu: bu ay protokol dışı HİÇBİR şey yapıldı mı? (varsayılan: HAYIR)
```

## B) ÇEYREKLİK ÖN-KAYITLI YENİDEN DEĞERLENDİRME — PROTOKOL v1

**Amaç:** yeni veri biriktikçe hükmü ÇOKLU-TEST DİSİPLİNİYLE tazelemek. Bu, "bir bakış daha" serbestliği DEĞİL; sayılan, ön-kayıtlı ve loglanan tek yoldur.

**Frekans tavanı:** yılda **maksimum 4 look** (çeyreklik). Erken look YASAK (yeni çeyrek kapanmadan veri birikmez). Look hakkı DEVREDİLEMEZ/birikmez (kullanılmayan çeyrek yanar).

**Her look'un ZORUNLU sırası (sıra ihlali = hüküm geçersiz):**
1. **ÖN-KAYIT (koşudan ÖNCE, commit'li):** `register_splits.py` policy_version ARTIRILARAK (v2, v3, …) YENİ `configs/splits_preregistered.yaml` üretilir; eski sürüm SİLİNMEZ (arşiv geleneği v1.0'daki gibi). Yeni frozen snapshot'lar + sha256'lar yazılır. Look'un kapsamı (hangi varlıklar, hangi hücre kümesi — değişmez: {P0..P3}×{A0..A2}, a-priori hücreler ve önceki look'un seçimi) ve hipotez NOTU ön-kayıt dosyasına işlenir.
2. **SEÇİM (yalnız yeni TRAIN):** `run_stage9.py --phase select` → seçim `selected_cells.yaml`'a YENİ hash'lerle dondurulur (eski seçim dosyası `selected_cells.v<N-1>.yaml` olarak arşivlenir, silinmez).
3. **VERDICT:** `run_stage9.py --phase verdict` — aynı kilitli eşikler (`go_no_go`: n≥100 core/150 basket · expR>0 · CI altı>0 · PF≥1.2 · maxDD≤%25), aynı VALID sağduyu kuralı (negatifse TEST KOŞULMAZ), TEST **bu look'ta 1 kez**.
4. **LOG (§C) + PROGRESS bloğu + patch** (senkron kuralı).

**Eşik/küme DEĞİŞİKLİĞİ YASAĞI:** go/no-go eşikleri, aday kümeleri, fill kuralları ve maliyet modelleri look'lar arasında DEĞİŞTİRİLEMEZ (değişiklik ancak kullanıcı onayı + yeni protokol sürümü v2 ile; eski hükümler yeniden yorumlanamaz).

**Hüküm kuralları:** GEÇTİ çıkarsa → varlık `paper_observe_candidate` olur; statü değişikliği YALNIZ kullanıcı onayıyla ve PROGRESS'e işlenerek (canlı emir HER HALÜKARDA kapsam dışı). KALDI/ZAYIF → watch_only devam; aynı varlık için bir sonraki look'tan önce EK analiz YASAK.

## C) LOOK LOG'U (zincirleme, silinmez, her look'ta 1 satır)

| # | tarih | ön-kayıt | seçili hücreler | TEST koşulan varlıklar | hükümler | look hakkı kaynağı |
|---|---|---|---|---|---|---|
| 1 | 2026-09-17 | v1.1 (`9e1cf2fe…`) · seçim `d7282b30…` | BTC `P2xA2`; GOLD/SILVER/BASKET a-priori `P0xA0` | GOLD, SILVER (BTC/basket: VALID reddi → KOŞULMADI) | GEÇTİ=0; BTC KALDI, basket KALDI, GOLD/SILVER ZAYIF | Aşama 9 (ilk mahkeme) |
| 2 | *(erken: ≥2026-12-17 çeyrek kapanışı)* | v2 (look ÖNCESİ yazılacak) | — | — | — | çeyreklik hak 1/4 |

*Yıllık look sayacı: 2026 → 1/4 kullanıldı (Aşama 9). 2027 takvim yılında sayaç sıfırlanır.*

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
