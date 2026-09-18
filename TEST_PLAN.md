# TEST_PLAN.md — pine/quant4h_viz.pine + export_viz_payload.py (M9b)

*Statü: **UNTESTED-VIZ** — Pine görselleştirme katmanı OTOMATİK test kapsamında DEĞİLDİR (TradingView derlemesi/paritesi bu repoda doğrulanamaz). Bu belge manuel doğrulama planıdır. **Doğruluk kaynağı DEĞİLDİR**; doğruluk kaynağı her zaman Python pipeline'ıdır (`reports/*.md`, `data/processed/*`, `configs/*`).*

## 0) Kapsam ve sınırlar (bağlayıcı)

- `pine/quant4h_viz.pine` **yalnız `indicator()`**: Python'un ihraç ettiği marker/seviyeleri ÇİZER; hiçbir değeri YENİDEN HESAPLAMAZ.
- **`strategy()` YOK · `alert()`/`alertcondition()` YOK · icra/emir temsili YOK** (icra `open[t+1]` grafikte gösterilmez; marker'lar KARAR barının kapanışındadır).
- watch_only: trade yok, emir yok, tavsiye yok (Aşama 9: GEÇTİ=0). Hüküm/seçim/look etkisi YOK.
- Payload kaynağı TEK: `scripts/export_viz_payload.py` → capped akış, **P0×A0** (Aşama 9 kilidi), `data/processed` frame'leri.
- Otomatik test adayları (P3, gelecek maint — R11 batch): pine dosyasında `strategy(`/`alert` yasak-kelime kilidi + payload yapı doğrulaması. Bu patch'te YOK (kapsam dışı).

## 1) Kurulum adımları (M9c — hazır dosya akışı; bölge ameliyatı YOK)

1. `python3 -W ignore scripts/export_viz_payload.py --month YYYY-MM` → `viz/quant4h_viz_<ASSET>_YYYY-MM.pine` (payload GÖMÜLÜ tam dosya; üretici iç yapısal lint uygular: her tanım TAM 1 kez + strategy/alert yasağı) + `viz/payload_YYYY-MM.txt` (referans).
2. TradingView Pine editöründe YENİ sekme aç → `<ASSET>.pine` dosyasının **TÜMÜNÜ** kopyala-yapıştır → kaydet.
3. Grafiği **4H**'de, ilgili sembolde aç (BTC → `BTCUSDT` (Binance) veya eşleniği; GOLD → `GC1!`/`XAUUSD`; SILVER → `SI1!`/`XAGUSD`; BIST30 → `XU030`).
4. Aşağıdaki parite listesini uygula (İLK kurulumda ZORUNLU; sonraki aylarda spot-check).
5. `payload_*.txt`'yi DOĞRUDAN yapıştırmayın.

**Hata modları (M9c vakasından öğrenildi):**

| TradingView hatası | kök neden | çözüm |
|---|---|---|
| `Syntax error at input 'end of line without line continuation'` (payloadMeta satırında) | txt başlık yorumları `payloadMeta =` satırına karışmış (bölge ameliyatı) | hazır `<ASSET>.pine` dosyasını kullan |
| duplicate declaration (`payloadMeta`/`ts` zaten tanımlı) | birden fazla varlık bloğu aynı anda yapıştırılmış | hazır `<ASSET>.pine` (tek varlık) kullan |
| plot/marker görünmüyor ama hata yok | sembol timeframe'i 4H değil veya payload ayı farklı | 4H + aynı ay payload'ı |

> **DÜRÜST NOT (sembol eşleme):** payload Binance spot `BTCUSDT` ve Yahoo `GC=F/SI=F/XU030.IS` verisinden üretilir. TradingView sembolü farklı bir vendor'sa mumlar birebir örtüşmeyebilir; parite kontrolü payload'ı üreten sembolün grafisinde yapılmalıdır. Farklı sembolde kullanım "yaklaşık görselleştirme"dir ve UNTESTED-VIZ etiketiyle kalır.

## 2) Parite kontrol listesi (manuel; kaynak kolonlar `data/processed/signals/<KEY>_4h_signals.parquet`)

| # | kontrol | kaynak (Python) | beklenen (Pine) |
|---|---|---|---|
| P1 | EMA200 eğrisi | `ema_trend` kolonu | turuncu çizgi; 3 rastgele barda değeri ±0.01 ile aynı |
| P2 | Yapısal stop | `stop_long` | kırmızı stepline; son onaylı barda değer aynı |
| P3 | Swing destek/direnç | `last_swing_low` / `last_swing_high` | yeşil/teal stepline; onay gecikmesi (k+1=4 bar) GÖRSELDE de aynı |
| P4 | Donchian(20) | `donchian_high` / `donchian_low` | gri noktalı; KAPANMIŞ 20 bar penceresi (shift'li) |
| P5 | LONG marker | `long_signal == True` (capped final) | yeşil üçgen, KARAR barının KAPANIŞ fiyatında; başka barda marker YOK |
| P6 | SHORT marker | `short_signal == True` | kırmızı üçgen (yalnız core; BIST30 endeks frame'inde tanısal) |
| P7 | Marker sayısı | pencere içi `long_signal.sum()+short_signal.sum()` | grafikteki marker adediyle birebir |
| P8 | İcra temsili YOK | — | hiçbir "giriş/çıkış oku", P&L, pozisyon çizgisi YOK |
| P9 | Boş payload fail-safe | `payloadOK=false` | yalnız uyarı tablosu; çizim YOK; hata YOK |
| P10 | Banner | — | sağ üstte "UNTESTED-VIZ · doğruluk kaynağı DEĞİLDİR · trade/emir/tavsiye YOK" |
| P11 | Yapısal bütünlük (otomatik) | `lint_pine()` üreticide | her `<ASSET>.pine`: 12 payload tanımı TAM 1 kez · `strategy(`/`alert(` yok — ihlalde üretici exit 1 |

**Uyuşmazlık bulursan:** Pine grafiği DEĞİL, Python çıktısı esastır. Uyuşmazlığı `reports/cadence/` ya da aylık rapora not düş; pine dosyasını kullanıcı onayı olmadan değiştirme.

## 3) Configs kilitli ayar tablosu (Pine'da HESAPLANMAZ — değerler Python'dan gelir)

| ayar | değer | kaynak (kilitli) |
|---|---|---|
| EMA periyodu | 200 | `config.DEFAULT_REGIME.ema_trend_period` |
| Donchian penceresi | 20 (yalnız KAPANMIŞ barlar, shift'li) | `DEFAULT_LEVELS.donchian_period` |
| Swing fraktal k | 3 (onay gecikmesi k+1 = 4 bar) | `DEFAULT_LEVELS` |
| Stop buffer | 1.0 × ATR(14) — aday küme {0.5,1.0,1.5}, seçim Aşama 9 | `DEFAULT_LEVELS.stop_buffer_atr` |
| Momentum | ATR-normalize ROC, n=10, m=1.0σ | `DEFAULT_MOMENTUM` |
| Tetik | Donchian(20) kırılımı | Aşama 5 |
| Cooldown | 3 bar (ilk yeniden sinyal s+4) | Aşama 5 |
| Akış | **capped** (pozisyon vekili + 90 bar) | Aşama 6 primary |
| Çıkış hücresi | **P0×A0** (TS90 + TP3R + dondurulmuş stop) | Aşama 9 kilidi |
| İcra | sinyal bar t KAPANIŞI → giriş open[t+1] | kabul kriteri 3 |
| Grafik öğeleri | mum + EMA200 + yapısal seviyeler (+ M9b marker'ları; hepsi input ile kapatılabilir) | `simplicity_rules.max_chart_elements=3` + M9b direktifi |

## 3b) M14 MULTI v2 kontrol listesi (`viz/quant4h_viz_multi_<AY>.pine`)

| # | kontrol | beklenen |
|---|---|---|
| M1 | sembol eşlemesi | BTCUSDT / GC1!·GC=F·XAUUSD / SI1!·SI=F·XAGUSD / XU030 dışında → çizim YOK + "⚠ PAYLOAD YOK" banner'ı |
| M2 | SADE MOD varsayılan | yalnız ▲ "AL koşulu oluştu (sinyal kaydı)" + ✖ "SAT koşulu (sinyal kaydı)"; EMA/seviyeler toggle-KAPALI |
| M3 | TRADE-REVIEW toggle | R etiketleri (trade başına, çıkışta) + kümülatif R stepline (scale.none); kaynak = reports/trades_*.csv gömülü diziler; Pine'da hesap YOK |
| M4 | trade dizisi paritesi | pine giriş-trade sayısı == trades CSV satır sayısı (üretici lint + test_viz_multi) |
| M5 | BIST30 bloğu | trade-review YOK (boş diziler); banner "trade-review: YOK" |
| M6 | SABİT banner | UNTESTED-VIZ + watch_only + "doğruluk kaynağı DEĞİL" + payload ufku satırı kapatılamaz |
| M7 | strategy/alert | kod satırlarında YOK (lint_multi) |
| M8 | payload ufku | dosya her --fetch'li §A koşusunda yenilenir (runbook §A-cadence kural 7) |

## 4) UNTESTED-VIZ etiketinin anlamı

Bu ek **hiçbir aşamada** otomatik doğrulanmadı: Pine derleyicisi bu ortamda yok; parite listesi (§2) elle uygulanana kadar çizimlerin doğruluğu **VARSAYILMAZ**. Etiket, pine dosyasının başlığında, payload başlığında ve bilgi tablosunda GÖRÜNÜR olmak zorundadır. Etiket kaldırılırsa bu plan ihlal edilmiş olur.

## 5) İlk koşu kanıtı (2026-09-18)

- `scripts/export_viz_payload.py` çalıştırıldı → `viz/payload_2026-09.txt` (4 varlık bölümü; checkpoint verisi, BTC son bar 2026-09-16 08:00 UTC).
- Payload yapı denetimi (manuel): her bölümde `payloadOK`, 10 dizi aynı uzunlukta, `ts` artan, final sinyal sayısı `signal_report` ile tutarlı.
- Pine derleme/parite: **UYGULANMADI** (TradingView erişimi bu ortamda yok) → UNTESTED-VIZ geçerli; kullanıcı ilk kurulumda §2 listesini uygulamalıdır.

*Bu belge yatırım tavsiyesi değildir.*
