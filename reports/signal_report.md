# AŞAMA 5 — Giriş Tetiği ve Sinyal Montajı Raporu

*Üretim: 2026-09-16T14:41:27 UTC* · timeframe **4h** · cooldown **3 bar (12 saat)**

## 1) TETİK — yeni indikatör YOK

```
LONG: close > max(high[t-20..t-1]); SHORT (yalnız core): close < min(low[t-20..t-1])
```

> donchian_high ZATEN shift(1) içerir; bu yüzden tetikte İKİNCİ bir shift YOKTUR (olsaydı pencere 21 bara çıkardı). Eşdeğerlik test_trigger_equals_manual_20_bar_breakout ile kilitli.

## 2) SİNYAL ZİNCİRİ

```
long  = long_regime_ok ∧ longs_allowed ∧ ~non_tradable ∧ return_valid ∧ momentum_ok ∧ trigger_long ∧ stop_valid_long
short = short_regime_ok ∧ ~non_tradable ∧ return_valid ∧ momentum_short_ok ∧ trigger_short ∧ stop_valid_short    (yalnız CORE)
```

> **stop_valid — fail-closed EK halka (dondurulmuş stop yoksa işlem yok). Şartname listesinde açıkça yoktu; require_valid_stop=False ile kapatılabilir.**
> Bir kapı kolonu frame'de YOKSA sonuç **False**'tur (fail-closed), sessizce 'geçti' sayılmaz.

## 3) İCRA ZAMANI — KRİTİK

> sinyal bar t KAPANIŞINDA; giriş bar t+1 AÇILIŞINDA. signal_bar_close P&L'de KULLANILMAZ. t+1 yoksa execution_valid=False.

## 4) COOLDOWN ve POZİSYON BASKILAMASI

- **Cooldown sözleşmesi:** sinyal barı s ise ilk yeniden sinyal (s+1)+cooldown_bars = s+4 (12 saat). test_cooldown_off_by_one_is_exactly_as_documented.
- **Pozisyon açıkken yeni sinyal YOK.** Pozisyon vekili: `frozen_stop_intrabar (VEKİL — Aşama 6/7'de gerçek motor)` — VEKİL — Aşama 6/7'de gerçek motor)

### ⚠️ ANA BULGU: pozisyon vekili sinyalleri AÇLIKTAN ÖLDÜRÜYOR

Yapısal stop girişten ~2,6–3,2 ATR geride olduğu için fiyat onu **yıllarca** ihlal etmeyebiliyor. Vekil çıkış yalnızca stop ihlali olduğu için pozisyon neredeyse hep açık kalıyor ve ham sinyallerin büyük bölümü bastırılıyor (BTC: 592 ham → 3 final, pozisyon açıklık oranı %96).

**Bu bir kod hatası DEĞİL.** Aşama 3'ün dürüst yorumunda öngörülen "yapısal stop geniş" sonucunun doğrudan ölçümüdür ve **Aşama 7'nin (partial + runner, trailing, time-stop) neden zorunlu olduğunu kanıtlar**. Aşama 6/7'de gerçek çıkış motoru geldiğinde bu tablo yeniden üretilecektir. Bu yüzden rapor ÜÇ akışı birlikte verir:

| Akış | Tanım | Ne için |
|---|---|---|
| **A) strict** | şartnamedeki kural: pozisyon açıkken sinyal yok + cooldown | asıl kural; sonuç GEÇİCİ (vekile bağlı) |
| **B) capped** | A + zorunlu time-stop (90 bar) | vekilin ne kadar bağlayıcı olduğunu gösterir |
| **C) cooldown_only** | pozisyon takibi yok, yalnız cooldown | **cooldown kuralının kendi etkisini** izole eder |

## 5) VARLIK BAŞINA SİNYAL SAYILARI

| Varlık | rol | bar | ham long | **A strict** long | A short | A poz açık % | A bastırılan(poz) | **B capped** long | **C cooldown** long | C bastırılan(cooldown) | C min aralık (bar) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **BTC** | core_tradable | 19888 | 592 | **3** | 3 | %96.4 | 920 | **100** | **366** | 335 | 4 |
| **GOLD** | core_tradable | 3606 | 212 | **1** | 0 | %85.8 | 258 | **23** | **109** | 123 | 4 |
| **SILVER** | core_tradable | 3606 | 138 | **3** | 0 | %82.6 | 171 | **26** | **79** | 70 | 4 |
| **BIST30** | context_filter_source | 1435 | 70 | **2** | 3 | %55.0 | 73 | **9** | **38** | 35 | 4 |
| **AEFES** | stock | 1436 | 26 | **2** | 0 | %28.3 | 24 | **4** | **14** | 12 | 4 |
| **AKBNK** | stock | 1436 | 30 | **3** | 0 | %47.4 | 27 | **8** | **21** | 9 | 4 |
| **ASELS** | stock | 1436 | 75 | **1** | 0 | %59.9 | 74 | **8** | **39** | 36 | 4 |
| **ASTOR** | stock | 1436 | 47 | **3** | 0 | %49.4 | 44 | **7** | **29** | 18 | 4 |
| **BIMAS** | stock | 1436 | 43 | **2** | 0 | %49.4 | 41 | **8** | **33** | 10 | 4 |
| **EKGYO** | stock | 1436 | 44 | **2** | 0 | %55.2 | 42 | **8** | **24** | 20 | 4 |
| **ENKAI** | stock | 1436 | 23 | **2** | 0 | %56.4 | 21 | **7** | **15** | 8 | 5 |
| **EREGL** | stock | 1436 | 42 | **2** | 0 | %49.9 | 40 | **9** | **24** | 18 | 4 |
| **FROTO** | stock | 1436 | 27 | **2** | 0 | %34.5 | 25 | **3** | **14** | 13 | 4 |
| **GARAN** | stock | 1436 | 22 | **3** | 0 | %31.6 | 19 | **5** | **17** | 5 | 5 |
| **GUBRF** | stock | 1436 | 49 | **1** | 0 | %62.1 | 48 | **7** | **29** | 20 | 4 |
| **ISCTR** | stock | 1435 | 29 | **4** | 0 | %40.9 | 25 | **6** | **18** | 11 | 4 |
| **KCHOL** | stock | 1436 | 35 | **2** | 0 | %36.9 | 33 | **6** | **20** | 15 | 4 |
| **KRDMD** | stock | 1436 | 50 | **3** | 0 | %45.7 | 47 | **7** | **30** | 20 | 4 |
| **MGROS** | stock | 1436 | 44 | **3** | 0 | %40.5 | 41 | **6** | **26** | 18 | 4 |
| **PETKM** | stock | 1436 | 27 | **2** | 0 | %32.5 | 25 | **4** | **13** | 14 | 4 |
| **PGSUS** | stock | 1436 | 14 | **4** | 0 | %11.8 | 10 | **4** | **8** | 6 | 4 |
| **SAHOL** | stock | 1436 | 27 | **3** | 0 | %36.8 | 24 | **6** | **17** | 10 | 4 |
| **SASA** | stock | 1436 | 4 | **3** | 0 | %10.7 | 1 | **3** | **3** | 1 | 173 |
| **SISE** | stock | 1435 | 15 | **3** | 0 | %33.9 | 12 | **6** | **13** | 2 | 10 |
| **TAVHL** | stock | 1436 | 33 | **3** | 0 | %39.6 | 30 | **5** | **21** | 12 | 4 |
| **TCELL** | stock | 1436 | 33 | **4** | 0 | %36.1 | 29 | **7** | **20** | 13 | 4 |
| **THYAO** | stock | 1436 | 33 | **5** | 0 | %32.6 | 28 | **7** | **18** | 15 | 4 |
| **TOASO** | stock | 1436 | 42 | **3** | 0 | %41.9 | 39 | **7** | **20** | 22 | 4 |
| **TTKOM** | stock | 1436 | 29 | **3** | 0 | %33.2 | 26 | **5** | **15** | 14 | 4 |
| **TUPRS** | stock | 1436 | 47 | **1** | 0 | %41.0 | 46 | **5** | **25** | 22 | 4 |
| **VAKBN** | stock | 1436 | 33 | **3** | 0 | %45.7 | 30 | **6** | **20** | 13 | 4 |
| **YKBNK** | stock | 1436 | 37 | **2** | 0 | %53.1 | 35 | **8** | **22** | 15 | 4 |

## 6) YILLARA GÖRE DAĞILIM ve ORTALAMA SİNYALLER ARASI SÜRE

Kabul kriteri 5. `strict` akışı vekile bağımlı olduğu için **capped** ve **cooldown_only** akışlarının dağılımı da verilir.

### Akış STRICT — LONG

| Varlık | 2017 | 2019 | 2020 | 2024 | 2025 | 2026 | TOPLAM | ort. aralık (gün) | medyan (gün) | min (gün) | sinyal/yıl |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **BTC** | 1 | 1 | 1 |  |  |  | 3 | 447.0 | 447.0 | 359.0 | 1.2 |
| **GOLD** |  |  |  | 1 |  |  | 1 | — | — | — | — |
| **SILVER** |  |  |  | 2 | 1 |  | 3 | 120.17 | 120.17 | 17.67 | 4.6 |
| **BIST30** |  |  |  | 1 | 1 |  | 2 | 211.0 | 211.0 | 211.0 | 3.5 |
| **AEFES** |  |  |  | 1 | 1 |  | 2 | 374.0 | 374.0 | 374.0 | 2.0 |
| **AKBNK** |  |  |  | 1 | 2 |  | 3 | 181.5 | 181.5 | 153.0 | 3.0 |
| **ASELS** |  |  |  | 1 |  |  | 1 | — | — | — | — |
| **ASTOR** |  |  |  | 1 | 2 |  | 3 | 192.0 | 192.0 | 126.0 | 2.9 |
| **BIMAS** |  |  |  | 1 | 1 |  | 2 | 225.17 | 225.17 | 225.17 | 3.2 |
| **EKGYO** |  |  |  | 1 | 1 |  | 2 | 193.17 | 193.17 | 193.17 | 3.8 |
| **ENKAI** |  |  |  | 1 | 1 |  | 2 | 71.17 | 71.17 | 71.17 | 10.3 |
| **EREGL** |  |  |  | 1 | 1 |  | 2 | 162.17 | 162.17 | 162.17 | 4.5 |
| **FROTO** |  |  |  |  | 2 |  | 2 | 120.0 | 120.0 | 120.0 | 6.1 |
| **GARAN** |  |  |  | 1 | 2 |  | 3 | 185.5 | 185.5 | 153.0 | 3.0 |
| **GUBRF** |  |  |  | 1 |  |  | 1 | — | — | — | — |
| **ISCTR** |  |  |  | 1 | 3 |  | 4 | 123.33 | 151.83 | 30.17 | 3.9 |
| **KCHOL** |  |  |  |  | 2 |  | 2 | 143.17 | 143.17 | 143.17 | 5.1 |
| **KRDMD** |  |  |  | 1 | 1 | 1 | 3 | 207.5 | 207.5 | 177.0 | 2.6 |
| **MGROS** |  |  |  | 1 | 2 |  | 3 | 187.0 | 187.0 | 140.83 | 2.9 |
| **PETKM** |  |  |  |  | 1 | 1 | 2 | 190.0 | 190.0 | 190.0 | 3.8 |
| **PGSUS** |  |  |  |  | 4 |  | 4 | 58.72 | 29.83 | 29.17 | 8.3 |
| **SAHOL** |  |  |  | 1 | 1 | 1 | 3 | 197.92 | 197.92 | 155.0 | 2.8 |
| **SASA** |  |  |  |  | 1 | 2 | 3 | 196.0 | 196.0 | 130.0 | 2.8 |
| **SISE** |  |  |  | 1 | 2 |  | 3 | 175.5 | 175.5 | 125.0 | 3.1 |
| **TAVHL** |  |  |  | 1 | 2 |  | 3 | 171.5 | 171.5 | 74.83 | 3.2 |
| **TCELL** |  |  |  |  | 4 |  | 4 | 113.67 | 69.0 | 42.0 | 4.3 |
| **THYAO** |  |  |  | 1 | 1 | 3 | 5 | 142.5 | 125.42 | 77.0 | 3.2 |
| **TOASO** |  |  |  |  | 3 |  | 3 | 85.5 | 85.5 | 72.0 | 6.4 |
| **TTKOM** |  |  |  |  | 3 |  | 3 | 154.5 | 154.5 | 153.17 | 3.5 |
| **TUPRS** |  |  |  |  | 1 |  | 1 | — | — | — | — |
| **VAKBN** |  |  |  | 1 | 2 |  | 3 | 168.0 | 168.0 | 148.83 | 3.3 |
| **YKBNK** |  |  |  | 1 | 1 |  | 2 | 216.83 | 216.83 | 216.83 | 3.4 |

### Akış CAPPED — LONG

| Varlık | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | TOPLAM | ort. aralık (gün) | medyan (gün) | min (gün) | sinyal/yıl |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **BTC** | 3 | 6 | 10 | 17 | 13 | 6 | 13 | 14 | 11 | 7 | 100 | 32.47 | 20.17 | 2.17 | 11.4 |
| **GOLD** |  |  |  |  |  |  |  | 4 | 13 | 6 | 23 | 33.55 | 26.92 | 14.0 | 11.4 |
| **SILVER** |  |  |  |  |  |  |  | 4 | 16 | 6 | 26 | 29.77 | 26.33 | 6.83 | 12.8 |
| **BIST30** |  |  |  |  |  |  |  | 1 | 5 | 3 | 9 | 78.0 | 75.08 | 14.83 | 5.3 |
| **AEFES** |  |  |  |  |  |  |  | 1 | 1 | 2 | 4 | 197.0 | 142.0 | 75.0 | 2.5 |
| **AKBNK** |  |  |  |  |  |  |  | 1 | 3 | 4 | 8 | 92.14 | 79.0 | 58.17 | 4.5 |
| **ASELS** |  |  |  |  |  |  |  | 1 | 4 | 3 | 8 | 77.45 | 71.0 | 50.17 | 5.4 |
| **ASTOR** |  |  |  |  |  |  |  | 1 | 3 | 3 | 7 | 97.33 | 110.5 | 17.0 | 4.4 |
| **BIMAS** |  |  |  |  |  |  |  | 1 | 4 | 3 | 8 | 82.71 | 72.0 | 28.0 | 5.0 |
| **EKGYO** |  |  |  |  |  |  |  | 1 | 5 | 2 | 8 | 92.74 | 76.0 | 15.0 | 4.5 |
| **ENKAI** |  |  |  |  |  |  |  | 1 | 4 | 2 | 7 | 85.5 | 74.08 | 65.17 | 5.0 |
| **EREGL** |  |  |  |  |  |  |  | 1 | 3 | 5 | 9 | 80.65 | 77.0 | 13.17 | 5.1 |
| **FROTO** |  |  |  |  |  |  |  |  | 2 | 1 | 3 | 153.5 | 153.5 | 120.0 | 3.6 |
| **GARAN** |  |  |  |  |  |  |  | 1 | 4 |  | 5 | 92.75 | 92.08 | 75.83 | 4.9 |
| **GUBRF** |  |  |  |  |  |  |  | 1 | 4 | 2 | 7 | 108.17 | 108.0 | 27.0 | 3.9 |
| **ISCTR** |  |  |  |  |  |  |  | 1 | 4 | 1 | 6 | 87.2 | 74.83 | 30.17 | 5.0 |
| **KCHOL** |  |  |  |  |  |  |  |  | 3 | 3 | 6 | 80.8 | 72.83 | 61.0 | 5.4 |
| **KRDMD** |  |  |  |  |  |  |  | 1 | 3 | 3 | 7 | 99.69 | 91.58 | 64.0 | 4.3 |
| **MGROS** |  |  |  |  |  |  |  | 1 | 4 | 1 | 6 | 98.2 | 117.0 | 26.0 | 4.5 |
| **PETKM** |  |  |  |  |  |  |  |  | 1 | 3 | 4 | 137.72 | 148.17 | 75.0 | 3.5 |
| **PGSUS** |  |  |  |  |  |  |  |  | 4 |  | 4 | 58.72 | 29.83 | 29.17 | 8.3 |
| **SAHOL** |  |  |  |  |  |  |  | 1 | 2 | 3 | 6 | 128.37 | 144.83 | 88.83 | 3.4 |
| **SASA** |  |  |  |  |  |  |  |  | 1 | 2 | 3 | 196.0 | 196.0 | 130.0 | 2.8 |
| **SISE** |  |  |  |  |  |  |  | 1 | 2 | 3 | 6 | 108.43 | 79.0 | 43.17 | 4.0 |
| **TAVHL** |  |  |  |  |  |  |  | 1 | 2 | 2 | 5 | 124.75 | 82.33 | 66.17 | 3.7 |
| **TCELL** |  |  |  |  |  |  |  |  | 5 | 2 | 7 | 77.0 | 68.5 | 42.0 | 5.5 |
| **THYAO** |  |  |  |  |  |  |  | 1 | 3 | 3 | 7 | 95.0 | 80.0 | 16.0 | 4.5 |
| **TOASO** |  |  |  |  |  |  |  |  | 5 | 2 | 7 | 76.17 | 77.5 | 49.83 | 5.6 |
| **TTKOM** |  |  |  |  |  |  |  |  | 3 | 2 | 5 | 111.04 | 112.67 | 63.0 | 4.1 |
| **TUPRS** |  |  |  |  |  |  |  |  | 2 | 3 | 5 | 91.0 | 93.0 | 66.17 | 5.0 |
| **VAKBN** |  |  |  |  |  |  |  | 1 | 3 | 2 | 6 | 124.4 | 109.17 | 69.17 | 3.5 |
| **YKBNK** |  |  |  |  |  |  |  | 1 | 4 | 3 | 8 | 81.12 | 76.17 | 40.83 | 5.2 |

### Akış COOLDOWN_ONLY — LONG

| Varlık | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | TOPLAM | ort. aralık (gün) | medyan (gün) | min (gün) | sinyal/yıl |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **BTC** | 20 | 18 | 45 | 69 | 51 | 15 | 39 | 52 | 34 | 23 | 366 | 8.81 | 2.67 | 0.67 | 41.6 |
| **GOLD** |  |  |  |  |  |  |  | 18 | 70 | 21 | 109 | 6.83 | 2.67 | 0.67 | 53.9 |
| **SILVER** |  |  |  |  |  |  |  | 8 | 50 | 21 | 79 | 9.54 | 4.67 | 0.67 | 38.8 |
| **BIST30** |  |  |  |  |  |  |  | 2 | 18 | 18 | 38 | 17.41 | 9.0 | 2.0 | 21.6 |
| **AEFES** |  |  |  |  |  |  |  | 1 | 2 | 11 | 14 | 45.46 | 9.0 | 2.0 | 8.7 |
| **AKBNK** |  |  |  |  |  |  |  | 3 | 10 | 8 | 21 | 32.25 | 19.0 | 2.0 | 11.9 |
| **ASELS** |  |  |  |  |  |  |  | 2 | 23 | 14 | 39 | 14.27 | 6.58 | 2.0 | 26.3 |
| **ASTOR** |  |  |  |  |  |  |  | 3 | 9 | 17 | 29 | 22.82 | 13.0 | 2.0 | 16.6 |
| **BIMAS** |  |  |  |  |  |  |  | 1 | 11 | 21 | 33 | 19.97 | 7.5 | 2.0 | 18.9 |
| **EKGYO** |  |  |  |  |  |  |  | 3 | 14 | 7 | 24 | 28.22 | 15.0 | 2.0 | 13.5 |
| **ENKAI** |  |  |  |  |  |  |  | 1 | 9 | 5 | 15 | 36.64 | 21.83 | 2.83 | 10.7 |
| **EREGL** |  |  |  |  |  |  |  | 2 | 9 | 13 | 24 | 28.05 | 13.17 | 2.0 | 13.6 |
| **FROTO** |  |  |  |  |  |  |  |  | 7 | 7 | 14 | 26.15 | 5.17 | 2.0 | 15.0 |
| **GARAN** |  |  |  |  |  |  |  | 4 | 9 | 4 | 17 | 27.2 | 19.5 | 3.0 | 14.3 |
| **GUBRF** |  |  |  |  |  |  |  | 4 | 13 | 12 | 29 | 23.18 | 8.0 | 2.0 | 16.3 |
| **ISCTR** |  |  |  |  |  |  |  | 2 | 10 | 6 | 18 | 25.65 | 18.17 | 2.0 | 15.1 |
| **KCHOL** |  |  |  |  |  |  |  |  | 9 | 11 | 20 | 22.32 | 13.83 | 2.17 | 17.2 |
| **KRDMD** |  |  |  |  |  |  |  | 3 | 11 | 16 | 30 | 22.21 | 8.0 | 2.0 | 17.0 |
| **MGROS** |  |  |  |  |  |  |  | 5 | 9 | 12 | 26 | 22.36 | 7.0 | 2.0 | 17.0 |
| **PETKM** |  |  |  |  |  |  |  |  | 5 | 8 | 13 | 34.43 | 13.0 | 2.0 | 11.5 |
| **PGSUS** |  |  |  |  |  |  |  |  | 8 |  | 8 | 25.17 | 14.0 | 2.0 | 16.6 |
| **SAHOL** |  |  |  |  |  |  |  | 1 | 7 | 9 | 17 | 40.11 | 12.5 | 2.0 | 9.7 |
| **SASA** |  |  |  |  |  |  |  |  | 1 | 2 | 3 | 196.0 | 196.0 | 130.0 | 2.8 |
| **SISE** |  |  |  |  |  |  |  | 1 | 5 | 7 | 13 | 45.18 | 28.5 | 7.0 | 8.8 |
| **TAVHL** |  |  |  |  |  |  |  | 3 | 11 | 7 | 21 | 25.05 | 5.92 | 2.0 | 15.3 |
| **TCELL** |  |  |  |  |  |  |  |  | 11 | 9 | 20 | 25.95 | 7.17 | 2.0 | 14.8 |
| **THYAO** |  |  |  |  |  |  |  | 1 | 9 | 8 | 18 | 33.76 | 7.83 | 2.0 | 11.5 |
| **TOASO** |  |  |  |  |  |  |  |  | 9 | 11 | 20 | 26.26 | 15.0 | 2.0 | 14.6 |
| **TTKOM** |  |  |  |  |  |  |  |  | 8 | 7 | 15 | 31.73 | 10.58 | 2.0 | 12.3 |
| **TUPRS** |  |  |  |  |  |  |  |  | 10 | 15 | 25 | 17.38 | 5.67 | 2.0 | 21.9 |
| **VAKBN** |  |  |  |  |  |  |  | 1 | 13 | 6 | 20 | 32.74 | 10.17 | 2.0 | 11.7 |
| **YKBNK** |  |  |  |  |  |  |  | 3 | 12 | 7 | 22 | 27.23 | 18.0 | 2.17 | 14.1 |

## 7) ZİNCİR HALKALARI (strict akışı)

| Varlık | regime | context | tradable | return_valid | momentum | trigger | stop_valid |
|---|---:|---:|---:|---:|---:|---:|---:|
| **BTC** | 8489 | — | 8489 | 8489 | 3206 | 592 | 592 |
| **GOLD** | 1932 | — | 1915 | 1915 | 816 | 212 | 212 |
| **SILVER** | 1615 | — | 1602 | 1602 | 661 | 138 | 138 |
| **BIST30** | 640 | — | 630 | 630 | 297 | 70 | 70 |
| **AEFES** | 356 | 329 | 320 | 320 | 144 | 26 | 26 |
| **AKBNK** | 478 | 447 | 442 | 442 | 199 | 30 | 30 |
| **ASELS** | 791 | 623 | 610 | 610 | 318 | 75 | 75 |
| **ASTOR** | 560 | 507 | 497 | 497 | 252 | 47 | 47 |
| **BIMAS** | 658 | 598 | 578 | 578 | 253 | 43 | 43 |
| **EKGYO** | 574 | 484 | 476 | 476 | 216 | 44 | 44 |
| **ENKAI** | 683 | 523 | 501 | 501 | 202 | 23 | 23 |
| **EREGL** | 504 | 424 | 414 | 414 | 190 | 42 | 42 |
| **FROTO** | 253 | 217 | 213 | 213 | 93 | 27 | 27 |
| **GARAN** | 461 | 430 | 426 | 426 | 159 | 22 | 22 |
| **GUBRF** | 688 | 558 | 550 | 550 | 263 | 49 | 49 |
| **ISCTR** | 416 | 405 | 399 | 399 | 176 | 29 | 29 |
| **KCHOL** | 440 | 420 | 415 | 415 | 183 | 35 | 35 |
| **KRDMD** | 536 | 505 | 499 | 499 | 233 | 50 | 50 |
| **MGROS** | 483 | 458 | 448 | 448 | 205 | 44 | 44 |
| **PETKM** | 231 | 224 | 219 | 219 | 120 | 27 | 27 |
| **PGSUS** | 209 | 146 | 144 | 144 | 71 | 14 | 14 |
| **SAHOL** | 413 | 404 | 400 | 400 | 189 | 27 | 27 |
| **SASA** | 77 | 54 | 52 | 52 | 28 | 4 | 4 |
| **SISE** | 279 | 275 | 271 | 271 | 118 | 15 | 15 |
| **TAVHL** | 397 | 366 | 362 | 362 | 165 | 33 | 33 |
| **TCELL** | 418 | 382 | 375 | 375 | 160 | 33 | 33 |
| **THYAO** | 403 | 363 | 357 | 357 | 166 | 33 | 33 |
| **TOASO** | 415 | 373 | 366 | 366 | 182 | 42 | 42 |
| **TTKOM** | 475 | 358 | 353 | 353 | 159 | 29 | 29 |
| **TUPRS** | 525 | 463 | 453 | 453 | 205 | 47 | 47 |
| **VAKBN** | 518 | 470 | 465 | 465 | 206 | 33 | 33 |
| **YKBNK** | 502 | 470 | 465 | 465 | 195 | 37 | 37 |

## 8) UYGULANAMAYAN SİNYALLER

| Varlık | strict long sinyali | uygulanabilir | **uygulanamaz** | sebep |
|---|---:|---:|---:|---|
| **BTC** | 3 | 3 | **0** | — |
| **GOLD** | 1 | 1 | **0** | — |
| **SILVER** | 3 | 3 | **0** | — |
| **BIST30** | 2 | 2 | **0** | — |
| **AEFES** | 2 | 2 | **0** | — |
| **AKBNK** | 3 | 3 | **0** | — |
| **ASELS** | 1 | 1 | **0** | — |
| **ASTOR** | 3 | 3 | **0** | — |
| **BIMAS** | 2 | 2 | **0** | — |
| **EKGYO** | 2 | 2 | **0** | — |
| **ENKAI** | 2 | 2 | **0** | — |
| **EREGL** | 2 | 2 | **0** | — |
| **FROTO** | 2 | 2 | **0** | — |
| **GARAN** | 3 | 3 | **0** | — |
| **GUBRF** | 1 | 1 | **0** | — |
| **ISCTR** | 4 | 4 | **0** | — |
| **KCHOL** | 2 | 2 | **0** | — |
| **KRDMD** | 3 | 3 | **0** | — |
| **MGROS** | 3 | 3 | **0** | — |
| **PETKM** | 2 | 2 | **0** | — |
| **PGSUS** | 4 | 4 | **0** | — |
| **SAHOL** | 3 | 3 | **0** | — |
| **SASA** | 3 | 3 | **0** | — |
| **SISE** | 3 | 3 | **0** | — |
| **TAVHL** | 3 | 3 | **0** | — |
| **TCELL** | 4 | 4 | **0** | — |
| **THYAO** | 5 | 5 | **0** | — |
| **TOASO** | 3 | 3 | **0** | — |
| **TTKOM** | 3 | 3 | **0** | — |
| **TUPRS** | 1 | 1 | **0** | — |
| **VAKBN** | 3 | 3 | **0** | — |
| **YKBNK** | 2 | 2 | **0** | — |

## ZORUNLU CAVEAT'LER

- Bu tablodaki sinyal SAYILARI **GEÇİCİDİR**: pozisyon vekiline (yalnız stop ihlali) bağlıdır. Aşama 6/7'de gerçek çıkış motoru (TP, partial+runner, trailing, time-stop) geldiğinde yeniden üretilecektir.
- Sinyal sayısı bir **başarı ölçüsü DEĞİLDİR**. Az sinyal = az yanlış sinyal değildir; precision/recall/F1 ve expectancy ölçümü Aşama 5'in kalan işi ve Aşama 6'nın konusudur.
- `n=10`, `m=1.0`, `cooldown=3`, `Donchian=20` **VARSAYILANDIR**, optimize EDİLMEMİŞTİR. Seçim Aşama 9'da, yalnızca core varlıklar üzerinde.
- BIST30 sepeti **survivorship bias** taşır; sinyal sayıları da bu çarpık örnekleme aittir.
- XU030 satırı **bağlam kaynağıdır**; trade edilmez, sinyali portföye yazılmaz.
