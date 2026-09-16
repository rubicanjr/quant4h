# Faz 1 - Veri Kalitesi Raporu (Data Quality Report)

*Uretim zamani: 2026-09-16 13:56:31 UTC*  
*Bu rapor ham veriyi degistirmez; sadece tespit eder. Temizlik ayri ve loglanan bir adimdir.*

## Ozet

| Varlik | Sembol | Mod | TF | Bar | Ilk bar | Son bar | Karar | ERROR | WARN | Gecmis yeterli | Model icin uygun |
|---|---|---|---|---:|---|---|---|---:|---:|---|---|
| BTC | `BTCUSDT` | **core** | 4h | 19888 | 2017-08-17 | 2026-09-16 | **AMBER** | 0 | 3 | EVET | EVET |
| GOLD | `XAUUSD_PROXY_GC` | **core** | 4h | 3606 | 2024-04-24 | 2026-09-16 | **AMBER** | 0 | 8 | EVET | EVET |
| SILVER | `XAGUSD_PROXY_SI` | **core** | 4h | 3606 | 2024-04-24 | 2026-09-16 | **AMBER** | 0 | 9 | EVET | EVET |
| BIST30 | `XU030_INDEX` | **watch_only** | 4h | 1435 | 2023-10-27 | 2026-09-15 | **AMBER (insufficient history)** | 0 | 13 | HAYIR | HAYIR |

**Cekirdek backtest portfoyu:** BTC, GOLD, SILVER  
**Izleme modu (portfoye zorla sokulmaz):** BIST30

## ZORUNLU CAVEAT'LER (kullanici karari - her raporda aynen tasinir)

**BTC**

- :warning: BTCUSDT SPOT serisi sinyal verisidir. Funding yalnizca maliyet/baglam katmanidir; PERP SINYALI URETILMEZ.
**GOLD**

- :warning: GC=F ON-AY vadeli serisidir: roll gap duzeltmesi yapilmadan ham getiri serisi KULLANILAMAZ. Roll tespiti (gap > esik ATR) zorunludur. requires_adjustment=True oldugu icin duzeltme calistirilana kadar QC bu varligi 'model icin uygun DEGIL' olarak isaretler.
- :warning: Intraday gecmis ~2.4 yil ile sinirlidir (Yahoo 1h limiti 730 gun).
- :warning: TESPIT (KARAR 3): 2026-01-30 15:00 UTC -> 2026-02-02 18:00 UTC arasinda 75 saatlik VERI KESINTISI var (normal hafta sonu 80 bar; burada Pazartesi 00:00-15:00 UTC de kayip). 2026-02-02 gunu yalnizca 5 bar gelmis (normal ~23). Kesintiyi atlayan -%7.97'lik getiri NE ROLL NE BAD PRINT'tir: SAHTE bir getiridir. BAR SILINMEZ, 'boslugu atlayan getiri' olarak isaretlenir ve getiri/roll hesaplarinda HARIC TUTULUR.
- :warning: UYARI: 2026-01-26 .. 2026-02-06 penceresinde fiyat 5.626 -> 4.653 arasinda (yaklasik -%17) savruluyor ve gunluk hacim onceki donemin %38'ine dusuyor. Feed kalitesi bu pencerede DUSUK; ayni kesinti SILVER'da da birebir ayni tarihlerde goruluyor (Yahoo kaynakli ortak sorun). Bu doneme dayandirilan sonuclara guvenilmez, egitim/validasyonda ayrica isaretlenmelidir.
**SILVER**

- :warning: SI=F ON-AY vadeli serisidir: roll gap duzeltmesi zorunludur. requires_adjustment=True oldugu icin duzeltme calistirilana kadar QC bu varligi 'model icin uygun DEGIL' olarak isaretler.
- :warning: Intraday gecmis ~2.4 yil ile sinirlidir (Yahoo 1h limiti 730 gun).
- :warning: TESPIT (KARAR 3): 2026-02-02'deki tek barlik -%22 hareket incelendi. SONUC: bu NE ROLL NE BAD PRINT'tir. 2026-01-30 15:00 UTC -> 2026-02-02 18:00 UTC arasinda 75 saatlik VERI KESINTISI var (normal hafta sonu 80 bar; burada Pazartesi 00:00-15:00 UTC de kayip) ve 2026-02-02 gunu yalnizca 5 bar gelmis (normal ~23). Dolayisiyla -%22, veri boslugunu atlayan SAHTE bir getiridir. BAR SILINMEZ; 'boslugu atlayan getiri' olarak isaretlenir ve getiri/roll/label hesaplarinda HARIC TUTULUR.
- :warning: UYARI: 2026-01-26 .. 2026-02-06 penceresinde fiyat 121.79 -> 66.88 arasinda (yaklasik -%45) savruluyor ve gunluk hacim onceki donemin %42'sine dusuyor. Ayni kesinti GOLD'da da birebir ayni tarihlerde var (Yahoo kaynakli ortak sorun). Bu pencerede feed kalitesi COK DUSUK; model egitimi/validasyonunda ayrica isaretlenmeli, sonuclar bu doneme dayandirilmamali.
**BIST30**

- :warning: BIST30 dogrudan trade edilemez: XU030.IS endeksin kendisidir. Execution VIOp XU030 vadeli maliyet modeliyle VARSAYIMSAL olarak modellenir.
- :warning: Hacim verisi YOKTUR (her bar 0). Hacim/onay bacagi bu varlikta KULLANILMAZ; cift onay burada trend + momentum ile sinirlidir.
- :warning: Gecmis sadece ~2.9 yil. 4H bar sayisi ~2.157 gorunur ama bunun ~721 adedi yalnizca 09:30 ACILIS ANI printini iceren INCE barlardir; TAM 4H bar sayisi ~1.436'ddir. BTC'nin 19.888 bariyla karsilastirildiginda istatistiksel guc COK DUSUKTUR; sonuclar yalnizca yon gosterir, kesinlik iddia edilemez.
- :warning: Alternatif VIOp XU030 futures gecmisi bulunamadigi surece BIST30 backtest portfoyune ZORLA SOKULMAZ, izleme modunda kalir.
- :warning: 4H grid faz farki: BIST30 barlari 07/11 UTC'de, BTC barlari 00/04/08 UTC'de acilir. Bu yuzden varliklar arasi korelasyon YALNIZCA GUNLUK bazda hesaplanir; 4H seviyesinde ortak bar yoktur (n=0).

## BTC (`BTCUSDT`) - 4h

**Karar: AMBER** | mod: **core** | bar: 19888 | aralik: 2017-08-17T04:00:00+00:00 -> 2026-09-16T08:00:00+00:00

### Metrikler

| Metrik | Deger |
|---|---|
| `grid_anchor_tz` | UTC |
| `grid_anchor_local` | 00:00 |
| `distinct_utc_hours` | [0, 4, 8, 12, 16, 20] |
| `expected_bars` | 19909 |
| `missing_bar_fraction` | 0.0010548 |
| `bars_per_session_observed` | 6 |
| `gap_threshold_bars` | 50 |
| `zero_range_bars` | 1 |
| `gap_anomaly_tolerance_bars` | 13 |
| `bars_crossing_data_gap` | 0 |
| `bars_crossing_gap_frac` | 0 |
| `gap_anomaly_rule` | gap > modal_gap(dayofweek, local_hour) + 13 bars (seans bazlı: 24/7 ise 2 seans, değilse 8 seans; tavan 25 bar; bps=6.0) |
| `abs_logret_max_raw_incl_gaps` | 0.271624 |
| `bars_after_normal_session_gap` | 8 |
| `abs_logret_median` | 0.00501008 |
| `abs_logret_p99` | 0.0541258 |
| `abs_logret_max` | 0.271624 |
| `outlier_return_count` | 286 |
| `outlier_range_count` | 169 |
| `outlier_contiguous_count` | 2 |
| `volume_zero_fraction` | 5.02816e-05 |
| `volume_total` | 1.95941e+08 |
| `volume_vs_range_corr` | 0.293231 |
| `optional_populated` | ['quote_volume', 'trades', 'taker_buy_volume'] |
| `optional_partial_nan` | [] |
| `last_bar_age_hours` | 5.94199 |
| `last_bar_is_complete` | True |
| `history_years` | 9.08191 |
| `bars` | 19888 |
| `sessions` | 3318 |
| `bars_per_session_median` | 6 |
| `bars_per_session_min` | 1 |
| `bars_per_session_max` | 6 |
| `mode` | core |
| `adjust_pipeline_ran` | True |
| `roll_flagged_bars` | 0 |
| `bad_print_flagged_bars` | 0 |
| `non_tradable_bars` | 1 |
| `return_invalid_bars` | 2 |
| `outage_windows` | 1 |
| `roll_correction_applied` | False |
| `non_tradable_frac` | 5.02816e-05 |
| `non_tradable_reasons` | {'outage_resumption': 1} |

### Uyari (sonuclara yazilmali)

- :warning: 1 zero-range bars (high==low==open==close): 0.01% of data
- :warning: 2 bar with |log return| > 20% on a CONTIGUOUS pair (bad print, roll gap or genuine extreme move). AYRICA incelenmeli, ASLA SILINMEMELI.
- :warning: BTCUSDT SPOT serisi sinyal verisidir. Funding yalnizca maliyet/baglam katmanidir; PERP SINYALI URETILMEZ.

### Tum bulgular

| Check | Seviye | Bulgu | Metrik |
|---|---|---|---|
| schema | INFO | canonical schema OK; optional columns present: ['quote_volume', 'trades', 'taker_buy_volume'] | - |
| timestamp | INFO | no duplicated timestamps | - |
| timestamp | INFO | timestamps strictly increasing | - |
| timestamp | INFO | all bars aligned to the 4h grid anchored at 00:00 (utc mode, tz=UTC). Distinct UTC hours: [0, 4, 8, 12, 16, 20] | - |
| completeness | INFO | bar completeness 99.89% | - |
| completeness | INFO | no gap larger than 50 bars (session-aware threshold, 6.0 bars/session) | - |
| ohlc | INFO | OHLC envelope consistent on every bar | - |
| ohlc | WARN | 1 zero-range bars (high==low==open==close): 0.01% of data | 5.028e-05 |
| continuity | INFO | no bar crosses an UNEXPECTED data gap: her getiri ya bitisik ya da seans takviminin normal bir boslugu (hafta sonu / gece arasi) | - |
| outlier | WARN | 2 bar with \|log return\| > 20% on a CONTIGUOUS pair (bad print, roll gap or genuine extreme move). AYRICA incelenmeli, ASLA SILINMEMELI.  
ornek: 2017-09-15T12:00:00+00:00 r=+0.272; 2020-03-12T20:00:00+00:00 r=-0.229 | 2 |
| outlier | INFO | 286 MAD(8) return outliers kept but flagged for review | 286 |
| volume | INFO | zero-volume bars: 0.01% | - |
| volume | INFO | volume vs bar-range correlation = 0.293 | - |
| optional | INFO | optional columns fully populated: ['quote_volume', 'trades', 'taker_buy_volume'] | - |
| optional | INFO | optional columns present but entirely NaN (dropped from the feature set): ['funding_rate', 'open_interest', 'spread', 'dxy', 'usdtry', 'benchmark'] | - |
| resample | INFO | no source frame supplied: resampling audit skipped | - |
| freshness | INFO | last complete bar 5.9h old | - |
| history | INFO | 19888 bars / 9.08 years of history | - |
| session | INFO | grid anchored 00:00 in mode 'utc' (UTC) | - |
| session | INFO | distinct UTC hours used: [0, 4, 8, 12, 16, 20] | - |
| mandated_caveat | WARN | BTCUSDT SPOT serisi sinyal verisidir. Funding yalnizca maliyet/baglam katmanidir; PERP SINYALI URETILMEZ. | - |
| adjustment | INFO | adjust pipeline calisti (bu varlikta roll TANIM GEREGI imkansiz: 0 roll). 1 bar non-tradable isaretlendi, 2 getiri gecersiz sayildi. | - |

## GOLD (`XAUUSD_PROXY_GC`) - 4h

**Karar: AMBER** | mod: **core** | bar: 3606 | aralik: 2024-04-24T02:00:00+00:00 -> 2026-09-16T06:00:00+00:00

### Metrikler

| Metrik | Deger |
|---|---|
| `grid_anchor_tz` | America/New_York |
| `grid_anchor_local` | 18:00 |
| `distinct_utc_hours` | [2, 3, 6, 7, 10, 11, 14, 15, 18, 19, 22, 23] |
| `expected_bars` | 3756 |
| `missing_bar_fraction` | 0.0399361 |
| `bars_per_session_observed` | 6 |
| `gap_threshold_bars` | 50 |
| `zero_range_bars` | 0 |
| `gap_anomaly_tolerance_bars` | 25 |
| `bars_crossing_data_gap` | 0 |
| `bars_crossing_gap_frac` | 0 |
| `gap_anomaly_rule` | gap > modal_gap(dayofweek, local_hour) + 25 bars (seans bazlı: 24/7 ise 2 seans, değilse 8 seans; tavan 25 bar; bps=6.0) |
| `abs_logret_max_raw_incl_gaps` | 0.0796563 |
| `bars_after_normal_session_gap` | 145 |
| `abs_logret_median` | 0.0026 |
| `abs_logret_p99` | 0.0195417 |
| `abs_logret_max` | 0.0796563 |
| `outlier_return_count` | 16 |
| `outlier_range_count` | 15 |
| `outlier_contiguous_count` | 0 |
| `volume_zero_fraction` | 0.000277316 |
| `volume_total` | 1.11583e+08 |
| `volume_vs_range_corr` | 0.488655 |
| `optional_populated` | [] |
| `optional_partial_nan` | [] |
| `resample_ratio_expected` | 4 |
| `resample_thin_bars` | 46 |
| `resample_thin_fraction` | 0.0127565 |
| `last_bar_age_hours` | 7.94207 |
| `last_bar_is_complete` | True |
| `history_years` | 2.39608 |
| `bars` | 3606 |
| `sessions` | 616 |
| `bars_per_session_median` | 6 |
| `bars_per_session_min` | 1 |
| `bars_per_session_max` | 6 |
| `mode` | core |
| `adjclose_equals_close_frac` | 1 |
| `adjust_pipeline_ran` | True |
| `roll_flagged_bars` | 10 |
| `bad_print_flagged_bars` | 0 |
| `non_tradable_bars` | 31 |
| `return_invalid_bars` | 32 |
| `outage_windows` | 22 |
| `roll_correction_applied` | False |
| `non_tradable_frac` | 0.00859678 |
| `non_tradable_reasons` | {'outage_resumption': 18, 'thin_bar': 9, 'outage_resumption+thin_bar': 4} |

### Uyari (sonuclara yazilmali)

- :warning: 4.0% of expected 4h bars are missing
- :warning: 46 4h bar (1.3%) was built from <75% of the expected 4 source bars (half days / holidays / maintenance halt)
- :warning: GC=F ON-AY vadeli serisidir: roll gap duzeltmesi yapilmadan ham getiri serisi KULLANILAMAZ. Roll tespiti (gap > esik ATR) zorunludur. requires_adjustment=True oldugu icin duzeltme calistirilana kadar QC bu varligi 'model icin uygun DEGIL' olarak isaretler.
- :warning: Intraday gecmis ~2.4 yil ile sinirlidir (Yahoo 1h limiti 730 gun).
- :warning: TESPIT (KARAR 3): 2026-01-30 15:00 UTC -> 2026-02-02 18:00 UTC arasinda 75 saatlik VERI KESINTISI var (normal hafta sonu 80 bar; burada Pazartesi 00:00-15:00 UTC de kayip). 2026-02-02 gunu yalnizca 5 bar gelmis (normal ~23). Kesintiyi atlayan -%7.97'lik getiri NE ROLL NE BAD PRINT'tir: SAHTE bir getiridir. BAR SILINMEZ, 'boslugu atlayan getiri' olarak isaretlenir ve getiri/roll hesaplarinda HARIC TUTULUR.
- :warning: UYARI: 2026-01-26 .. 2026-02-06 penceresinde fiyat 5.626 -> 4.653 arasinda (yaklasik -%17) savruluyor ve gunluk hacim onceki donemin %38'ine dusuyor. Feed kalitesi bu pencerede DUSUK; ayni kesinti SILVER'da da birebir ayni tarihlerde goruluyor (Yahoo kaynakli ortak sorun). Bu doneme dayandirilan sonuclara guvenilmez, egitim/validasyonda ayrica isaretlenmelidir.
- :warning: adjclose, close ile %100.0 oraninda AYNI: bu seri kurumsal aksiyon duzeltmesi ICMERMIYOR (Yahoo intraday davranisi). Temettu/bolunme tespiti bu seriden YAPILAMAZ; GUNLUK serinin adjclose/close orani kullanilmalidir (adjust.corporate_actions_from_daily). Aksi halde bolunmeler SAHTE fiyat sicramasi olarak seriye girer.
- :warning: 10 roll ADAYI yalnizca ISARETLENDI, fiyat DUZELTILMEDI. Sebep: Yahoo on-ay serisinde KONTRAT AYI kimligi yoktur, bu yuzden roll ile gercek ekstrem hareket kesin olarak AYIRT EDILEMEZ. close_adjusted == close_raw. Roll adaylari reports/adjust_evidence.md icinde listelenir ve INSAN INCELEMESI bekler. Kesin cozum: kontrat ayi kimligi olan bir continuous future kaynagi saglamak.

### Tum bulgular

| Check | Seviye | Bulgu | Metrik |
|---|---|---|---|
| schema | INFO | canonical schema OK; optional columns present: ['quote_volume', 'trades', 'taker_buy_volume'] | - |
| timestamp | INFO | no duplicated timestamps | - |
| timestamp | INFO | timestamps strictly increasing | - |
| timestamp | INFO | all bars aligned to the 4h grid anchored at 18:00 (local mode, tz=America/New_York). Distinct UTC hours: [2, 3, 6, 7, 10, 11, 14, 15, 18, 19, 22, 23] | - |
| completeness | WARN | 4.0% of expected 4h bars are missing | 0.03994 |
| completeness | INFO | no gap larger than 50 bars (session-aware threshold, 6.0 bars/session) | - |
| ohlc | INFO | OHLC envelope consistent on every bar | - |
| continuity | INFO | no bar crosses an UNEXPECTED data gap: her getiri ya bitisik ya da seans takviminin normal bir boslugu (hafta sonu / gece arasi) | - |
| outlier | INFO | no contiguous bar with \|log return\| > 20% | - |
| outlier | INFO | 16 MAD(8) return outliers kept but flagged for review | 16 |
| volume | INFO | zero-volume bars: 0.03% | - |
| volume | INFO | volume vs bar-range correlation = 0.489 | - |
| optional | INFO | optional columns present but entirely NaN (dropped from the feature set): ['funding_rate', 'open_interest', 'spread', 'quote_volume', 'trades', 'taker_buy_volume', 'dxy', 'usdtry', 'benchmark'] | - |
| resample | WARN | 46 4h bar (1.3%) was built from <75% of the expected 4 source bars (half days / holidays / maintenance halt) | 46 |
| resample | INFO | resampled OHLC envelope matches the source | - |
| freshness | INFO | last complete bar 7.9h old | - |
| history | INFO | 3606 bars / 2.40 years of history | - |
| session | INFO | 46 bars built from <75% of the expected 4 source bars | - |
| session | INFO | grid anchored 18:00 in mode 'local' (America/New_York) | - |
| session | INFO | distinct UTC hours used: [2, 3, 6, 7, 10, 11, 14, 15, 18, 19, 22, 23] | - |
| mandated_caveat | WARN | GC=F ON-AY vadeli serisidir: roll gap duzeltmesi yapilmadan ham getiri serisi KULLANILAMAZ. Roll tespiti (gap > esik ATR) zorunludur. requires_adjustment=True oldugu icin duzeltme calistirilana kadar QC bu varligi 'model icin uygun DEGIL' olarak isaretler. | - |
| mandated_caveat | WARN | Intraday gecmis ~2.4 yil ile sinirlidir (Yahoo 1h limiti 730 gun). | - |
| mandated_caveat | WARN | TESPIT (KARAR 3): 2026-01-30 15:00 UTC -> 2026-02-02 18:00 UTC arasinda 75 saatlik VERI KESINTISI var (normal hafta sonu 80 bar; burada Pazartesi 00:00-15:00 UTC de kayip). 2026-02-02 gunu yalnizca 5 bar gelmis (normal ~23). Kesintiyi atlayan -%7.97'lik getiri NE ROLL NE BAD PRINT'tir: SAHTE bir getiridir. BAR SILINMEZ, 'boslugu atlayan getiri' olarak isaretlenir ve getiri/roll hesaplarinda HARIC TUTULUR. | - |
| mandated_caveat | WARN | UYARI: 2026-01-26 .. 2026-02-06 penceresinde fiyat 5.626 -> 4.653 arasinda (yaklasik -%17) savruluyor ve gunluk hacim onceki donemin %38'ine dusuyor. Feed kalitesi bu pencerede DUSUK; ayni kesinti SILVER'da da birebir ayni tarihlerde goruluyor (Yahoo kaynakli ortak sorun). Bu doneme dayandirilan sonuclara guvenilmez, egitim/validasyonda ayrica isaretlenmelidir. | - |
| corporate_actions | WARN | adjclose, close ile %100.0 oraninda AYNI: bu seri kurumsal aksiyon duzeltmesi ICMERMIYOR (Yahoo intraday davranisi). Temettu/bolunme tespiti bu seriden YAPILAMAZ; GUNLUK serinin adjclose/close orani kullanilmalidir (adjust.corporate_actions_from_daily). Aksi halde bolunmeler SAHTE fiyat sicramasi olarak seriye girer. | - |
| adjustment | INFO | adjust pipeline CALISTI: 22 kesinti penceresi isaretlendi, 31 bar non-tradable, 32 getiri gecersiz sayildi, 10 roll adayi ISARETLENDI (fiyat duzeltmesi uygulandi=False). Bar SILINMEDI, bar UYDURULMADI. | - |
| adjustment | WARN | 10 roll ADAYI yalnizca ISARETLENDI, fiyat DUZELTILMEDI. Sebep: Yahoo on-ay serisinde KONTRAT AYI kimligi yoktur, bu yuzden roll ile gercek ekstrem hareket kesin olarak AYIRT EDILEMEZ. close_adjusted == close_raw. Roll adaylari reports/adjust_evidence.md icinde listelenir ve INSAN INCELEMESI bekler. Kesin cozum: kontrat ayi kimligi olan bir continuous future kaynagi saglamak. | - |

## SILVER (`XAGUSD_PROXY_SI`) - 4h

**Karar: AMBER** | mod: **core** | bar: 3606 | aralik: 2024-04-24T02:00:00+00:00 -> 2026-09-16T06:00:00+00:00

### Metrikler

| Metrik | Deger |
|---|---|
| `grid_anchor_tz` | America/New_York |
| `grid_anchor_local` | 18:00 |
| `distinct_utc_hours` | [2, 3, 6, 7, 10, 11, 14, 15, 18, 19, 22, 23] |
| `expected_bars` | 3756 |
| `missing_bar_fraction` | 0.0399361 |
| `bars_per_session_observed` | 6 |
| `gap_threshold_bars` | 50 |
| `zero_range_bars` | 0 |
| `gap_anomaly_tolerance_bars` | 25 |
| `bars_crossing_data_gap` | 0 |
| `bars_crossing_gap_frac` | 0 |
| `gap_anomaly_rule` | gap > modal_gap(dayofweek, local_hour) + 25 bars (seans bazlı: 24/7 ise 2 seans, değilse 8 seans; tavan 25 bar; bps=6.0) |
| `abs_logret_max_raw_incl_gaps` | 0.222192 |
| `bars_after_normal_session_gap` | 145 |
| `abs_logret_median` | 0.00455506 |
| `abs_logret_p99` | 0.0402822 |
| `abs_logret_max` | 0.222192 |
| `outlier_return_count` | 34 |
| `outlier_range_count` | 25 |
| `outlier_contiguous_count` | 1 |
| `volume_zero_fraction` | 0.000277316 |
| `volume_total` | 4.01586e+07 |
| `volume_vs_range_corr` | 0.477413 |
| `optional_populated` | [] |
| `optional_partial_nan` | [] |
| `resample_ratio_expected` | 4 |
| `resample_thin_bars` | 47 |
| `resample_thin_fraction` | 0.0130338 |
| `last_bar_age_hours` | 7.94214 |
| `last_bar_is_complete` | True |
| `history_years` | 2.39608 |
| `bars` | 3606 |
| `sessions` | 616 |
| `bars_per_session_median` | 6 |
| `bars_per_session_min` | 1 |
| `bars_per_session_max` | 6 |
| `mode` | core |
| `adjclose_equals_close_frac` | 1 |
| `adjust_pipeline_ran` | True |
| `roll_flagged_bars` | 6 |
| `bad_print_flagged_bars` | 0 |
| `non_tradable_bars` | 31 |
| `return_invalid_bars` | 32 |
| `outage_windows` | 22 |
| `roll_correction_applied` | False |
| `non_tradable_frac` | 0.00859678 |
| `non_tradable_reasons` | {'outage_resumption': 18, 'thin_bar': 9, 'outage_resumption+thin_bar': 4} |

### Uyari (sonuclara yazilmali)

- :warning: 4.0% of expected 4h bars are missing
- :warning: 1 bar with |log return| > 20% on a CONTIGUOUS pair (bad print, roll gap or genuine extreme move). AYRICA incelenmeli, ASLA SILINMEMELI.
- :warning: 47 4h bar (1.3%) was built from <75% of the expected 4 source bars (half days / holidays / maintenance halt)
- :warning: SI=F ON-AY vadeli serisidir: roll gap duzeltmesi zorunludur. requires_adjustment=True oldugu icin duzeltme calistirilana kadar QC bu varligi 'model icin uygun DEGIL' olarak isaretler.
- :warning: Intraday gecmis ~2.4 yil ile sinirlidir (Yahoo 1h limiti 730 gun).
- :warning: TESPIT (KARAR 3): 2026-02-02'deki tek barlik -%22 hareket incelendi. SONUC: bu NE ROLL NE BAD PRINT'tir. 2026-01-30 15:00 UTC -> 2026-02-02 18:00 UTC arasinda 75 saatlik VERI KESINTISI var (normal hafta sonu 80 bar; burada Pazartesi 00:00-15:00 UTC de kayip) ve 2026-02-02 gunu yalnizca 5 bar gelmis (normal ~23). Dolayisiyla -%22, veri boslugunu atlayan SAHTE bir getiridir. BAR SILINMEZ; 'boslugu atlayan getiri' olarak isaretlenir ve getiri/roll/label hesaplarinda HARIC TUTULUR.
- :warning: UYARI: 2026-01-26 .. 2026-02-06 penceresinde fiyat 121.79 -> 66.88 arasinda (yaklasik -%45) savruluyor ve gunluk hacim onceki donemin %42'sine dusuyor. Ayni kesinti GOLD'da da birebir ayni tarihlerde var (Yahoo kaynakli ortak sorun). Bu pencerede feed kalitesi COK DUSUK; model egitimi/validasyonunda ayrica isaretlenmeli, sonuclar bu doneme dayandirilmamali.
- :warning: adjclose, close ile %100.0 oraninda AYNI: bu seri kurumsal aksiyon duzeltmesi ICMERMIYOR (Yahoo intraday davranisi). Temettu/bolunme tespiti bu seriden YAPILAMAZ; GUNLUK serinin adjclose/close orani kullanilmalidir (adjust.corporate_actions_from_daily). Aksi halde bolunmeler SAHTE fiyat sicramasi olarak seriye girer.
- :warning: 6 roll ADAYI yalnizca ISARETLENDI, fiyat DUZELTILMEDI. Sebep: Yahoo on-ay serisinde KONTRAT AYI kimligi yoktur, bu yuzden roll ile gercek ekstrem hareket kesin olarak AYIRT EDILEMEZ. close_adjusted == close_raw. Roll adaylari reports/adjust_evidence.md icinde listelenir ve INSAN INCELEMESI bekler. Kesin cozum: kontrat ayi kimligi olan bir continuous future kaynagi saglamak.

### Tum bulgular

| Check | Seviye | Bulgu | Metrik |
|---|---|---|---|
| schema | INFO | canonical schema OK; optional columns present: ['quote_volume', 'trades', 'taker_buy_volume'] | - |
| timestamp | INFO | no duplicated timestamps | - |
| timestamp | INFO | timestamps strictly increasing | - |
| timestamp | INFO | all bars aligned to the 4h grid anchored at 18:00 (local mode, tz=America/New_York). Distinct UTC hours: [2, 3, 6, 7, 10, 11, 14, 15, 18, 19, 22, 23] | - |
| completeness | WARN | 4.0% of expected 4h bars are missing | 0.03994 |
| completeness | INFO | no gap larger than 50 bars (session-aware threshold, 6.0 bars/session) | - |
| ohlc | INFO | OHLC envelope consistent on every bar | - |
| continuity | INFO | no bar crosses an UNEXPECTED data gap: her getiri ya bitisik ya da seans takviminin normal bir boslugu (hafta sonu / gece arasi) | - |
| outlier | WARN | 1 bar with \|log return\| > 20% on a CONTIGUOUS pair (bad print, roll gap or genuine extreme move). AYRICA incelenmeli, ASLA SILINMEMELI.  
ornek: 2026-02-02T15:00:00+00:00 r=-0.222 | 1 |
| outlier | INFO | 34 MAD(8) return outliers kept but flagged for review | 34 |
| volume | INFO | zero-volume bars: 0.03% | - |
| volume | INFO | volume vs bar-range correlation = 0.477 | - |
| optional | INFO | optional columns present but entirely NaN (dropped from the feature set): ['funding_rate', 'open_interest', 'spread', 'quote_volume', 'trades', 'taker_buy_volume', 'dxy', 'usdtry', 'benchmark'] | - |
| resample | WARN | 47 4h bar (1.3%) was built from <75% of the expected 4 source bars (half days / holidays / maintenance halt) | 47 |
| resample | INFO | resampled OHLC envelope matches the source | - |
| freshness | INFO | last complete bar 7.9h old | - |
| history | INFO | 3606 bars / 2.40 years of history | - |
| session | INFO | 47 bars built from <75% of the expected 4 source bars | - |
| session | INFO | grid anchored 18:00 in mode 'local' (America/New_York) | - |
| session | INFO | distinct UTC hours used: [2, 3, 6, 7, 10, 11, 14, 15, 18, 19, 22, 23] | - |
| mandated_caveat | WARN | SI=F ON-AY vadeli serisidir: roll gap duzeltmesi zorunludur. requires_adjustment=True oldugu icin duzeltme calistirilana kadar QC bu varligi 'model icin uygun DEGIL' olarak isaretler. | - |
| mandated_caveat | WARN | Intraday gecmis ~2.4 yil ile sinirlidir (Yahoo 1h limiti 730 gun). | - |
| mandated_caveat | WARN | TESPIT (KARAR 3): 2026-02-02'deki tek barlik -%22 hareket incelendi. SONUC: bu NE ROLL NE BAD PRINT'tir. 2026-01-30 15:00 UTC -> 2026-02-02 18:00 UTC arasinda 75 saatlik VERI KESINTISI var (normal hafta sonu 80 bar; burada Pazartesi 00:00-15:00 UTC de kayip) ve 2026-02-02 gunu yalnizca 5 bar gelmis (normal ~23). Dolayisiyla -%22, veri boslugunu atlayan SAHTE bir getiridir. BAR SILINMEZ; 'boslugu atlayan getiri' olarak isaretlenir ve getiri/roll/label hesaplarinda HARIC TUTULUR. | - |
| mandated_caveat | WARN | UYARI: 2026-01-26 .. 2026-02-06 penceresinde fiyat 121.79 -> 66.88 arasinda (yaklasik -%45) savruluyor ve gunluk hacim onceki donemin %42'sine dusuyor. Ayni kesinti GOLD'da da birebir ayni tarihlerde var (Yahoo kaynakli ortak sorun). Bu pencerede feed kalitesi COK DUSUK; model egitimi/validasyonunda ayrica isaretlenmeli, sonuclar bu doneme dayandirilmamali. | - |
| corporate_actions | WARN | adjclose, close ile %100.0 oraninda AYNI: bu seri kurumsal aksiyon duzeltmesi ICMERMIYOR (Yahoo intraday davranisi). Temettu/bolunme tespiti bu seriden YAPILAMAZ; GUNLUK serinin adjclose/close orani kullanilmalidir (adjust.corporate_actions_from_daily). Aksi halde bolunmeler SAHTE fiyat sicramasi olarak seriye girer. | - |
| adjustment | INFO | adjust pipeline CALISTI: 22 kesinti penceresi isaretlendi, 31 bar non-tradable, 32 getiri gecersiz sayildi, 6 roll adayi ISARETLENDI (fiyat duzeltmesi uygulandi=False). Bar SILINMEDI, bar UYDURULMADI. | - |
| adjustment | WARN | 6 roll ADAYI yalnizca ISARETLENDI, fiyat DUZELTILMEDI. Sebep: Yahoo on-ay serisinde KONTRAT AYI kimligi yoktur, bu yuzden roll ile gercek ekstrem hareket kesin olarak AYIRT EDILEMEZ. close_adjusted == close_raw. Roll adaylari reports/adjust_evidence.md icinde listelenir ve INSAN INCELEMESI bekler. Kesin cozum: kontrat ayi kimligi olan bir continuous future kaynagi saglamak. | - |

## BIST30 (`XU030_INDEX`) - 4h

**Karar: AMBER (insufficient history)** | mod: **watch_only** | bar: 1435 | aralik: 2023-10-27T07:00:00+00:00 -> 2026-09-15T11:00:00+00:00

### Metrikler

| Metrik | Deger |
|---|---|
| `grid_anchor_tz` | Europe/Istanbul |
| `grid_anchor_local` | 10:00 |
| `distinct_utc_hours` | [7, 11] |
| `expected_bars` | 1506 |
| `missing_bar_fraction` | 0.0471448 |
| `bars_per_session_observed` | 2 |
| `gap_threshold_bars` | 18 |
| `zero_range_bars` | 0 |
| `gap_anomaly_tolerance_bars` | 17 |
| `bars_crossing_data_gap` | 9 |
| `bars_crossing_gap_frac` | 0.00627178 |
| `gap_anomaly_rule` | gap > modal_gap(dayofweek, local_hour) + 17 bars (seans bazlı: 24/7 ise 2 seans, değilse 8 seans; tavan 25 bar; bps=2.0) |
| `abs_logret_max_raw_incl_gaps` | 0.0777343 |
| `bars_after_normal_session_gap` | 711 |
| `abs_logret_median` | 0.0054099 |
| `abs_logret_p99` | 0.0403934 |
| `abs_logret_max` | 0.0777343 |
| `outlier_return_count` | 8 |
| `outlier_range_count` | 7 |
| `outlier_contiguous_count` | 0 |
| `volume_zero_fraction` | 1 |
| `volume_total` | 0 |
| `volume_vs_range_corr` | nan |
| `optional_populated` | [] |
| `optional_partial_nan` | [] |
| `resample_ratio_expected` | 4 |
| `resample_thin_bars` | 0 |
| `resample_thin_fraction` | 0 |
| `last_bar_age_hours` | 26.9422 |
| `last_bar_is_complete` | True |
| `history_years` | 2.88615 |
| `bars` | 1435 |
| `sessions` | 721 |
| `bars_per_session_median` | 2 |
| `bars_per_session_min` | 1 |
| `bars_per_session_max` | 2 |
| `mode` | watch_only |
| `adjclose_equals_close_frac` | 1 |
| `adjust_pipeline_ran` | True |
| `roll_flagged_bars` | 0 |
| `bad_print_flagged_bars` | 0 |
| `non_tradable_bars` | 25 |
| `return_invalid_bars` | 26 |
| `outage_windows` | 25 |
| `roll_correction_applied` | False |
| `non_tradable_frac` | 0.0174216 |
| `non_tradable_reasons` | {'outage_resumption': 25} |

### Uyari (sonuclara yazilmali)

- :warning: 4.7% of expected 4h bars are missing
- :warning: 12 gaps larger than 18 bars (max 36 bars) - holidays/outages need review
- :warning: 9 bar (0.627%) BEKLENMEDIK bir veri boslugunu atliyor (kural: gap > modal_gap(dayofweek, local_hour) + 17 bars (seans bazlı: 24/7 ise 2 seans, değilse 8 seans; tavan 25 bar; bps=2.0)). Bu barlarin getirisi GERCEK GETIRI DEGILDIR: roll-gap/outlier tespiti, label uretimi ve backtest P/L hesabinda HARIC TUTULMALIDIR. Barlar SILINMEZ, isaretlenir. En buyuk sahte getiriler:
- :warning: KULLANICI KARARI: bu varlikta hacim verisi yoktur ve hacim/onay bacagi DEVRE DISIDIR (volume_required=False). Cift onay yalnizca trend + momentum ile sinirlidir; bu kisit tum raporlarda caveat olarak tasinar.
- :warning: volume is zero on every bar (beklenen durum: endeks serisi, hacim bacagi zaten devre disi)
- :warning: only 1435 4h bars (2.89 years). Minimum for a trustworthy walk-forward study is 1500. Results on this asset will be statistically weak.
- :warning: BIST30 dogrudan trade edilemez: XU030.IS endeksin kendisidir. Execution VIOp XU030 vadeli maliyet modeliyle VARSAYIMSAL olarak modellenir.
- :warning: Hacim verisi YOKTUR (her bar 0). Hacim/onay bacagi bu varlikta KULLANILMAZ; cift onay burada trend + momentum ile sinirlidir.
- :warning: Gecmis sadece ~2.9 yil. 4H bar sayisi ~2.157 gorunur ama bunun ~721 adedi yalnizca 09:30 ACILIS ANI printini iceren INCE barlardir; TAM 4H bar sayisi ~1.436'ddir. BTC'nin 19.888 bariyla karsilastirildiginda istatistiksel guc COK DUSUKTUR; sonuclar yalnizca yon gosterir, kesinlik iddia edilemez.
- :warning: Alternatif VIOp XU030 futures gecmisi bulunamadigi surece BIST30 backtest portfoyune ZORLA SOKULMAZ, izleme modunda kalir.
- :warning: 4H grid faz farki: BIST30 barlari 07/11 UTC'de, BTC barlari 00/04/08 UTC'de acilir. Bu yuzden varliklar arasi korelasyon YALNIZCA GUNLUK bazda hesaplanir; 4H seviyesinde ortak bar yoktur (n=0).
- :warning: KULLANICI KARARI: bu varlik 'watch_only' modundadir. Sinyal uretilir ve raporlanir ama backtest/PORTFOY performansina ZORLA SOKULMAZ. Cekirdek portfoy: BTC + GOLD + SILVER.
- :warning: adjclose, close ile %100.0 oraninda AYNI: bu seri kurumsal aksiyon duzeltmesi ICMERMIYOR (Yahoo intraday davranisi). Temettu/bolunme tespiti bu seriden YAPILAMAZ; GUNLUK serinin adjclose/close orani kullanilmalidir (adjust.corporate_actions_from_daily). Aksi halde bolunmeler SAHTE fiyat sicramasi olarak seriye girer.

### Tum bulgular

| Check | Seviye | Bulgu | Metrik |
|---|---|---|---|
| schema | INFO | canonical schema OK; optional columns present: ['quote_volume', 'trades', 'taker_buy_volume'] | - |
| timestamp | INFO | no duplicated timestamps | - |
| timestamp | INFO | timestamps strictly increasing | - |
| timestamp | INFO | all bars aligned to the 4h grid anchored at 10:00 (local mode, tz=Europe/Istanbul). Distinct UTC hours: [7, 11] | - |
| completeness | WARN | 4.7% of expected 4h bars are missing | 0.04714 |
| completeness | WARN | 12 gaps larger than 18 bars (max 36 bars) - holidays/outages need review  
ornek: 2024-01-02T07:00:00+00:00 (+1 bars); 2024-04-15T07:00:00+00:00 (+1 bars); 2024-06-20T07:00:00+00:00 (+1 bars); 2024-07-16T07:00:00+00:00 (+1 bars); 2024-09-02T07:00:00+00:00 (+1 bars) | 12 |
| ohlc | INFO | OHLC envelope consistent on every bar | - |
| continuity | WARN | 9 bar (0.627%) BEKLENMEDIK bir veri boslugunu atliyor (kural: gap > modal_gap(dayofweek, local_hour) + 17 bars (seans bazlı: 24/7 ise 2 seans, değilse 8 seans; tavan 25 bar; bps=2.0)). Bu barlarin getirisi GERCEK GETIRI DEGILDIR: roll-gap/outlier tespiti, label uretimi ve backtest P/L hesabinda HARIC TUTULMALIDIR. Barlar SILINMEZ, isaretlenir. En buyuk sahte getiriler:  
ornek: 2024-06-20T07:00:00+00:00 r=+1.977% (bosluk 35 bar, tipik 5); 2025-06-10T07:00:00+00:00 r=+1.529% (bosluk 30 bar, tipik 5); 2025-05-20T07:00:00+00:00 r=-1.046% (bosluk 23 bar, tipik 5); 2026-06-01T07:00:00+00:00 r=+1.034% (bosluk 36 bar, tipik 17); 2025-04-02T07:00:00+00:00 r=-0.970% (bosluk 29 bar, tipik 5) | 9 |
| outlier | INFO | no contiguous bar with \|log return\| > 20% | - |
| outlier | INFO | 8 MAD(8) return outliers kept but flagged for review | 8 |
| volume | WARN | KULLANICI KARARI: bu varlikta hacim verisi yoktur ve hacim/onay bacagi DEVRE DISIDIR (volume_required=False). Cift onay yalnizca trend + momentum ile sinirlidir; bu kisit tum raporlarda caveat olarak tasinar. | - |
| volume | WARN | volume is zero on every bar (beklenen durum: endeks serisi, hacim bacagi zaten devre disi) | 1 |
| optional | INFO | optional columns present but entirely NaN (dropped from the feature set): ['funding_rate', 'open_interest', 'spread', 'quote_volume', 'trades', 'taker_buy_volume', 'dxy', 'usdtry', 'benchmark'] | - |
| resample | INFO | every 4h bar has the expected number of source bars (~4) | - |
| freshness | INFO | last complete bar 26.9h old | - |
| history | WARN | only 1435 4h bars (2.89 years). Minimum for a trustworthy walk-forward study is 1500. Results on this asset will be statistically weak. | 1435 |
| session | INFO | 0 bars built from <75% of the expected 4 source bars | - |
| session | INFO | grid anchored 10:00 in mode 'local' (Europe/Istanbul) | - |
| session | INFO | distinct UTC hours used: [7, 11] | - |
| mandated_caveat | WARN | BIST30 dogrudan trade edilemez: XU030.IS endeksin kendisidir. Execution VIOp XU030 vadeli maliyet modeliyle VARSAYIMSAL olarak modellenir. | - |
| mandated_caveat | WARN | Hacim verisi YOKTUR (her bar 0). Hacim/onay bacagi bu varlikta KULLANILMAZ; cift onay burada trend + momentum ile sinirlidir. | - |
| mandated_caveat | WARN | Gecmis sadece ~2.9 yil. 4H bar sayisi ~2.157 gorunur ama bunun ~721 adedi yalnizca 09:30 ACILIS ANI printini iceren INCE barlardir; TAM 4H bar sayisi ~1.436'ddir. BTC'nin 19.888 bariyla karsilastirildiginda istatistiksel guc COK DUSUKTUR; sonuclar yalnizca yon gosterir, kesinlik iddia edilemez. | - |
| mandated_caveat | WARN | Alternatif VIOp XU030 futures gecmisi bulunamadigi surece BIST30 backtest portfoyune ZORLA SOKULMAZ, izleme modunda kalir. | - |
| mandated_caveat | WARN | 4H grid faz farki: BIST30 barlari 07/11 UTC'de, BTC barlari 00/04/08 UTC'de acilir. Bu yuzden varliklar arasi korelasyon YALNIZCA GUNLUK bazda hesaplanir; 4H seviyesinde ortak bar yoktur (n=0). | - |
| portfolio | WARN | KULLANICI KARARI: bu varlik 'watch_only' modundadir. Sinyal uretilir ve raporlanir ama backtest/PORTFOY performansina ZORLA SOKULMAZ. Cekirdek portfoy: BTC + GOLD + SILVER. | - |
| corporate_actions | WARN | adjclose, close ile %100.0 oraninda AYNI: bu seri kurumsal aksiyon duzeltmesi ICMERMIYOR (Yahoo intraday davranisi). Temettu/bolunme tespiti bu seriden YAPILAMAZ; GUNLUK serinin adjclose/close orani kullanilmalidir (adjust.corporate_actions_from_daily). Aksi halde bolunmeler SAHTE fiyat sicramasi olarak seriye girer. | - |
| adjustment | INFO | adjust pipeline calisti (bu varlikta roll TANIM GEREGI imkansiz: 0 roll). 25 bar non-tradable isaretlendi, 26 getiri gecersiz sayildi. | - |

## Portfoy duzeyi kontroller

- Ortak pencere: **2024-04-24T02:00 -> 2026-09-15T11:00 UTC**
- Ortak pencerede bar sayilari: {'BTC': 5245, 'GOLD': 3600, 'SILVER': 3600, 'BIST30': 1189}
- Ortak pencere yeterli mi (>=500 bar): **True**
- En yuksek |korelasyon| (4H, ortak saatler): {'pair': 'GOLD|SILVER', 'corr': 0.7807, 'abs': 0.7807}

### 4H log-getiri korelasyonu (pairwise-complete, sadece ortak saatler)

| Cift | korelasyon | n (ortak bar) |
|---|---|---:|
| BIST30|BTC | None | 0 |
| BIST30|GOLD | 0.0705 | 334 |
| BIST30|SILVER | 0.1039 | 334 |
| BTC|GOLD | None | 0 |
| BTC|SILVER | None | 0 |
| GOLD|SILVER | 0.7807 | 3600 |

*Not: BTC 24/7, metaller ~23h NY, BIST 6.5h Istanbul islem gordugu icin ortak bar sayilari farklidir. Korelasyon limitleri asagidaki GUNLUK korelasyona gore uygulanmalidir; 4H degeri sadece intraday es-zamanlilik bilgisi verir.*

### Gunluk log-getiri korelasyonu (ortak gun sayisi: 874)

| Cift | korelasyon |
|---|---|
| BIST30|BTC | 0.0847 |
| BIST30|GOLD | 0.0427 |
| BIST30|SILVER | 0.0815 |
| BTC|GOLD | 0.1796 |
| BTC|SILVER | 0.2651 |
| GOLD|SILVER | 0.7682 |

- Ortak gun sayilari: {'BTC': 874, 'GOLD': 603, 'SILVER': 603, 'BIST30': 461}

*Korelasyon limitleri GUNLUK korelasyona gore uygulanir. 4H degeri sadece intraday es-zamanlilik bilgisidir; grid faz farki olan ciftlerde (orn. BIST30 03/07/11 UTC vs BTC 00/04/08 UTC) 4H ortus bar sayisi 0 olabilir.*

- :warning: |korelasyon| > 0.70 olan ciftler (risk limiti devreye girer): ['GOLD|SILVER = +0.781 (n=3600)', 'GOLD|SILVER = +0.768']
