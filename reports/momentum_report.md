# AŞAMA 4 — Momentum Onayı ve Sinyal Zinciri Raporu

*Üretim: 2026-09-16T14:20:28 UTC* · timeframe **4h** · **n=10**, **m=1.0 ATR** (varsayılan)

## TEK MOMENTUM KURALI

```
mom = (close/close.shift(n) − 1) / (ATR14/close.shift(n))
long  onayı: mom > +m        short onayı: mom < −m   (short yalnız CORE)
```

- **YASAKLI olanlar kullanılmadı:** RSI, MACD, Stochastic, StochRSI, MFI, OBV, CCI, Williams%R
- **Karar anı sözleşmesi:** bar t kararı bar t AÇILIŞINDA verilir; close[t−1] ve close[t−n] o ana kadar KAPANMIŞTIR
- **Guard (fail-closed):** ATR NaN/<=0 · close[t−n] NaN/<=0 · non_tradable · return_valid==False · ilk 10 bar (warmup)
- **ATR politikası:** ATR kolonu VARSA kullanılır (Aşama 2 ile aynı seri); yoksa hesaplanır. Tamamen NaN olsa bile YENİDEN HESAPLANMAZ — guard yakalar.
- **Parametre seçimi YOK:** aday kümeler `n=[5, 10, 20]`, `m=[0.5, 1.0, 1.5]` → yalnızca **Aşama 9**, yalnızca **['BTC', 'GOLD', 'SILVER']** üzerinde. `per_asset_in_sample_tuning_allowed=False`
- **Kalibrasyon bandı:** [0.10, 0.60] · bant dışında **TUNE EDİLMEZ**, yalnızca bayraklanır (`tune_out_of_band=False`)

## SİNYAL ZİNCİRİ (kabul kriteri 5)

```
long_final_ok  = long_regime_ok ∧ longs_allowed ∧ ~non_tradable ∧ return_valid ∧ stop_valid_long ∧ momentum_ok
short_final_ok = short_regime_ok ∧ ~non_tradable ∧ return_valid ∧ stop_valid_short ∧ momentum_short_ok   (yalnız CORE)
```

> Bir kapı kolonu frame'de YOKSA zincir **False** üretir (fail-closed); sessizce 'geçti' sayılmaz. `test_missing_gate_is_fail_closed_not_pass` ile kilitli.

## KALİBRASYON: MOMENTUM GEÇİŞ ORANLARI

Bant **[10%, 60%]**. Oran = `momentum_ok` / `momentum_valid`.

| Varlık | bar | mom geçerli % | **long geçiş %** | short geçiş % | bant | mom p05/p50/p95 | |mom| p50 |
|---|---:|---:|---:|---:|---|---|---:|
| **BTC** | 19888 | %99.9 | **%30.5** | %26.7 | ✅ içinde | -3.122 / 0.096 / 3.458 | 1.209 |
| **GOLD** | 3606 | %98.8 | **%37.2** | %26.8 | ✅ içinde | -3.057 / 0.317 / 3.862 | 1.482 |
| **SILVER** | 3606 | %98.8 | **%36.0** | %27.3 | ✅ içinde | -3.097 / 0.265 / 3.66 | 1.401 |
| **XU030** | 1435 | %97.4 | **%43.0** | %29.4 | ✅ içinde | -3.689 / 0.534 / 4.745 | 1.916 |
| **AEFES** | 1436 | %96.7 | **%38.7** | %0.0 | ✅ içinde | -3.75 / 0.286 / 4.183 | 1.734 |
| **AKBNK** | 1436 | %96.7 | **%40.9** | %0.0 | ✅ içinde | -3.78 / 0.448 / 4.35 | 1.77 |
| **ASELS** | 1436 | %96.7 | **%43.3** | %0.0 | ✅ içinde | -3.318 / 0.582 / 4.822 | 1.628 |
| **ASTOR** | 1436 | %96.9 | **%38.1** | %0.0 | ✅ içinde | -3.844 / 0.227 / 4.233 | 1.777 |
| **BIMAS** | 1436 | %95.6 | **%39.8** | %0.0 | ✅ içinde | -3.085 / 0.342 / 4.157 | 1.56 |
| **EKGYO** | 1436 | %96.9 | **%40.9** | %0.0 | ✅ içinde | -3.842 / 0.39 / 4.571 | 1.735 |
| **ENKAI** | 1436 | %95.9 | **%37.5** | %0.0 | ✅ içinde | -3.068 / 0.281 / 3.912 | 1.591 |
| **EREGL** | 1436 | %96.7 | **%38.3** | %0.0 | ✅ içinde | -3.912 / 0.363 / 4.129 | 1.696 |
| **FROTO** | 1436 | %96.3 | **%34.2** | %0.0 | ✅ içinde | -3.716 / -0.136 / 4.308 | 1.801 |
| **GARAN** | 1436 | %96.8 | **%37.8** | %0.0 | ✅ içinde | -3.371 / 0.288 / 4.059 | 1.562 |
| **GUBRF** | 1436 | %97.4 | **%38.0** | %0.0 | ✅ içinde | -3.443 / 0.336 / 3.987 | 1.624 |
| **ISCTR** | 1435 | %96.7 | **%38.8** | %0.0 | ✅ içinde | -3.947 / 0.322 / 4.133 | 1.787 |
| **KCHOL** | 1436 | %96.8 | **%35.7** | %0.0 | ✅ içinde | -4.124 / 0.182 / 4.28 | 1.681 |
| **KRDMD** | 1436 | %97.1 | **%37.6** | %0.0 | ✅ içinde | -3.6 / 0.174 / 3.855 | 1.699 |
| **MGROS** | 1436 | %96.3 | **%39.0** | %0.0 | ✅ içinde | -4.119 / 0.356 / 3.837 | 1.646 |
| **PETKM** | 1436 | %97.4 | **%36.8** | %0.0 | ✅ içinde | -4.085 / 0.129 / 4.083 | 1.736 |
| **PGSUS** | 1436 | %97.4 | **%33.1** | %0.0 | ✅ içinde | -3.911 / -0.09 / 3.935 | 1.642 |
| **SAHOL** | 1436 | %96.9 | **%39.8** | %0.0 | ✅ içinde | -3.598 / 0.246 / 3.952 | 1.705 |
| **SASA** | 1436 | %97.4 | **%29.8** | %0.0 | ✅ içinde | -4.222 / -0.276 / 4.135 | 1.653 |
| **SISE** | 1435 | %96.7 | **%32.3** | %0.0 | ✅ içinde | -3.953 / -0.207 / 4.085 | 1.705 |
| **TAVHL** | 1436 | %97.1 | **%38.0** | %0.0 | ✅ içinde | -3.413 / 0.194 / 4.115 | 1.67 |
| **TCELL** | 1436 | %96.5 | **%36.8** | %0.0 | ✅ içinde | -3.431 / 0.157 / 4.001 | 1.529 |
| **THYAO** | 1436 | %96.9 | **%34.8** | %0.0 | ✅ içinde | -4.108 / 0.122 / 4.148 | 1.575 |
| **TOASO** | 1436 | %96.8 | **%37.0** | %0.0 | ✅ içinde | -4.207 / 0.199 / 4.117 | 1.593 |
| **TTKOM** | 1436 | %97.4 | **%37.5** | %0.0 | ✅ içinde | -3.297 / 0.223 / 4.072 | 1.47 |
| **TUPRS** | 1436 | %96.4 | **%36.8** | %0.0 | ✅ içinde | -3.371 / 0.113 / 4.725 | 1.671 |
| **VAKBN** | 1436 | %97.4 | **%37.0** | %0.0 | ✅ içinde | -3.68 / 0.336 / 4.247 | 1.545 |
| **YKBNK** | 1436 | %97.1 | **%38.2** | %0.0 | ✅ içinde | -3.998 / 0.257 / 4.577 | 1.868 |

### ✅ Tüm varlıklar kalibrasyon bandı içinde — bayrak YOK

## ZİNCİR HALKALARI: BAR SAYILARI (sıralı)

| Varlık | regime | context | tradable | return_valid | levels | momentum | **FINAL long** | % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **BTC** | 8489 | — | 8489 | 8489 | 8244 | 3206 | **3206** | %16.1 |
| **GOLD** | 1932 | — | 1915 | 1915 | 1834 | 816 | **816** | %22.6 |
| **SILVER** | 1615 | — | 1602 | 1602 | 1569 | 661 | **661** | %18.3 |
| **XU030** | 640 | — | 630 | 630 | 563 | 293 | **293** | %20.4 |
| **AEFES** | 356 | 329 | 320 | 320 | 316 | 144 | **144** | %10.0 |
| **AKBNK** | 478 | 447 | 442 | 442 | 431 | 199 | **199** | %13.9 |
| **ASELS** | 791 | 623 | 610 | 610 | 563 | 318 | **318** | %22.1 |
| **ASTOR** | 560 | 507 | 497 | 497 | 464 | 252 | **252** | %17.5 |
| **BIMAS** | 658 | 598 | 578 | 578 | 564 | 252 | **252** | %17.5 |
| **EKGYO** | 574 | 484 | 476 | 476 | 450 | 216 | **216** | %15.0 |
| **ENKAI** | 683 | 523 | 501 | 501 | 438 | 202 | **202** | %14.1 |
| **EREGL** | 504 | 424 | 414 | 414 | 376 | 188 | **188** | %13.1 |
| **FROTO** | 253 | 217 | 213 | 213 | 206 | 93 | **93** | %6.5 |
| **GARAN** | 461 | 430 | 426 | 426 | 404 | 159 | **159** | %11.1 |
| **GUBRF** | 688 | 558 | 550 | 550 | 508 | 263 | **263** | %18.3 |
| **ISCTR** | 416 | 405 | 399 | 399 | 374 | 176 | **176** | %12.3 |
| **KCHOL** | 440 | 420 | 415 | 415 | 393 | 183 | **183** | %12.7 |
| **KRDMD** | 536 | 505 | 499 | 499 | 474 | 233 | **233** | %16.2 |
| **MGROS** | 483 | 458 | 448 | 448 | 433 | 205 | **205** | %14.3 |
| **PETKM** | 231 | 224 | 219 | 219 | 214 | 120 | **120** | %8.4 |
| **PGSUS** | 209 | 146 | 144 | 144 | 143 | 71 | **71** | %4.9 |
| **SAHOL** | 413 | 404 | 400 | 400 | 376 | 189 | **189** | %13.2 |
| **SASA** | 77 | 54 | 52 | 52 | 52 | 28 | **28** | %1.9 |
| **SISE** | 279 | 275 | 271 | 271 | 255 | 118 | **118** | %8.2 |
| **TAVHL** | 397 | 366 | 362 | 362 | 340 | 165 | **165** | %11.5 |
| **TCELL** | 418 | 382 | 375 | 375 | 370 | 160 | **160** | %11.1 |
| **THYAO** | 403 | 363 | 357 | 357 | 330 | 162 | **162** | %11.3 |
| **TOASO** | 415 | 373 | 366 | 366 | 341 | 182 | **182** | %12.7 |
| **TTKOM** | 475 | 358 | 353 | 353 | 333 | 158 | **158** | %11.0 |
| **TUPRS** | 525 | 463 | 453 | 453 | 416 | 205 | **205** | %14.3 |
| **VAKBN** | 518 | 470 | 465 | 465 | 427 | 206 | **206** | %14.3 |
| **YKBNK** | 502 | 470 | 465 | 465 | 440 | 195 | **195** | %13.6 |

### CORE varlıklar — short zinciri

| Varlık | regime | tradable | return_valid | levels | momentum | **FINAL short** |
|---|---:|---:|---:|---:|---:|---:|
| **BTC** | 7759 | 7758 | 7758 | 7424 | 2412 | **2412** |
| **GOLD** | 678 | 673 | 673 | 625 | 281 | **281** |
| **SILVER** | 803 | 797 | 797 | 745 | 279 | **279** |

> Hisselerde short zinciri **politika gereği üretilmez** (`STOCK_ALLOW_SHORT=False`, KARAR 4: LONG-ONLY).

## FİNAL SİNYAL ÖZETİ

| Varlık | bar | rejim long | bağlam izin | seviye (stop) geçerli | mom long | **FINAL long** | **%** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **BTC** | 19888 | 8489 | — | 18319 | 3206 | **3206** | %16.1 |
| **GOLD** | 3606 | 1932 | — | 3326 | 816 | **816** | %22.6 |
| **SILVER** | 3606 | 1615 | — | 3297 | 661 | **661** | %18.3 |
| **XU030** | 1435 | 640 | — | 1242 | 293 | **293** | %20.4 |
| **AEFES** | 1436 | 356 | 913 | 1272 | 144 | **144** | %10.0 |
| **AKBNK** | 1436 | 478 | 913 | 1240 | 199 | **199** | %13.9 |
| **ASELS** | 1436 | 791 | 913 | 1315 | 318 | **318** | %22.1 |
| **ASTOR** | 1436 | 560 | 913 | 1218 | 252 | **252** | %17.5 |
| **BIMAS** | 1436 | 658 | 913 | 1311 | 252 | **252** | %17.5 |
| **EKGYO** | 1436 | 574 | 913 | 1275 | 216 | **216** | %15.0 |
| **ENKAI** | 1436 | 683 | 913 | 1255 | 202 | **202** | %14.1 |
| **EREGL** | 1436 | 504 | 913 | 1238 | 188 | **188** | %13.1 |
| **FROTO** | 1436 | 253 | 913 | 1194 | 93 | **93** | %6.5 |
| **GARAN** | 1436 | 461 | 913 | 1257 | 159 | **159** | %11.1 |
| **GUBRF** | 1436 | 688 | 913 | 1213 | 263 | **263** | %18.3 |
| **ISCTR** | 1435 | 416 | 912 | 1224 | 176 | **176** | %12.3 |
| **KCHOL** | 1436 | 440 | 913 | 1221 | 183 | **183** | %12.7 |
| **KRDMD** | 1436 | 536 | 913 | 1274 | 233 | **233** | %16.2 |
| **MGROS** | 1436 | 483 | 913 | 1275 | 205 | **205** | %14.3 |
| **PETKM** | 1436 | 231 | 913 | 1258 | 120 | **120** | %8.4 |
| **PGSUS** | 1436 | 209 | 913 | 1242 | 71 | **71** | %4.9 |
| **SAHOL** | 1436 | 413 | 913 | 1247 | 189 | **189** | %13.2 |
| **SASA** | 1436 | 77 | 913 | 1175 | 28 | **28** | %1.9 |
| **SISE** | 1435 | 279 | 912 | 1169 | 118 | **118** | %8.2 |
| **TAVHL** | 1436 | 397 | 913 | 1254 | 165 | **165** | %11.5 |
| **TCELL** | 1436 | 418 | 913 | 1290 | 160 | **160** | %11.1 |
| **THYAO** | 1436 | 403 | 913 | 1236 | 162 | **162** | %11.3 |
| **TOASO** | 1436 | 415 | 913 | 1225 | 182 | **182** | %12.7 |
| **TTKOM** | 1436 | 475 | 913 | 1303 | 158 | **158** | %11.0 |
| **TUPRS** | 1436 | 525 | 913 | 1250 | 205 | **205** | %14.3 |
| **VAKBN** | 1436 | 518 | 913 | 1228 | 206 | **206** | %14.3 |
| **YKBNK** | 1436 | 502 | 913 | 1239 | 195 | **195** | %13.6 |
| **SEPET TOPLAM (28 hisse)** | 40206 | | | | | **5042** | %12.54 |

## ZORUNLU CAVEAT'LER

- Momentum onayı bir **olasılık filtresidir**, kesinlik değildir. Geçmiş geçiş oranları gelecekteki oranları garanti etmez.
- `n=10` ve `m=1.0` **VARSAYILANDIR**, optimize EDİLMEMİŞTİR. Aşama 9'da küçük aday kümesiyle ve yalnızca core varlıklar üzerinde test edilecek; hisseler yalnızca OOS raporlanacak.
- Guard'ın elediği barlar (kesinti, ince bar, kurumsal aksiyon, oluşmakta olan bar) **silinmez**; yalnızca sinyale katılmaz. Bu, örneklem sayısını küçültür ama veri bütünlüğünü korur.
- BIST30 sepeti **survivorship bias** taşır: momentum geçiş oranları da bu çarpık örnekleme aittir.
- Zincirdeki her halka **fail-closed**'tur: kolon yoksa veya değer bilinmiyorsa sonuç False'tur. Bu tasarım işlem SAYISINI azaltır, yanlış sinyal oranını düşürür.
