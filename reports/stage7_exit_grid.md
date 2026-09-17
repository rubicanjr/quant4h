# AŞAMA 7 — Çıkış mimarisi karşılaştırma grid'i

*Üretim: 2026-09-17T08:47:45.405227+00:00* · timeframe **4h** · risk **balanced** (%0.50/işlem) · başlangıç 100,000 · sinyal akışı **CAPPED** (proxy TS90)

> ⚠️ **TÜM HÜCRELER IN-SAMPLE'DIR — SEÇİM YOK.** Profil/anchor seçimi YALNIZ Aşama 9'da, ön-kayıtlı OOS split'lerle, yalnız core varlıklarda yapılır. En iyi/en kötü işaretleri TANIMLAYICIDIR; **ÖNERİ DEĞİLDİR**. Aşama 8 risk limitleri (kova ısısı, korelasyon, tavanlar) UYGULANMAMIŞTIR.

✅ **P0×A0 regresyon kilidi:** Aşama 6 baseline birebir yeniden üretildi (reports/backtest_baseline.json; motor refactor'ü + D6 aynı-bar giriş kilidi baseline'ı DEĞİŞTİRMEDİ).

**Profiller:** `P0` baseline: TS90 + TP3R (Aşama 6) · `P1` partial+runner: 1R'de %50 + stop→BE + runner chandelier ATR×3 (TS/TP YOK) · `P2` trailing: girişten chandelier ATR×3 (dondurulmuş stop'un altına inmez, yalnız yukarı taşınır — ratchet), TP YOK, TS90 emniyet · `P3` breakeven: 1R sonrası stop→BE, TP3R + TS90 (partial YOK)

**Anchor'lar:** `A0` onaylı swing − 1.0×ATR (mevcut) · `A1` Donchian(20) ters bandı (buffer YOK) · `A2` onaylı swing − 0.5×ATR (kilitli küme içi)

## BTC

| hücre | trade | win% | PF(net) | expR | expR CI95 | P(expR>0) | maxDD | ort.tutma | exposure | net% | zayıf |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| P0xA0 | 187 | 40.1 | 1.307 | +0.206 | [+0.006, +0.422] | 0.98 | -7.05% | 59.6 | 57.0% | +15.47% |  |
| P0xA1 | 192 | 38.5 | 1.213 | +0.168 | [-0.030, +0.376] | 0.95 | -6.82% | 57.2 | 56.2% | +11.88% |  |
| P0xA2 | 192 | 39.1 | 1.281 | +0.216 | [+0.006, +0.418] | 0.98 | -7.83% | 54.9 | 53.9% | +16.04% |  |
| P1xA0 | 156 | 52.6 | 1.220 | +0.156 | [-0.026, +0.342] | 0.95 | -4.63% | 75.7 | 56.0% | +8.80% |  |
| P1xA1 | 162 | 50.0 | 1.112 | +0.109 | [-0.069, +0.306] | 0.88 | -5.09% | 73.8 | 57.1% | +4.92% |  |
| P1xA2 | 163 | 54.0 | 1.320 | +0.213 | [+0.021, +0.395] | 0.99 | -4.72% | 67.1 | 52.8% | +13.27% |  |
| P2xA0 | 187 | 38.0 | 1.775 | +0.225 | [+0.088, +0.396] | 1.00 | -2.80% | 17.4 | 17.3% | +17.59% |  |
| P2xA1 | 192 | 38.0 | 1.636 | +0.210 | [+0.066, +0.358] | 1.00 | -4.19% | 17.1 | 17.4% | +16.19% |  |
| P2xA2 | 192 | 38.5 | 1.764 | +0.256 | [+0.092, +0.454] | 1.00 | -3.41% | 17.2 | 17.6% | +20.52% |  |
| P3xA0 | 187 | 33.7 | 1.433 | +0.234 | [+0.050, +0.439] | 0.99 | -5.74% | 54.0 | 51.7% | +18.24% |  |
| P3xA1 | 192 | 33.9 | 1.359 | +0.215 | [+0.028, +0.417] | 0.99 | -5.47% | 52.9 | 52.0% | +16.60% |  |
| P3xA2 | 192 | 32.8 | 1.445 | +0.262 | [+0.074, +0.465] | 1.00 | -6.11% | 49.1 | 48.4% | +20.80% |  |

*Tanımlayıcı (ÖNERİ DEĞİL): en yüksek expR `P3xA2` (+0.262R) · en düşük expR `P1xA1` (+0.109R) — in-sample.*

## GOLD

| hücre | trade | win% | PF(net) | expR | expR CI95 | P(expR>0) | maxDD | ort.tutma | exposure | net% | zayıf |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| P0xA0 | 30 | 56.7 | 2.673 | +0.626 | [+0.093, +1.194] | 0.99 | -2.12% | 67.8 | 57.2% | +8.66% | ⚠️ |
| P0xA1 | 32 | 50.0 | 2.037 | +0.502 | [-0.004, +1.041] | 0.97 | -2.16% | 62.6 | 56.4% | +7.14% | ⚠️ |
| P0xA2 | 32 | 53.1 | 2.167 | +0.527 | [+0.023, +1.071] | 0.98 | -2.15% | 64.2 | 57.9% | +7.54% | ⚠️ |
| P1xA0 | 24 | 66.7 | 1.810 | +0.345 | [-0.061, +0.754] | 0.95 | -1.21% | 73.2 | 49.4% | +3.52% | ⚠️ |
| P1xA1 | 28 | 60.7 | 1.458 | +0.246 | [-0.165, +0.622] | 0.88 | -1.57% | 62.4 | 48.4% | +2.64% | ⚠️ |
| P1xA2 | 30 | 63.3 | 1.435 | +0.229 | [-0.131, +0.533] | 0.88 | -1.57% | 50.1 | 42.5% | +2.54% | ⚠️ |
| P2xA0 | 30 | 50.0 | 2.407 | +0.249 | [+0.020, +0.511] | 0.99 | -0.67% | 19.9 | 17.4% | +2.87% | ⚠️ |
| P2xA1 | 32 | 50.0 | 1.794 | +0.190 | [-0.013, +0.437] | 0.96 | -0.67% | 19.6 | 18.3% | +2.05% | ⚠️ |
| P2xA2 | 32 | 50.0 | 1.879 | +0.206 | [+0.003, +0.440] | 0.98 | -0.61% | 19.8 | 18.4% | +2.30% | ⚠️ |
| P3xA0 | 30 | 46.7 | 2.542 | +0.536 | [+0.041, +1.083] | 0.98 | -1.63% | 61.8 | 52.2% | +7.24% | ⚠️ |
| P3xA1 | 32 | 40.6 | 1.925 | +0.400 | [-0.067, +0.924] | 0.95 | -1.66% | 56.1 | 50.6% | +5.46% | ⚠️ |
| P3xA2 | 32 | 40.6 | 1.936 | +0.383 | [-0.076, +0.874] | 0.95 | -1.65% | 56.8 | 51.3% | +5.16% | ⚠️ |

*Tanımlayıcı (ÖNERİ DEĞİL): en yüksek expR `P0xA0` (+0.626R) · en düşük expR `P2xA1` (+0.190R) — in-sample.*

## SILVER

| hücre | trade | win% | PF(net) | expR | expR CI95 | P(expR>0) | maxDD | ort.tutma | exposure | net% | zayıf |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| P0xA0 | 34 | 41.2 | 0.935 | +0.002 | [-0.419, +0.428] | 0.49 | -2.88% | 60.4 | 57.9% | -0.64% | ⚠️ |
| P0xA1 | 33 | 42.4 | 1.075 | +0.080 | [-0.356, +0.548] | 0.62 | -3.03% | 62.3 | 57.9% | +0.68% | ⚠️ |
| P0xA2 | 34 | 41.2 | 1.125 | +0.120 | [-0.362, +0.626] | 0.69 | -2.86% | 53.0 | 50.9% | +1.26% | ⚠️ |
| P1xA0 | 32 | 53.1 | 1.065 | +0.070 | [-0.280, +0.403] | 0.64 | -2.20% | 50.1 | 45.3% | +0.51% | ⚠️ |
| P1xA1 | 30 | 53.3 | 1.143 | +0.105 | [-0.274, +0.478] | 0.68 | -2.23% | 52.7 | 44.6% | +1.05% | ⚠️ |
| P1xA2 | 33 | 51.5 | 1.032 | +0.061 | [-0.281, +0.419] | 0.60 | -2.08% | 42.9 | 40.2% | +0.27% | ⚠️ |
| P2xA0 | 34 | 26.5 | 0.731 | -0.045 | [-0.249, +0.187] | 0.31 | -2.79% | 17.5 | 17.4% | -1.40% | ⚠️ |
| P2xA1 | 33 | 30.3 | 1.012 | +0.040 | [-0.188, +0.285] | 0.60 | -2.22% | 17.8 | 17.2% | +0.06% | ⚠️ |
| P2xA2 | 34 | 23.5 | 0.504 | -0.135 | [-0.343, +0.109] | 0.11 | -3.44% | 15.2 | 15.2% | -3.00% | ⚠️ |
| P3xA0 | 34 | 41.2 | 1.084 | +0.081 | [-0.326, +0.494] | 0.64 | -2.38% | 58.9 | 56.5% | +0.71% | ⚠️ |
| P3xA1 | 33 | 42.4 | 1.220 | +0.145 | [-0.276, +0.581] | 0.74 | -2.96% | 60.1 | 56.0% | +1.77% | ⚠️ |
| P3xA2 | 34 | 38.2 | 1.352 | +0.214 | [-0.230, +0.684] | 0.82 | -2.24% | 50.6 | 48.7% | +2.91% | ⚠️ |

*Tanımlayıcı (ÖNERİ DEĞİL): en yüksek expR `P3xA2` (+0.214R) · en düşük expR `P2xA2` (-0.135R) — in-sample.*

## BIST30_BASKET

| hücre | trade | win% | PF(net) | expR | expR CI95 | P(expR>0) | maxDD | ort.tutma | exposure | net% | zayıf |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| P0xA0 | 172 | 38.4 | 0.931 | +0.077 | [-0.127, +0.284] | 0.76 | -8.19% | 56.0 | 24.3% | -1.33% |  |
| P0xA1 | 171 | 36.8 | 0.902 | +0.061 | [-0.143, +0.284] | 0.72 | -9.75% | 54.0 | 23.4% | -1.38% |  |
| P0xA2 | 173 | 38.1 | 1.000 | +0.135 | [-0.096, +0.373] | 0.87 | -9.00% | 52.3 | 22.9% | -1.36% |  |
| P1xA0 | 151 | 51.0 | 0.925 | +0.081 | [-0.096, +0.247] | 0.81 | -5.58% | 55.3 | 21.1% | -0.47% |  |
| P1xA1 | 153 | 53.6 | 0.962 | +0.106 | [-0.053, +0.287] | 0.90 | -6.05% | 51.5 | 20.0% | -0.50% |  |
| P1xA2 | 157 | 52.2 | 0.915 | +0.090 | [-0.079, +0.268] | 0.84 | -6.43% | 48.5 | 19.3% | -0.49% |  |
| P2xA0 | 172 | 23.3 | 0.493 | -0.062 | [-0.164, +0.043] | 0.13 | -5.27% | 14.1 | 6.4% | -0.54% |  |
| P2xA1 | 171 | 26.9 | 0.630 | -0.002 | [-0.114, +0.123] | 0.47 | -5.53% | 14.8 | 6.7% | -0.71% |  |
| P2xA2 | 173 | 24.3 | 0.502 | -0.062 | [-0.164, +0.059] | 0.15 | -5.68% | 14.2 | 6.5% | -0.57% |  |
| P3xA0 | 172 | 33.1 | 0.971 | +0.105 | [-0.092, +0.312] | 0.85 | -6.49% | 52.4 | 22.8% | -0.84% |  |
| P3xA1 | 171 | 29.8 | 0.916 | +0.079 | [-0.122, +0.290] | 0.79 | -8.15% | 49.4 | 21.4% | -0.88% |  |
| P3xA2 | 173 | 31.8 | 1.017 | +0.145 | [-0.071, +0.361] | 0.90 | -7.32% | 48.6 | 21.3% | -0.86% |  |

*Tanımlayıcı (ÖNERİ DEĞİL): en yüksek expR `P3xA2` (+0.145R) · en düşük expR `P2xA2` (-0.062R) — in-sample.*

Sepet equity (eşit-risk, mark-to-market) hücre bazında json'da; P0×A0 Aşama 6 ile birebir.

## Çıkış sebebi karışımları (özet)

Detay `reports/stage7_exit_grid.json → cells.<VARLIK>.<hücre>.metrics.exit_reason_mix`. P1/P2'de `chandelier` yeni reason'dır; P1'de `time_stop` YOKTUR (şartname), P2'de `take_profit` YOKTUR.

## ZORUNLU CAVEAT'LER

- **SEÇİM YOK**: bu grid Aşama 9 girdisidir; hiçbir hücre 'kazanan' ilan edilemez.
- Tüm sayılar **in-sample** (train/valid/test ayrılmadı) ve maliyet dahil.
- Sepet: survivorship bias + risk modülü önizlemesi (Aşama 8 limitleri yok).
- P1 partial'ı aynı barda STOP ile çakışırsa **STOP kazanır, partial YAPILMAZ** (kabul kriteri 2, pesimist). BE/trailing güncellemeleri bar SONUNDA yazılır, sonraki bardan geçerli olur (bar içi sıkılaştırma yok → look-ahead yok).
- P1'de time-stop YOKTUR (şartname gereği): runner chandelier/stop/EOD ile çıkar; uzun tutma süreleri mümkündür.
- Bu rapor yatırım tavsiyesi DEĞİLDİR; geçmiş performans gelecek sonuçların göstergesi değildir.
