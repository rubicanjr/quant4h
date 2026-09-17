# AŞAMA 9 — Walk-forward OOS hükmü (TEST 1 KEZ koşuldu)

*Üretim: 2026-09-17T12:04:38.485979+00:00* · ön-kayıt policy **v1.1** · seçim dosyası `configs/selected_cells.yaml` (TRAIN hash'leriyle DONDURULMUŞ, verdict fazı hash'leri doğrulamadan TEST'i REDDEDER)

**Protokol (kilitli):** SEÇİM YALNIZ TRAIN'de, hücre başına TEK nokta (argmax TRAIN expR; n<50 → seçim YOK, a-priori `P0xA0`) · VALID = sağduyu (expR<0 veya CI üstü<0 → KALDI, **TEST koşulmaz**) · TEST = saf rapor · go/no-go OOS havuzu = **VALID+TEST** · eşikler: n≥100(core)/150(basket), expR>0, CI altı>0, PF≥1.2, maxDD≤%25 (user_decisions.yaml → go_no_go).

## HÜKÜM TABLOSU

| varlık | seçili hücre | seçim yapıldı mı | OOS n | **HÜKÜM** | mod |
|---|---|---|---:|---|---|
| BTC | `P2xA2` | EVET | — | **KALDI** | `watch_only` |
| GOLD | `P0xA0` | HAYIR (TRAIN ZAYIF → a-priori P0xA0) | 16 | **ZAYIF (örneklem)** | `watch_only` |
| SILVER | `P0xA0` | HAYIR (TRAIN ZAYIF → a-priori P0xA0) | 19 | **ZAYIF (örneklem)** | `watch_only` |
| BIST30_BASKET | `P0xA0` | HAYIR (TRAIN ZAYIF → a-priori P0xA0) | — | **KALDI** | `watch_only` |
| **CORE AGREGAT** | (üye hücreleri) | — | 42 | **ZAYIF (örneklem)** | `watch_only` |
| **PORTFÖY-SEPET** | (üye hücreleri) | — | 74 | **KALDI** | `watch_only` |

> GEÇTİ varlıklar **paper/observe modu adaylarıdır** (canlı emir YOK — kapsam dışı). ZAYIF/KALDI → `watch_only`: edge hükmü verilmez.

## BTC — `P2xA2`

Pencereler (used): TRAIN 2017-08-17→2025-11-13 (18045 bar) · VALID 2025-11-27→2026-03-26 (716) · TEST 2026-04-09→2026-09-16 (958) · gap-dışılanan trade: 2

TRAIN seçim: n=175 expR=0.2913 · seçim YAPILDI

| pencere | n | expR | CI95 | PF | win | maxDD(yol) | net |
|---|---:|---:|---|---:|---:|---:|---:|
| VALID | 7 | -0.3207 | [-0.463, -0.173] | 0.000 | 0.0% | -1.31% | -1,401 |
| TEST | — | — | — | — | — | — | — |

VALID sağduyu: ❌ VALID expR -0.3207 < 0 -> KALDI (TEST koşulmaz)
Hüküm gerekçesi: VALID expR -0.3207 < 0 -> KALDI (TEST koşulmaz)
Duyarlılık (TRAIN expR komşuları): `P1xA2` 0.2212, `P3xA2` 0.2739, `P2xA1` 0.254 · seçili +0.2913 − en iyi komşu +0.2739 = +0.0174

## GOLD — `P0xA0`

Pencereler (used): TRAIN 2024-04-24→2025-06-19 (1733 bar) · VALID 2025-07-10→2026-01-02 (716) · TEST 2026-01-26→2026-09-16 (958) · gap-dışılanan trade: 2

TRAIN seçim: n=12 expR=0.4334 · seçim YOK (ZAYIF) — a-priori P0xA0

| pencere | n | expR | CI95 | PF | win | maxDD(yol) | net |
|---|---:|---:|---|---:|---:|---:|---:|
| VALID | 6 | +1.3579 | [+0.162, +2.553] | 6.951 | 66.7% | -0.66% | +3,993 |
| TEST | 10 | +0.3430 | [-0.509, +1.371] | 1.573 | 40.0% | -0.81% | +1,376 |
| **OOS (V+T)** | 16 | +0.7236 | [-0.011, +1.526] | 2.747 | 50.0% | -0.81% | +5,370 |

VALID sağduyu: ✅ VALID sağduyu GEÇTİ
Hüküm gerekçesi: OOS trade 16 < min 100 -> edge hükmü VERİLMEZ
Monte Carlo (OOS dizisi, B=1000, seed=42): maxDD p05/p50/p95 = %-2.5/%-1.2/%-0.5 · P(maxDD>%25)=0.00 · P(ruin<%50 equity)=0.00
Duyarlılık (TRAIN expR komşuları): `P1xA0` 0.5, `P0xA1` 0.3052 · seçili +0.4334 − en iyi komşu +0.5000 = -0.0666

## SILVER — `P0xA0`

Pencereler (used): TRAIN 2024-04-24→2025-06-19 (1733 bar) · VALID 2025-07-10→2026-01-02 (716) · TEST 2026-01-26→2026-09-16 (958) · gap-dışılanan trade: 2

TRAIN seçim: n=13 expR=-0.3529 · seçim YOK (ZAYIF) — a-priori P0xA0

| pencere | n | expR | CI95 | PF | win | maxDD(yol) | net |
|---|---:|---:|---|---:|---:|---:|---:|
| VALID | 8 | +0.9021 | [-0.123, +1.918] | 3.144 | 62.5% | -1.07% | +3,408 |
| TEST | 11 | -0.2790 | [-0.860, +0.302] | 0.530 | 36.4% | -2.27% | -1,690 |
| **OOS (V+T)** | 19 | +0.2183 | [-0.368, +0.886] | 1.331 | 47.4% | -2.27% | +1,718 |

VALID sağduyu: ✅ VALID sağduyu GEÇTİ
Hüküm gerekçesi: OOS trade 19 < min 100 -> edge hükmü VERİLMEZ
Monte Carlo (OOS dizisi, B=1000, seed=42): maxDD p05/p50/p95 = %-4.5/%-2.1/%-1.0 · P(maxDD>%25)=0.00 · P(ruin<%50 equity)=0.00
Duyarlılık (TRAIN expR komşuları): `P1xA0` -0.2725, `P0xA1` -0.3914 · seçili -0.3529 − en iyi komşu -0.2725 = -0.0804

## BIST30_BASKET — `P0xA0`

Pencereler (used): TRAIN 2023-10-27→2024-09-13 (437 bar) · VALID 2024-11-14→2025-08-29 (395) · TEST 2025-10-30→2026-09-16 (436) · gap-dışılanan trade: 14

TRAIN seçim: n=0 expR=None · seçim YOK (ZAYIF) — a-priori P0xA0

| pencere | n | expR | CI95 | PF | win | maxDD(yol) | net |
|---|---:|---:|---|---:|---:|---:|---:|
| VALID | 74 | -0.0569 | [-0.332, +0.238] | 0.701 | 39.2% | -10.35% | -6,904 |
| TEST | — | — | — | — | — | — | — |

VALID sağduyu: ❌ VALID expR -0.0569 < 0 -> KALDI (TEST koşulmaz)
Hüküm gerekçesi: VALID expR -0.0569 < 0 -> KALDI (TEST koşulmaz)
Duyarlılık (TRAIN expR komşuları): `P1xA0` —, `P0xA1` — · seçili hücre TRAIN expR yok

## PORTFÖY DÜZEYİ

**CORE AGREGAT (BTC+GOLD+SILVER OOS birleşimi)**: 42 | +0.3210 | [-0.111, +0.781] | 1.588 | 40.5% | -3.60% | +5,686 
  hüküm **ZAYIF (örneklem)** (`watch_only`) — OOS trade 42 < min 100 -> edge hükmü VERİLMEZ; NOT: BTC VALID sağduyudan KALDI (TEST koşulmadı) — agregaya yalnız VALID trade'leriyle dahil; üye hükmü agregatla YUMUŞATILAMAZ
  MC: maxDD p50 %-2.6 · P(maxDD>%25)=0.00 · P(ruin)=0.00

**SEPET (BIST30 OOS)**: 74 | -0.0569 | [-0.332, +0.238] | 0.701 | 39.2% | -10.35% | -6,904 
  hüküm **KALDI** (`watch_only`) — üye VARLIK hükmü KALDI (VALID sağduyu başarısız, TEST koşulmadı); havuz yalnız VALID; OOS trade 74 < min 150 -> edge hükmü VERİLMEZ
  MC: maxDD p50 %-9.2 · P(maxDD>%25)=0.00 · P(ruin)=0.00

## CAVEAT'LER (zorunlu)

- TEK fold (ön-kayıtlı split v1.1); çok katlı walk-fold Aşama 9 sonrası genişletme adayıdır.
- Trade atfı GİRİŞ zamanına göre; pencere dışında kapanan çıkışlar giriş penceresine sayılır.
- Purge/embargo boşluğuna düşen girişler hiçbir pencereye sayılmadı (gap_excluded_trades).
- Sepet survivorship bias taşır; metals feed'inde düşük-kalite pencere (2026-01-26..02-06) TEST aralığı dışında.
- TEST bu teslimatta 1 KEZ koşuldu; yeniden koşum onay gerektirir.
- ZAYIF hükümler edge kanıtı DEĞİLDİR; watch_only = izle, edge iddiası YOK.

*Bu rapor yatırım tavsiyesi DEĞİLDİR; tüm ölçümler ön-kayıtlı pencerelerde ve maliyet dahil yapılmıştır. Geçmiş performans geleceğin göstergesi değildir.*
