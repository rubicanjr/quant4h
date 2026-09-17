# quant4h — NİHAİ HÜKÜM (final verdict)

*Tarih: 2026-09-17 · Durum: **ARAŞTIRMA-KAPALI · watch_only** · Bu belge Aşama 9 hükmünün DEĞİŞMEZ kaydıdır. Yeniden seçim, tune veya "bir bakış daha" YOKTUR (çoklu-test disiplini; kullanıcı onayı 2026-09-17).*

---

## 1) HÜKÜM TABLOSU — varlık başına + ölüm nedeni

| Varlık | Hücre | HÜKÜM | **Ölüm nedeni** | Kanıt (OOS, ön-kayıtlı pencereler) |
|---|---|---|---|---|
| **BTC** | `P2xA2` (TRAIN'de seçildi) | **KALDI** | **EDGE** (örneklem değil): VALID beklenen değeri NEGATİF | VALID n=7, expR **−0.321**, CI95 [−0.463, −0.173] → sağduyu başarısız; TEST protokol gereği KOŞULMADI (ikinci şans yok) |
| **GOLD** | `P0xA0` (a-priori; TRAIN n=12<50 → seçim YAPILAMADI) | **ZAYIF (örneklem)** | **ÖRNEKLEM**: OOS n=16 < min 100 — edge hükmü VERİLEMEZ (ne var ne yok) | VALID n=6 expR +1.358 · TEST n=10 expR +0.343 · OOS expR +0.724 CI [−0.011, +1.526] — yön pozitif ama güç YOK |
| **SILVER** | `P0xA0` (a-priori; TRAIN n=13<50) | **ZAYIF (örneklem)** | **ÖRNEKLEM**: OOS n=19 < min 100 | VALID n=8 expR +0.902 · TEST n=11 expR **−0.279** · OOS expR +0.218 CI 0'ı içeriyor |
| **BIST30 sepet** | `P0xA0` (a-priori; TRAIN n=**0**) | **KALDI** | **EDGE + ÖRNEKLEM**: VALID expR negatif VE havuz 74<150 | VALID n=74, expR **−0.057**, CI [−0.332, +0.238], PF 0.70 → sağduyu başarısız; TEST KOŞULMADI. TRAIN=0'ın nedeni yapısal: 500 bar rejim ısınması, BIST grid'inde (2 bar/gün) ≈250 iş günü = TRAIN penceresinin TAMAMI |
| **CORE agregat** | (üye hücreleri) | **ZAYIF (örneklem)** | **ÖRNEKLEM**: OOS n=42 < 100 | expR +0.321 CI [−0.111, +0.781] — BTC'nin negatif VALID'i agregata dahil (not: BTC yalnız VALID ile katıldı) |
| **PORTFÖY-sepet** | — | **KALDI** | Üye varlık hükmü KALDI (VALID sağduyu) + örneklem 74<150 | expR −0.057 · PF 0.701 · maxDD(yol) −10.35% |

**GENEL: GEÇTİ = 0 → paper/observe adayı YOK. Tüm varlıklar `watch_only`.**

Ölüm nedeni ayrımı (bağlayıcı tanım):
- **EDGE öldü** = OOS beklenen değer negatife düştü (VALID sağduyu veya OOS havuz eşikleri) → sistem bu varlıkta ölçülen dönemde edge GÖSTEREMEDİ.
- **ÖRNEKLEM öldü** = eşikler için yeterli trade yok → edge VAR mı YOK mu SÖYLENEMEZ; "kazanıyor" da "kaybediyor" da denemez.

## 2) PROTOKOL GÜNLÜĞÜ (zincir tamamı kayıtlı)

| adım | kayıt |
|---|---|
| Ön-kayıt (split'ler) | `configs/splits_preregistered.yaml` policy **v1.1** · dosya sha256 `9e1cf2fe4d16c94e281a919b8cd2bb6185df7be6f9914ecc2a25010c2b7afcb7` · v1.0 arşivde (silinmedi) |
| Frozen veri kilitleri (H17) | BTC `aab99f83c757…` · GOLD `f7d53a8ead74…` · SILVER `1df18551a0d2…` · BIST30 `ddc9669d896f…` · basket `218de18b6158…` — `register_splits.py --check` her aşamada EXIT 0 |
| Seçim dondurması | `configs/selected_cells.yaml` · üretildi **2026-09-17T11:59:55Z** · dosya sha256 **`d7282b303e03b207d818304f40f2139d7e5fa7f72bb232b670108481f17b4c44`** · BTC→`P2xA2` (TRAIN n=175, expR +0.2913, argmax 12 hücre) · GOLD/SILVER/BASKET → seçim YOK (TRAIN<50), a-priori `P0xA0` · verdict fazı bu hash'leri doğrulamadan TEST'i REDDEDER (test ile kilitli) |
| **look sayısı (TEST)** | **1** — yalnız GOLD+SILVER (2026-09-17T12:04:38Z). BTC ve basket TEST'i HİÇ koşulmadı (VALID sağduyu reddi). Yeniden bakış YOK (onay 2026-09-17). |
| Çoklu-test disiplini | 12 hücre yalnız TRAIN'de karşılaştırıldı (tek argmax); VALID yalnız sağduyu; TEST tek look; eşikler `user_decisions.yaml → go_no_go` (Aşama 6 denetimi D1 ile kayda alınmıştı) |
| Monte Carlo | OOS dizileri, B=1000, seed 42: P(maxDD>%25)=0.00 · P(ruin<%50)=0.00 — küçük örneklemda GÜVENLİK KANITI DEĞİL |
| Duyarlılık | BTC `P2xA2` − en iyi komşu `P3xA2` = +0.017R (< 0.25 eşik) → overfit sivrilik bayrağı YOK |
| Denetim zinciri | Aşama 6 denetimi 10/10 (`stage6_audit.md`) → Aşama 7 grid (SEÇİM YOK, `stage7_exit_grid.md`) → Aşama 8 risk (tavanlar, regresyon kilidi, `stage8_risk.md`) → Aşama 9 hüküm (`stage9_oos_verdict.md`) · suite **223/223** |

## 3) IN-SAMPLE BAĞLAM (karar değeri YOKTUR — yalnız dürüstlük kaydı)

Aşama 6/7/8 in-sample ölçümleri (BTC net +%15.5, PF 1.31; sepet ≈ başabaş; hiçbir varlık buy&hold'u geçemedi; tavanlar DD'yi −%17.7→−%7.8 indirdi) OOS'ta edge KANITI DEĞİLDİR. 2024–2026 dönemi şiddetli tek yönlü boğa piyasasıydı; düşük maruziyetli %0.5 riskli sistem bu dönemde buy&hold karşısında yapısal olarak geride kalır. Bu raporların hiçbiri "sistem para kazanır" demez ve diyemez.

## 4) HÜKMÜ DEĞİŞTİREBİLECEK TEK YOL

`ops_runbook.md` → çeyreklik **ÖN-KAYITLI** yeniden değerlendirme (maks 4 look/yıl, her look'ta YENİ split ön-kaydı v2/v3…, aynı kilitli eşikler, look log'u zorunlu) veya YENİ hipotezin **YENİ PROJE** olarak aynı kapı pipeline'ına girmesi (ön-kayıt → inşa → OOS hüküm). Ön-kayıtsız her bakış protokol ihlalidir ve hüküm üretmez.

## 5) ZORUNLU CAVEAT'LER (hükme eşlik eder)

Survivorship bias (BIST30 sepeti — yalnız bugünkü üyeler; sonuçları YUKARI çeker, buna rağmen KALDI) · metaller ~2.4 yıl intraday (Yahoo 730 gün limiti) · TEST penceresi 159 gün (BTC) — tek başına güçsüz · metals feed'inde roll belirsizliği (FLAG-ONLY politika) · 2026-01-26..02-06 düşük-kalite pencere (SILVER TEST aralığında; teşhis kayıtlı) · tek fold walk-forward · BIST ince-bar/açılış temsiliyeti kısıtı (09:30-10:00 4H'de yok).

*Bu belge yatırım tavsiyesi DEĞİLDİR. Sistem watch_only'ddir: emir yok, pozisyon yok, tavsiye yok.*
