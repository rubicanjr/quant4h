# AŞAMA 8 — Risk katmanı: tavanlı vs tavansız portföy simülasyonu

*Üretim: 2026-09-17T10:17:37.848872+00:00* · sinyal **CAPPED** · çıkış **P0×A0 KİLİTLİ** (seçim Aşama 9) · risk **balanced** (%0.50/işlem) · başlangıç 100,000 · t+1 icra · maliyet çift taraf · **tavanlar YALNIZ girişte** (çıkışlara dokunmaz)

> ⚠️ **IN-SAMPLE** — bu rapor karar üretmez; nihai hüküm Aşama 9 OOS + `go_no_go` eşikleridir. Sepet survivorship bias taşır. ORTAK equity semantiği: boyutlama her girişte GÜNCEL realized equity ile yapılır (Aşama 6'nın varlık-başına-ayrı-equity koşusundan milimetrik farklar beklenir; expR ve trade sayıları equity'den bağımsızdır ve regresyonla kilitlidir).

✅ **Regresyon:** TAVANSIZ koşu Aşama 7 P0×A0 hücreleriyle birebir (trade sayıları + expR; BTC/GOLD/SILVER/BASKET) → simülatör motorla eşdeğer.

## 1) Bağlayıcı tavanlar (kullanıcı direktifi 2026-09-17 · balanced)

| tavan | değer |
|---|---|
| maks eşzamanlı (TOPLAM) | 6 |
| BTC / GOLD / SILVER eşzamanlı | 2 / 1 / 1 |
| BIST30 sepet eşzamanlı | 3 |
| kıymetli maden birleşik ISI | ≤ 1 × risk_per_trade (%0.50) — TEK kova (onaylı karar) |
| BIST30 sepet birleşik ISI | ≤ 3 × risk_per_trade (%1.50) |
| hisse başı ISI | ≤ 1 × risk_per_trade (%0.50) |
| banka sektörü eşzamanlı | ≤ 2 (donmuş üniversalden: sector == 'banka') |
| günlük / haftalık kayıp limiti | %2 / %5 (RiskProfile — realized P&L bazlı, fail-closed) |
| ardışık kayıp freni | 4 ardışık kayıp → 20 bar yeni giriş yok (varlık bazında, L+S ortak) |

## 2) TAVANLI vs TAVANSIZ (in-sample, portföy düzeyi)

| ölçü | TAVANSIZ | TAVANLI | fark |
|---|---:|---:|---:|
| trade sayısı | 423 | 247 | -176.0000 |
| net getiri (mtm eğri) | 0.1637 | 0.1768 | +0.0131 |
| max DD (mtm eğri) | -0.1766 | -0.0776 | +0.0990 |
| exposure (bar oranı) | 0.7021 | 0.6849 | -0.0172 |

### Varlık bazında (TAVANLI koşu; expR R-bazlı)

| grup | trade | win% | PF(net) | expR | expR CI95 | P(expR>0) | net P&L | zayıf |
|---|---:|---:|---:|---:|---|---:|---:|---|
| BTC | 177 | 39.6 | 1.273 | +0.199 | [-0.015, +0.405] | 0.97 | +13,731 |  |
| GOLD | 17 | 58.8 | 2.247 | +0.476 | [-0.161, +1.148] | 0.93 | +3,968 | ⚠️ |
| SILVER | 18 | 44.4 | 0.959 | +0.018 | [-0.590, +0.658] | 0.51 | -250 | ⚠️ |
| BIST30_BASKET | 35 | 45.7 | 1.024 | +0.126 | [-0.263, +0.534] | 0.72 | +233 | ⚠️ |

## 3) Tavan tipi başına REDDEDİLEN giriş (tavanlı koşu)

| tavan tipi | red |
|---|---:|
| `basket_concurrent` | 137 |
| `metals_bucket_heat` | 29 |
| `loss_streak_brake` | 10 |
| `no_valid_stop` | 0 |
| `stop_geometry` | 0 |
| `not_tradable` | 0 |
| `invalid_price` | 0 |
| `daily_loss_limit` | 0 |
| `weekly_loss_limit` | 0 |
| `total_concurrent` | 0 |
| `per_asset_concurrent` | 0 |
| `bank_sector` | 0 |
| `basket_heat` | 0 |
| `per_stock_heat` | 0 |

**Tepe değerler — TAVANLI:** maks eşzamanlı 5 (tavan 6) · metals ısısı %0.50 (tavan %0.50) · basket ısısı %1.50 (tavan %1.50) · toplam ısı %2.50 · banka eşzamanlı 1 (tavan 2)

**Tepe değerler — TAVANSIZ:** maks eşzamanlı 28 · metals %1.00 · basket %13.00 · toplam %14.00 · banka 5

## 4) EK (APPENDIX) — BIST30 hisse bazlı (tavanlı; tanı amaçlı, kabul kriteri 6)

| hisse | trade | win% | PF | expR | zayıf |
|---|---:|---:|---:|---:|---|
| ASELS | 2 | 50 | 9.52 | +1.55 | ⚠️ |
| ASTOR | 1 | 100 | inf | +3.00 | ⚠️ |
| BIMAS | 3 | 33 | 0.27 | -0.44 | ⚠️ |
| EKGYO | 3 | 67 | 1.38 | +0.22 | ⚠️ |
| ENKAI | 3 | 33 | 0.62 | -0.04 | ⚠️ |
| EREGL | 1 | 100 | inf | +0.66 | ⚠️ |
| GARAN | 1 | 100 | inf | +1.08 | ⚠️ |
| ISCTR | 2 | 50 | 1.15 | +0.22 | ⚠️ |
| KCHOL | 1 | 0 | 0.00 | -0.26 | ⚠️ |
| KRDMD | 2 | 0 | 0.00 | -0.14 | ⚠️ |
| MGROS | 2 | 50 | 0.68 | -0.05 | ⚠️ |
| PETKM | 2 | 100 | inf | +0.81 | ⚠️ |
| PGSUS | 2 | 50 | 0.15 | -0.41 | ⚠️ |
| SAHOL | 1 | 100 | inf | +0.35 | ⚠️ |
| SASA | 1 | 0 | 0.00 | -0.57 | ⚠️ |
| SISE | 1 | 0 | 0.00 | -1.00 | ⚠️ |
| TAVHL | 1 | 100 | inf | +0.16 | ⚠️ |
| THYAO | 1 | 0 | 0.00 | -1.00 | ⚠️ |
| TOASO | 2 | 0 | 0.00 | -1.00 | ⚠️ |
| TTKOM | 1 | 0 | 0.00 | -1.00 | ⚠️ |
| TUPRS | 1 | 100 | inf | +2.82 | ⚠️ |
| YKBNK | 1 | 0 | 0.00 | -1.00 | ⚠️ |

## ZORUNLU CAVEAT'LER

- **SEÇİM YOK**: P0×A0 Aşama 9'a kadar kilitli; bu rapor risk KATMANININ etkisini ölçer, profil/anchor seçmez.
- Tüm sayılar IN-SAMPLE ve maliyet dahil; go/no-go Aşama 9 OOS + `user_decisions.yaml → go_no_go` eşikleriyle.
- Günlük/haftalık limitler REALIZED P&L bazlıdır (unrealized dahil DEĞİL) — belgelenmiş seçim; mtm bazlı limite geçiş ayrı onay gerektirir.
- `max_correlation` ayrıca ZORLANMADI: metals tek-kova ısısı (≤ %0.5 birleşik) GOLD|SILVER'i zaten sınırlar; günlük bazlı korelasyon limiti Aşama 9'da ele alınacak.
- Stage 0 `RiskProfile.max_open_positions=3` bu şartnameyle SUPERSEDE edildi (toplam 6 · kullanıcı direktifi 2026-09-17); PROGRESS'e işlendi.
- Bu rapor yatırım tavsiyesi DEĞİLDİR; geçmiş performans geleceğin göstergesi değildir.
