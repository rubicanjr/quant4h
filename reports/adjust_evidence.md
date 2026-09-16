# adjust.py Kanit Tablosu (KARAR 2 & KARAR 3)

*Uretim: 2026-09-16 13:56:31 UTC* · `apply_roll_correction=False` · `roll_atr_multiple=3.0`

## 1) Degismezler (hard rules)

| Varlik | bar once | bar sonra | SILINEN | EKLENEN | timestamp ayni | close_raw ayni |
|---|---:|---:|---:|---:|---|---|
| BTC | 19888 | 19888 | **0** | **0** | EVET | EVET |
| GOLD | 3606 | 3606 | **0** | **0** | EVET | EVET |
| SILVER | 3606 | 3606 | **0** | **0** | EVET | EVET |
| BIST30 | 1435 | 1435 | **0** | **0** | EVET | EVET |

> Bar silinmedi, bar uydurulmadi, ham fiyatlar bayt bayt ayni. Yalnizca **isaret** kolonlari eklendi.

## 2) Kesinti / islem-disi isaretleme

| Varlik | kesinti penceresi | pencere ici bar | devami gelen bar | ince bar | non-tradable TOPLAM | gecersiz getiri |
|---|---:|---:|---:|---:|---:|---:|
| BTC | 1 | 0 | 1 | 0 | **1** | **2** |
| GOLD | 22 | 0 | 22 | 13 | **31** | **32** |
| SILVER | 22 | 0 | 22 | 13 | **31** | **32** |
| BIST30 | 25 | 0 | 25 | 0 | **25** | **26** |

## 3) Getiri duzeltmesi: once / sonra

| Varlik | max\|log getiri\| HAM | max\|log getiri\| GECERLI | fark | yorum |
|---|---:|---:|---:|---|
| BTC | 0.2716 | 0.2716 | +0.0000 | ham seride de sahte getiri yok |
| GOLD | 0.0797 | 0.0466 | +0.0330 | sahte getiri seriye girmiyor |
| SILVER | 0.2222 | 0.1665 | +0.0557 | sahte getiri seriye girmiyor |
| BIST30 | 0.0777 | 0.0777 | +0.0000 | ham seride de sahte getiri yok |

## 4) Buyuk hareket siniflandirmasi (DURUST SINIR)

| Varlik | requires_adjustment | aday | bad-print sezgisi | fiyati DUZELTILEN | close_adjusted |
|---|---|---:|---:|---:|---|
| BTC | False | 0 | 0 | 0 | == close_raw |
| GOLD | True | 10 | 0 | 0 | == close_raw |
| SILVER | True | 6 | 0 | 0 | == close_raw |
| BIST30 | False | 0 | 0 | 0 | == close_raw |

> Yahoo on-ay serisinde **kontrat ayi kimligi yoktur**; bu yuzden bir roll ile gercek bir ekstrem hareket fiyattan KESIN olarak ayirt edilemez. Varsayilan politika bu yuzden **FLAG ONLY**'dir: fiyatlar duzeltilmez, adaylar insan incelemesine birakilir. Kalıcılık testi bad print'i ayirt ETMEZ (print sonrasi seviye kaymis gorunur); ayirt edici sezgi **hacim**dir ve bu da bir kanit degildir. Kesin cozum: kontrat ayi kimligi olan bir continuous future kaynagi.

## 5) Tespit edilen kesinti pencereleri (ilk 8, varlik basina)

**BTC** — 1 pencere

| onceki bar (UTC) | devam bari (UTC) | kayip saat | bosluk (bar) | tipik (bar) | boslugu atlayan getiri |
|---|---|---:|---:|---:|---:|
| 2018-02-08 00:00 | 2018-02-09 08:00 | 32 | 8 | 1 | +6.18% |

**GOLD** — 22 pencere

| onceki bar (UTC) | devam bari (UTC) | kayip saat | bosluk (bar) | tipik (bar) | boslugu atlayan getiri |
|---|---|---:|---:|---:|---:|
| 2025-08-29 18:00 | 2025-09-02 02:00 | 80 | 20 | 1 | +1.29% |
| 2026-05-22 18:00 | 2026-05-26 02:00 | 80 | 20 | 1 | +0.10% |
| 2026-09-04 18:00 | 2026-09-08 02:00 | 80 | 20 | 1 | -0.27% |
| 2025-04-17 18:00 | 2025-04-20 22:00 | 76 | 19 | 13 | +1.45% |
| 2026-04-02 18:00 | 2026-04-05 22:00 | 76 | 19 | 13 | -1.09% |
| 2026-01-30 15:00 | 2026-02-02 15:00 | 72 | 18 | 1 | -7.97% |
| 2025-07-11 18:00 | 2025-07-14 02:00 | 56 | 14 | 1 | +0.00% |
| 2026-01-16 19:00 | 2026-01-19 03:00 | 56 | 14 | 1 | +1.51% |

**SILVER** — 22 pencere

| onceki bar (UTC) | devam bari (UTC) | kayip saat | bosluk (bar) | tipik (bar) | boslugu atlayan getiri |
|---|---|---:|---:|---:|---:|
| 2025-08-29 18:00 | 2025-09-02 02:00 | 80 | 20 | 1 | +2.28% |
| 2026-05-22 18:00 | 2026-05-26 02:00 | 80 | 20 | 1 | +0.75% |
| 2026-09-04 18:00 | 2026-09-08 02:00 | 80 | 20 | 1 | +0.67% |
| 2025-04-17 18:00 | 2025-04-20 22:00 | 76 | 19 | 13 | +0.46% |
| 2026-04-02 18:00 | 2026-04-05 22:00 | 76 | 19 | 13 | -1.56% |
| 2026-01-30 15:00 | 2026-02-02 15:00 | 72 | 18 | 1 | -22.22% |
| 2025-07-11 18:00 | 2025-07-14 02:00 | 56 | 14 | 1 | +0.90% |
| 2026-01-16 19:00 | 2026-01-19 03:00 | 56 | 14 | 1 | +3.18% |

**BIST30** — 25 pencere

| onceki bar (UTC) | devam bari (UTC) | kayip saat | bosluk (bar) | tipik (bar) | boslugu atlayan getiri |
|---|---|---:|---:|---:|---:|
| 2024-04-09 07:00 | 2024-04-15 07:00 | 144 | 36 | 17 | -0.95% |
| 2026-05-26 07:00 | 2026-06-01 07:00 | 144 | 36 | 17 | +1.03% |
| 2024-06-14 11:00 | 2024-06-20 07:00 | 140 | 35 | 5 | +1.98% |
| 2025-06-05 07:00 | 2025-06-10 07:00 | 120 | 30 | 5 | +1.53% |
| 2025-03-28 11:00 | 2025-04-02 07:00 | 116 | 29 | 5 | -0.97% |
| 2026-03-19 07:00 | 2026-03-23 07:00 | 96 | 24 | 17 | +0.54% |
| 2023-12-29 11:00 | 2024-01-02 07:00 | 92 | 23 | 5 | +0.60% |
| 2024-07-12 11:00 | 2024-07-16 07:00 | 92 | 23 | 5 | +0.38% |

## 6) KARAR 3 vakasi: SILVER 2026-02-02

`tests/test_adjust.py::test_real_silver_2026_02_02_event_is_flagged_and_preserved` bu vakayi GERCEK veri uzerinden sabitler: bar SILINMEDI, `gap_anomaly=True`, `outage_resumption=True`, `non_tradable=True`, `return_valid=False`, `close_to_close_return=NaN`, `roll_candidate=False`. Yani ne roll ne bad print: **veri kesintisini atlayan sahte getiri.**
