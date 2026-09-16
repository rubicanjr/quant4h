# AŞAMA 2 — Piyasa Rejimi ve XU030 Bağlam Filtresi Raporu

*Üretim: 2026-09-16T13:19:38 UTC* · timeframe **4h**

## REJİM POLİTİKASI (sadelik kuralı)

- **Trend filtresi:** EMA200 yönü (close vs EMA + ATR-normalize eğim)
- **Volatilite filtresi:** ATR(14) yüzdelik dilimi, 500 bar geriye dönük
- **Durumlar:** trend_up|trend_down|range × vol_high|vol_normal|vol_low = 6 durum
- Long izni: `['trend_up']` · Short izni: `['trend_down']` · ATR yüzdelik tavanı: `0.95`
- Isınma: ilk `500` bar etiketsiz · `fail_closed=True` → **rejim bilinmiyorsa sinyal YOK**
- **İPTAL EDİLEN yöntemler:** ADX, Hurst, HMM, Choppiness, Bollinger width, Ichimoku, Supertrend, Keltner (config'te bile tutulmuyor: kullanılmayan parametre = overfitting yüzeyi)

## XU030 BAĞLAM FİLTRESİ (KARAR 4)

- **Kural:** BIST30 hisseleri LONG-ONLY; yeni long yalnızca XU030 4H kapanış > EMA200 iken. Endeks EMA200 altındayken YENİ sinyal açılmaz; MEVCUT pozisyonlar kendi stoplarıyla yönetilir (zorla kapatma YOK).
- **Core varlıklar:** BTC/GOLD/SILVER long+short, filtreye TABİ DEĞİL
- **Anti look-ahead:** karar anı = bar_open - 1 bar; yalnızca KAPANMIŞ XU030 barı kullanılır
- **Fail-closed:** `True` · maks bağlam yaşı `120` saat · EMA periyodu `200`

## ZORUNLU CAVEAT'LER

- Rejim etiketi bir **tahmin**dir, kesinlik değildir; geçmiş rejim dağılımı gelecekteki dağılımı garanti etmez.
- `range` rejiminde **yeni sinyal üretilmez**. Bu, fırsat kaçırmak pahasına yanlış sinyali azaltmayı seçen bilinçli bir tercihtir.
- Isınma döneminde (ilk ~500 bar) etiket YOKTUR; bu barlar backtest'te kullanılamaz. Metallerde bu, ~2.4 yıllık geçmişin %14'üdür.
- **SURVIVORSHIP BIAS:** hisse sepeti yalnızca BUGÜN BIST30'da olan 28 hisseyi içerir. Rejim dağılımı da bu çarpık örnekleme aittir.
- XU030 filtresi long'ları bastırdığında **mevcut pozisyonlar zorla kapatılmaz**; bu bir tasarım kararıdır ve düşen piyasada taşıma riskini azaltmaz.

## CORE VARLIKLAR

| Varlık | rol | bar | işlem-uygun | etiketli | etiketsiz % | trend_up | trend_down | range | vol_high | vol_normal | vol_low | long OK | short OK |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **BTC** | core_tradable | 19888 | 19887 | 19388 | %2.5 | 9024 | 8358 | 2006 | 4923 | 8024 | 6441 | 8489 | 7759 |
| **GOLD** | core_tradable | 3606 | 3575 | 3106 | %13.9 | 2092 | 692 | 322 | 812 | 1490 | 804 | 1932 | 678 |
| **SILVER** | core_tradable | 3606 | 3575 | 3106 | %13.9 | 1846 | 851 | 409 | 901 | 1147 | 1058 | 1615 | 803 |
| **BIST30** | context_filter_source | 2158 | 1436 | 1658 | %23.2 | 988 | 420 | 250 | 417 | 797 | 444 | 953 | 384 |
| **XU030** | context_filter_source | 2158 | 2158 | 1658 | %23.2 | 988 | 420 | 250 | 417 | 797 | 444 | 953 | 384 |

## BIST30 HİSSE SEPETİ — REJİM DAĞILIMI VE FİLTRE SONUCU

| Hisse | sektör | bar | işlem-uygun | etiketli | trend_up | trend_down | range | vol_high | rejim long | XU030 izin | **FINAL long** | final % |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **AEFES** | içecek | 2158 | 1430 | 1658 | 690 | 767 | 201 | 435 | 640 | 1410 | **364** | %16.9 |
| **AKBNK** | banka | 2158 | 1430 | 1658 | 817 | 638 | 203 | 323 | 804 | 1410 | **496** | %23.0 |
| **ASELS** | elektronik/savunma | 2158 | 1430 | 1658 | 1278 | 227 | 153 | 467 | 1175 | 1410 | **595** | %27.6 |
| **ASTOR** | elektrik ekipman | 2157 | 1432 | 1657 | 886 | 625 | 146 | 521 | 759 | 1409 | **437** | %20.3 |
| **BIMAS** | perakende | 2158 | 1419 | 1658 | 1123 | 294 | 241 | 394 | 1056 | 1410 | **555** | %25.7 |
| **EKGYO** | GYO | 2158 | 1432 | 1658 | 1031 | 405 | 222 | 348 | 1011 | 1410 | **530** | %24.6 |
| **ENKAI** | inşaat | 2158 | 1422 | 1658 | 1186 | 278 | 194 | 528 | 1095 | 1410 | **519** | %24.1 |
| **EREGL** | demir-çelik | 2158 | 1430 | 1658 | 852 | 581 | 225 | 546 | 779 | 1410 | **407** | %18.9 |
| **FROTO** | otomotiv | 2157 | 1424 | 1657 | 457 | 991 | 209 | 345 | 404 | 1409 | **215** | %10.0 |
| **GARAN** | banka | 2158 | 1430 | 1658 | 922 | 517 | 219 | 349 | 892 | 1410 | **503** | %23.3 |
| **GUBRF** | kimya/gübre | 2158 | 1436 | 1658 | 1188 | 302 | 168 | 423 | 1156 | 1410 | **550** | %25.5 |
| **ISCTR** | banka | 2157 | 1430 | 1657 | 694 | 754 | 209 | 335 | 690 | 1409 | **446** | %20.7 |
| **KCHOL** | holding | 2158 | 1430 | 1658 | 641 | 717 | 300 | 317 | 639 | 1410 | **401** | %18.6 |
| **KRDMD** | demir-çelik | 2158 | 1434 | 1658 | 951 | 443 | 264 | 494 | 866 | 1410 | **513** | %23.8 |
| **MGROS** | perakende | 2158 | 1426 | 1658 | 797 | 676 | 185 | 392 | 764 | 1410 | **461** | %21.4 |
| **PETKM** | petrokimya | 2158 | 1436 | 1658 | 592 | 814 | 252 | 500 | 525 | 1410 | **283** | %13.1 |
| **PGSUS** | havacılık | 2157 | 1436 | 1657 | 522 | 899 | 236 | 338 | 477 | 1409 | **217** | %10.1 |
| **SAHOL** | holding | 2158 | 1430 | 1658 | 718 | 706 | 234 | 346 | 701 | 1410 | **451** | %20.9 |
| **SASA** | tekstil/kimya | 2158 | 1436 | 1658 | 265 | 1191 | 202 | 475 | 205 | 1410 | **102** | %4.7 |
| **SISE** | cam | 2157 | 1430 | 1657 | 537 | 850 | 270 | 591 | 474 | 1409 | **309** | %14.3 |
| **TAVHL** | havacılık/havalimanı | 2157 | 1434 | 1657 | 708 | 684 | 265 | 393 | 688 | 1409 | **406** | %18.8 |
| **TCELL** | telekom | 2157 | 1428 | 1657 | 704 | 588 | 365 | 347 | 687 | 1409 | **390** | %18.1 |
| **THYAO** | havacılık | 2158 | 1432 | 1658 | 693 | 706 | 259 | 421 | 676 | 1410 | **389** | %18.0 |
| **TOASO** | otomotiv | 2158 | 1430 | 1658 | 722 | 718 | 218 | 425 | 693 | 1410 | **399** | %18.5 |
| **TTKOM** | telekom | 2157 | 1436 | 1657 | 838 | 583 | 236 | 369 | 813 | 1409 | **388** | %18.0 |
| **TUPRS** | enerji/rafineri | 2158 | 1426 | 1658 | 830 | 672 | 156 | 513 | 766 | 1410 | **410** | %19.0 |
| **VAKBN** | banka | 2158 | 1436 | 1658 | 915 | 502 | 241 | 354 | 881 | 1410 | **484** | %22.4 |
| **YKBNK** | banka | 2158 | 1434 | 1658 | 821 | 552 | 285 | 315 | 816 | 1410 | **500** | %23.2 |
| **TOPLAM** | | 60416 | | | 22378 | 17680 | 6358 | | 21132 | 39472 | **11720** | %19.4 |

### XU030 filtresi ret sebepleri (sepet toplamı)

| Sebep | bar | anlamı |
|---|---:|---|
| `context_ok` | 39472 | XU030 EMA200 ÜSTÜNDE → long'a izin var |
| `context_below_ema200` | 15260 | XU030 EMA200 ALTINDA → **yeni long YOK** (mevcut pozisyon stopla yönetilir) |
| `context_warmup` | 5572 | XU030 EMA200 henüz hazır değil → fail-closed, long YOK |
| `context_stale` | 84 | en son kapanmış XU030 barı çok eski → fail-closed, long YOK |
| `context_missing` | 28 | karar anından önce kapanmış XU030 barı yok → fail-closed, long YOK |

## FİNAL LONG İZNİNİN BİLEŞİMİ

```
long_final_ok = long_regime_ok      # trend_up VE ATR yüzdeliği <= tavan
              AND longs_allowed      # XU030 4H kapanış > EMA200 (KAPANMIŞ bar, fail-closed)
              AND NOT non_tradable   # kesinti / ince açılış barı / henüz oluşuyor / kurumsal aksiyon
              AND return_valid       # boşluğu veya ex-date'i atlayan getiri DEĞİL
```

> Short sinyali hisse sepetinde **politika gereği kapalıdır** (LONG-ONLY). Core varlıklarda `short_regime_ok` yalnızca `trend_down` rejiminde açılır ve XU030 filtresine tabi değildir.
