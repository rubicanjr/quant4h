# AŞAMA 6 — Baseline Backtest Raporu

*Üretim: 2026-09-16T15:14:20 UTC* · timeframe **4h** · risk profili **balanced** (işlem başı **0.50%**, kaldıraç ≤ 2.0) · başlangıç sermayesi 100,000

**Primary akış: `capped`** · Sinyaller CAPPED akıştan alınır (pozisyon vekili + 90 bar zorunlu time-stop). STRICT akış yalnız tanısal tabloda verilir; COOLDOWN_ONLY backtest EDİLMEZ.

## ÇIKIŞ MOTORU

- Dondurulmuş yapısal stop (Aşama 3) · time-stop **90 bar** · basit TP **3.0R**
- Aynı barda çakışma → **stop** öncelikli (PESİMİST)
- Aday kümeleri: time-stop `[60, 90, 120]`, TP `[2.0, 3.0, 4.0]` → **yalnızca Aşama 9**; `tuned_now=False`
- Doldurma: giriş `open[t+1]`; stop `open < stop` ise open'dan değilse stop'tan; TP `open > tp` ise open'dan değilse tp'den; time-stop kapanıştan
- Maliyet: komisyon + yarım spread + slippage, **iki tarafa da**
- **Geçerli stopu olmayan pozisyon ASLA açılmaz** (H35 kilidi)

> ⚠️ **RİSK MODÜLÜ ÖNCESİ ÖNİZLEME — portföy agregasyonu ve risk limitleri Aşama 8'de. Buradaki toplam eşit-risk varsayımıyla basit toplamdır; korelasyon/ısı/sektör tavanı UYGULANMAMIŞTIR.**

## 0) ANA BULGU — dürüst özet

Bu bir **baseline**'dır ve sonucu net söylemek gerekir:

1. **Hiçbir varlık buy&hold'u geçemedi; çoğu VASTLY geride.** Sebep bir hata değil, ölçülen dönemin (2024-2026) şiddetli boğa piyasası olması ve sistemin **%0,5 risk/işlem + düşük maruziyet** ile çalışmasıdır. Buy&hold tam maruziyet demektir; bu sistem barların yalnızca bir kısmında pozisyondadır.
2. **Expectancy pozitif ama güven aralığı geniş.** GOLD'da CI 0'ı içermiyor (P(expR>0)≈0.99) ama yalnız 30 trade; SILVER'da CI 0'ı içeriyor (P≈0.49) → **ayırt edilemez**. BTC'de 187 trade ile expR≈+0.21.
3. **Maliyet sonucu değiştiriyor ama tersine çevirmiyor** (core varlıklarda). Sepette maliyet 10.348 birim ve net getiri ≈ 0 → maliyet ÖNCESİ de sonrası da anlamlı pozitif değil.
4. **Trade sayıları ÇOK düşük** (hisse başına medyan 6). Kabul kriteri 6 gereği hisse bazlı sonuçlar anlamsız; ana karar BASKET agregasyonundan okunur ve o da ≈ başabaş.

> **Sonuç:** bu parametre setiyle sistem **para kazanıyor diyemeyiz**. Kaybediyor da diyemeyiz — örneklem yetersiz. Aşama 7 (esnek kâr alma) ve Aşama 9 (out-of-sample parametre seçimi + robustluk) olmadan bu tablo üzerinden HİÇBİR karar verilmemelidir.

## 1) CORE VARLIKLAR

| Varlık | maliyet (bp gidiş-dönüş) | trade (L/S) | win rate | PF (net) | expectancy (R) | ort. tutma (bar) | max DD | **net getiri** | **BH net** | maliyet toplamı | zayıf? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **BTC** | 31 | 187 (100/87) | 40.1% | 1.307 | 0.206 | 59.6 | -7.05% | **15.47%** | **1636.82%** | 4,904 | hayır |
| **GOLD** | 20 | 30 (23/7) | 56.7% | 2.673 | 0.626 | 67.8 | -2.12% | **8.66%** | **86.32%** | 895 | ⚠️ EVET |
| **SILVER** | 20 | 34 (26/8) | 41.2% | 0.935 | 0.002 | 60.4 | -2.88% | **-0.64%** | **136.61%** | 616 | ⚠️ EVET |

### Maliyet satırı (kabul kriteri 7)

| Varlık | toplam maliyet | maliyetli net | **maliyetsiz brüt** | fark |
|---|---:|---:|---:|---:|
| **BTC** | 4,904 | 15.47% | 20.37% | 4.90% |
| **GOLD** | 895 | 8.66% | 9.55% | 0.90% |
| **SILVER** | 616 | -0.64% | -0.03% | 0.62% |

### Bootstrap CI (trade < 100 ise ZORUNLU; karşılaştırılabilirlik için HER varlıkta hesaplanır)

| Varlık | trade | expectancy R [CI95] | P(expectancy>0) | win rate [CI95] | bayrak |
|---|---:|---|---:|---|---|
| **BTC** | 187 | [0.006, 0.422] | 0.98 | [0.35, 0.49] | CI 0'ı İÇERMİYOR · — |
| **GOLD** | 30 | [0.093, 1.194] | 0.99 | [0.40, 0.73] | CI 0'ı İÇERMİYOR · ⚠️ İSTATİSTİKSEL ZAYIF |
| **SILVER** | 34 | [-0.419, 0.428] | 0.49 | [0.24, 0.59] | CI 0'ı içeriyor · ⚠️ İSTATİSTİKSEL ZAYIF |

### Çıkış sebebi karışımı

| Varlık | stop | take_profit | time_stop | end_of_data | long | short |
|---|---:|---:|---:|---:|---:|---:|
| **BTC** | 80 | 27 | 80 | 0 | 100 | 87 |
| **GOLD** | 7 | 6 | 16 | 1 | 23 | 7 |
| **SILVER** | 17 | 1 | 16 | 0 | 26 | 8 |

## 2) BIST30 SEPETİ — ANA SONUÇ (BASKET AGREGASYONU)

> Agregasyon: eşit-risk: her sinyal aynı risk bütçesi; basket getirisi = hisse başına % getirilerin ORTALAMASI

| ölçü | değer |
|---|---|
| hisse sayısı | 28 |
| **toplam trade** | **172** |
| win rate | 38.4% |
| profit factor (net) | 0.931 |
| expectancy (R) | 0.077 |
| ort. tutma (bar) | 56.0 |
| max DD (trade bazlı) | -8.19% |
| **basket equity net getiri** (eşit-risk, günlük yeniden dengelenmiş, açık pozisyonlar mark-to-market) | **-0.14%** |
| trade bazlı kümülatif net (kapanmış trade'ler, bileşiksiz) | -1.33% |
| basket max DD (bar bazlı) | -0.78% |
| pencere | 2023-10-27 → 2026-09-16 |
| toplam maliyet | 10,348 |
| istatistiksel zayıf mı | hayır |
| expectancy R [CI95] | [-0.133, 0.283] |
| P(expectancy > 0) | 0.762 |
| çıkış sebepleri | {'stop': 85, 'time_stop': 61, 'take_profit': 20, 'end_of_data': 6} |

![basket equity](reports/figures/equity_bist30_basket.png)

## 3) EK (APPENDIX) — HİSSE BAZLI TABLO

> Kabul kriteri 6: hisse başına ~6 trade **istatistiksel olarak anlamsızdır**. Bu tablo yalnızca tanı amaçlıdır; karar BASKET agregasyonuna göre verilir.

| Hisse | trade | win % | PF | exp R | ort. tutma | net % | BH net % | zayıf |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **AEFES** | 4 | 50% | 1.11 | 0.19 | 58 | 0.1% | 74.9% | ⚠️ |
| **AKBNK** | 8 | 25% | 0.31 | -0.45 | 47 | -2.2% | 111.6% | ⚠️ |
| **ASELS** | 8 | 62% | 4.27 | 1.25 | 61 | 4.6% | 791.9% | ⚠️ |
| **ASTOR** | 7 | 43% | 2.27 | 0.81 | 55 | 2.4% | 107.9% | ⚠️ |
| **BIMAS** | 8 | 62% | 1.50 | 0.36 | 71 | 0.9% | 193.4% | ⚠️ |
| **EKGYO** | 8 | 38% | 0.75 | -0.06 | 56 | -0.7% | 175.3% | ⚠️ |
| **ENKAI** | 7 | 43% | 0.79 | 0.03 | 71 | -0.3% | 167.9% | ⚠️ |
| **EREGL** | 9 | 44% | 1.54 | 0.53 | 44 | 1.6% | 87.6% | ⚠️ |
| **FROTO** | 3 | 67% | 3.83 | 1.14 | 68 | 1.5% | -12.4% | ⚠️ |
| **GARAN** | 5 | 40% | 0.98 | 0.11 | 62 | -0.0% | 152.7% | ⚠️ |
| **GUBRF** | 7 | 43% | 0.81 | -0.03 | 53 | -0.5% | 23.0% | ⚠️ |
| **ISCTR** | 6 | 33% | 0.75 | -0.05 | 56 | -0.5% | 38.1% | ⚠️ |
| **KCHOL** | 6 | 33% | 0.93 | 0.10 | 53 | -0.1% | 49.0% | ⚠️ |
| **KRDMD** | 7 | 43% | 1.77 | 0.40 | 74 | 1.0% | 63.9% | ⚠️ |
| **MGROS** | 6 | 50% | 1.56 | 0.51 | 51 | 1.1% | 44.4% | ⚠️ |
| **PETKM** | 4 | 50% | 0.80 | 0.03 | 70 | -0.2% | 3.0% | ⚠️ |
| **PGSUS** | 4 | 25% | 0.05 | -0.70 | 40 | -1.7% | 0.3% | ⚠️ |
| **SAHOL** | 6 | 17% | 0.05 | -0.59 | 57 | -2.1% | 57.3% | ⚠️ |
| **SASA** | 3 | 0% | 0.00 | -0.86 | 51 | -1.3% | -53.6% | ⚠️ |
| **SISE** | 6 | 17% | 0.20 | -0.54 | 55 | -1.9% | -21.2% | ⚠️ |
| **TAVHL** | 5 | 40% | 0.21 | -0.44 | 60 | -1.4% | 111.3% | ⚠️ |
| **TCELL** | 7 | 29% | 0.47 | -0.30 | 42 | -1.5% | 89.1% | ⚠️ |
| **THYAO** | 7 | 14% | 0.09 | -0.66 | 49 | -2.8% | 30.0% | ⚠️ |
| **TOASO** | 7 | 29% | 1.04 | 0.16 | 37 | 0.1% | 7.4% | ⚠️ |
| **TTKOM** | 5 | 20% | 0.62 | -0.21 | 62 | -0.9% | 155.5% | ⚠️ |
| **TUPRS** | 5 | 80% | 7.01 | 1.49 | 67 | 3.4% | 192.0% | ⚠️ |
| **VAKBN** | 6 | 50% | 1.10 | 0.17 | 59 | 0.2% | 85.4% | ⚠️ |
| **YKBNK** | 8 | 25% | 0.12 | -0.56 | 52 | -2.7% | 82.6% | ⚠️ |

## 4) GRAFİKLER ve TRADE LİSTELERİ

- `BTC`: equity `reports/figures/equity_BTC_long.png` · trade listesi `reports/trades_BTC.csv`
- `GOLD`: equity `reports/figures/equity_GOLD_long.png` · trade listesi `reports/trades_GOLD.csv`
- `SILVER`: equity `reports/figures/equity_SILVER_long.png` · trade listesi `reports/trades_SILVER.csv`
- BIST30 basket: equity `reports/figures/equity_bist30_basket.png`

## ZORUNLU CAVEAT'LER

- **Bu bir baseline'dır.** Parametreler (n=10, m=1.0, Donchian 20, buffer 1.0, time-stop 90, TP 3R, cooldown 3) **VARSAYILANDIR ve OPTİMİZE EDİLMEMİŞTİR**. Seçim Aşama 9'da, yalnızca core varlıklar üzerinde, out-of-sample yapılacak.
- **Sinyal akışı CAPPED varyantıdır.** Pozisyon vekili (stop ihlali + 90 bar time-stop) gerçek çıkış motoruyla değiştirildiğinde sayılar DEĞİŞECEKTİR.
- **Portföy agregasyonu bir ÖNİZLEMEDİR.** Korelasyon limiti, bucket ısısı, sektör tavanı ve maks eşzamanlı pozisyon Aşama 8'de uygulanacak. GOLD|SILVER korelasyonu +0.77 olduğu için ikisi TEK risk kovası sayılacak; buradaki basit toplam o etkiyi İÇERMEZ.
- **Train/valid/test ayrımı bu raporda UYGULANMADI.** Sayılar tüm örneklem üzerindedir ve bu yüzden **in-sample**'dır. Aşama 9'da ön-kayıtlı split'lerle (`configs/splits_preregistered.yaml`) OOS ölçümü yapılacak.
- BIST30 sepeti **survivorship bias** taşır → sonuçlar yukarı yönlü çarpıktır.
- Metallerde roll **kesin tespit edilemediği** için getiri serisi ön-ay fiyatlarına dayanır; roll kaynaklı bias olabilir.
- Trade sayısı < 100 olan HER satır `İSTATİSTİKSEL ZAYIF` bayrağı taşır ve bootstrap CI olmadan YORUMLANMAMALIDIR.
- Geçmiş performans gelecek sonuçların göstergesi değildir. Bu rapor yatırım tavsiyesi DEĞİLDİR.
