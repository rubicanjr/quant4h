# AŞAMA 3 — Yapısal Seviyeler ve Yapısal Stop Raporu

*Üretim: 2026-09-16T13:57:15 UTC* · timeframe **4h** · buffer **1.0 ATR** (varsayılan)

## POLİTİKA

- **Swing:** 3-bar fraktal. Onay gecikmesi **4 bar** (p konumlu swing ancak `p+k` barı KAPANDIĞINDA görünür). Lookback 120 bar.
- **Donchian(20):** son 20 **KAPANMIŞ** bar (`shift(1)`); mevcut bar pencereye GİRMEZ. Pencere geçerlilik oranı < 0.9 ise seviye **NaN** (fail-closed).
- **Anchor kısıtı:** `return_valid==False, non_tradable==True, halt_or_limit_flag==True, OHLC NaN veya <=0` → bu barlar ne swing ne Donchian anchor'ı olabilir. **FLAG-ONLY**: veri silinmez, sadece seviye üretimine katılmaz.
- **Yapısal stop:** long = onaylı `swing_low − 1.0×ATR`; short (yalnız core) = onaylı `swing_high + 1.0×ATR`. Stop **girişten önce** belli ve **DONDURULMUŞ** (`FrozenStop`; `widen/move_against/relax` → `StopImmutabilityError`).
- **Buffer seçimi YOK:** aday küme `[0.5, 1.0, 1.5]` yalnızca **Aşama 9**'da test edilir. `selection_now=False`
- **Hisse başına in-sample parametre seçimi:** `False` (YASAK). Parametre seçimi Aşama ['BTC', 'GOLD', 'SILVER'] üzerinde, Aşama 9'da.
- **Hisselerde short:** `False` (LONG-ONLY, KARAR 4).
- **Yeni indikatör:** YOK · grafik öğeleri: `['candles', 'EMA200', 'structural_stop/target']` (maks 3).

## ZORUNLU NOT (PROGRESS'e işlendi)

> BIST30 hisselerinde **warmup** nedeniyle TRAIN döneminde etiketli bar sayısı azdır. Bu yüzden **hiçbir aşamada hisse başına in-sample parametre seçimi YAPILMAYACAK**. Parametre seçimi Aşama 9'da, küçük bir aday kümesiyle ve yalnızca **core varlıklar** (BTC / GOLD / SILVER) üzerinde yapılacak; hisseler **yalnızca OOS** raporlanacak. Bu kural `config.PER_ASSET_IN_SAMPLE_TUNING_ALLOWED=False` ile kod düzeyinde kilitlidir.

## CORE VARLIKLAR + BAĞLAM ENDEKSİ

| Varlık | rol | bar | anchor_ok % | swing_low | swing_high | Donchian % | breakout ↑ | breakout ↓ | temas Donch ↑ | temas Donch ↓ | temas swing_low | stop_long (ATR) | stop_long (% fiyat) | stop_short (ATR) | planlanabilir long % |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **BTC** | core_tradable | 19888 | 100.0 | 2014 | 2014 | 99.9 | 1449 | 1216 | 2123 | 1663 | 4440 | 2.58 | 4.11 | 2.29 | 92.1 |
| **GOLD** | core_tradable | 3606 | 99.1 | 338 | 313 | 99.5 | 347 | 192 | 598 | 277 | 752 | 2.91 | 2.01 | 2.19 | 92.2 |
| **SILVER** | core_tradable | 3606 | 99.1 | 331 | 316 | 99.5 | 336 | 233 | 535 | 316 | 800 | 2.85 | 3.65 | 2.14 | 91.4 |
| **BIST30** | context_filter_source | 1435 | 98.2 | 111 | 109 | 98.7 | 141 | 97 | 241 | 159 | 354 | 3.24 | 4.33 | 2.32 | 86.6 |

## BIST30 HİSSE SEPETİ — STOP MESAFESİ VE OLAY SAYILARI

| Hisse | sektör | bar | anchor_ok % | swing_low | swing_high | Donchian % | breakout ↑ | temas swing_low | swing_low kapanış-altı | **stop_long (ATR)** | **stop_long (% fiyat)** | planlanabilir % | FINAL long | short üretildi |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **AEFES** | içecek | 1436 | 97.2 | 110 | 114 | 92.7 | 141 | 315 | 253 | **3.01** | **6.84** | 88.6 | 316 (22.0%) | ✅ hayır |
| **AKBNK** | banka | 1436 | 97.3 | 107 | 113 | 93.7 | 141 | 341 | 293 | **3.21** | **7.00** | 86.4 | 431 (30.0%) | ✅ hayır |
| **ASELS** | elektronik/savunma | 1436 | 97.6 | 101 | 115 | 94.9 | 139 | 268 | 211 | **3.35** | **7.64** | 91.6 | 563 (39.2%) | ✅ hayır |
| **ASTOR** | elektrik ekipman | 1436 | 97.6 | 106 | 123 | 95.5 | 130 | 397 | 338 | **2.76** | **7.01** | 84.8 | 464 (32.3%) | ✅ hayır |
| **BIMAS** | perakende | 1436 | 96.5 | 102 | 110 | 88.3 | 137 | 289 | 225 | **3.17** | **6.08** | 91.3 | 564 (39.3%) | ✅ hayır |
| **EKGYO** | GYO | 1436 | 97.5 | 113 | 118 | 94.7 | 140 | 341 | 270 | **2.91** | **6.87** | 88.8 | 450 (31.3%) | ✅ hayır |
| **ENKAI** | inşaat | 1436 | 96.6 | 105 | 120 | 89.5 | 118 | 352 | 289 | **2.82** | **5.67** | 87.4 | 438 (30.5%) | ✅ hayır |
| **EREGL** | demir-çelik | 1436 | 97.6 | 122 | 105 | 94.5 | 139 | 342 | 277 | **2.89** | **5.04** | 86.2 | 376 (26.2%) | ✅ hayır |
| **FROTO** | otomotiv | 1436 | 96.9 | 93 | 99 | 91.8 | 121 | 432 | 359 | **2.56** | **4.56** | 83.2 | 206 (14.3%) | ✅ hayır |
| **GARAN** | banka | 1436 | 97.6 | 101 | 106 | 94.8 | 124 | 325 | 261 | **3.25** | **6.65** | 87.5 | 404 (28.1%) | ✅ hayır |
| **GUBRF** | kimya/gübre | 1436 | 96.5 | 107 | 109 | 95.9 | 134 | 387 | 334 | **2.79** | **6.99** | 84.5 | 508 (35.4%) | ✅ hayır |
| **ISCTR** | banka | 1435 | 97.5 | 115 | 100 | 94.8 | 121 | 372 | 317 | **2.87** | **6.17** | 85.3 | 374 (26.1%) | ✅ hayır |
| **KCHOL** | holding | 1436 | 97.6 | 107 | 108 | 94.6 | 106 | 379 | 316 | **2.92** | **5.34** | 85.0 | 393 (27.4%) | ✅ hayır |
| **KRDMD** | demir-çelik | 1436 | 97.9 | 106 | 109 | 97.4 | 136 | 372 | 301 | **2.76** | **6.61** | 88.7 | 474 (33.0%) | ✅ hayır |
| **MGROS** | perakende | 1436 | 97.1 | 105 | 103 | 91.9 | 132 | 322 | 246 | **3.06** | **5.81** | 88.8 | 433 (30.1%) | ✅ hayır |
| **PETKM** | petrokimya | 1436 | 98.1 | 114 | 112 | 98.7 | 123 | 375 | 310 | **2.79** | **5.56** | 87.6 | 214 (14.9%) | ✅ hayır |
| **PGSUS** | havacılık | 1436 | 98.2 | 104 | 112 | 98.7 | 109 | 394 | 316 | **2.72** | **4.82** | 86.5 | 143 (10.0%) | ✅ hayır |
| **SAHOL** | holding | 1436 | 97.6 | 120 | 124 | 94.8 | 118 | 355 | 285 | **2.88** | **6.05** | 86.8 | 376 (26.2%) | ✅ hayır |
| **SASA** | tekstil/kimya | 1436 | 97.6 | 91 | 83 | 97.6 | 93 | 445 | 373 | **2.38** | **5.85** | 81.8 | 52 (3.6%) | ✅ hayır |
| **SISE** | cam | 1435 | 97.4 | 100 | 110 | 94.7 | 100 | 469 | 396 | **2.59** | **4.35** | 81.5 | 255 (17.8%) | ✅ hayır |
| **TAVHL** | havacılık/havalimanı | 1436 | 98.0 | 106 | 108 | 97.4 | 143 | 373 | 302 | **2.85** | **5.85** | 87.3 | 340 (23.7%) | ✅ hayır |
| **TCELL** | telekom | 1436 | 97.4 | 115 | 117 | 93.5 | 115 | 357 | 279 | **2.65** | **5.46** | 89.8 | 370 (25.8%) | ✅ hayır |
| **THYAO** | havacılık | 1436 | 97.8 | 108 | 110 | 96.1 | 120 | 361 | 298 | **2.76** | **4.46** | 86.1 | 330 (23.0%) | ✅ hayır |
| **TOASO** | otomotiv | 1436 | 97.6 | 105 | 102 | 94.5 | 131 | 440 | 351 | **2.60** | **5.58** | 85.3 | 341 (23.8%) | ✅ hayır |
| **TTKOM** | telekom | 1436 | 98.0 | 109 | 116 | 98.7 | 143 | 290 | 213 | **2.89** | **6.22** | 90.7 | 333 (23.2%) | ✅ hayır |
| **TUPRS** | enerji/rafineri | 1436 | 97.2 | 102 | 96 | 92.2 | 131 | 365 | 287 | **3.12** | **5.45** | 87.1 | 416 (29.0%) | ✅ hayır |
| **VAKBN** | banka | 1436 | 97.8 | 101 | 116 | 97.6 | 123 | 382 | 313 | **2.84** | **6.60** | 85.5 | 427 (29.7%) | ✅ hayır |
| **YKBNK** | banka | 1436 | 97.8 | 107 | 96 | 97.3 | 131 | 354 | 293 | **3.06** | **6.79** | 86.3 | 440 (30.6%) | ✅ hayır |
| **MEDYAN (28 hisse)** | | | 97.6 | | | 94.8 | 130 | | | **2.86** | **5.95** | 86.7 | 26.8% | ✅ |

Stop mesafesi hisse bazında **2.38 – 3.35 ATR** (medyan 2.86) ve **%4.35 – %7.64** fiyat (medyan %5.95) arasında.

## DURDURMA MESAFESİNİN SONUÇLARI (yorum)

- Eşit-risk politikasında pozisyon büyüklüğü = `risk_per_trade / stop_mesafesi`. Yani **geniş yapısal stop = küçük pozisyon**. Bu bir hata değil, tasarımın doğrudan sonucudur ve stop'un yapısal (swing) olması bedelidir.
- Medyan stop mesafesi ATR cinsinden 1'in çok üstündeyse (ör. 3 ATR) bunun iki sebebi olabilir: (a) son onaylı swing gerçekten uzakta, (b) `swing_lookback` çok geniş. **Aşama 7'de** alternatif anchor'lar (Donchian-low, daha yakın swing) ve partial+runner/trailing yöntemleri test edilecek; **şimdi seçim yapılmıyor**.
- `planlanabilir %` = stop'un gerçekten DONDURULABİLDİĞİ bar oranı. Düşükse fail-closed çalışıyor demektir: seviye bilinmiyorsa **işlem yok**.

## FİNAL LONG İZNİNİN BİLEŞİMİ (hisseler)

```
long_final_ok = long_regime_ok      # trend_up VE ATR yüzdeliği <= tavan   (Aşama 2)
              AND longs_allowed      # XU030 4H kapanış > EMA200, KAPANMIŞ bar (Aşama 2)
              AND NOT non_tradable   # kesinti / ince açılış barı / oluşuyor / kurumsal aksiyon
              AND return_valid       # boşluğu veya ex-date'i atlayan getiri DEĞİL
              AND stop_valid_long    # DONDURULABİLİR yapısal stop VAR  (Aşama 3)
```
