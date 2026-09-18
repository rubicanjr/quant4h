# quant4h

**BIST30 · Altın · Gümüş · BTC** için 4 saatlik zaman diliminde çalışan, kural
tabanlı çekirdeğe sahip, opsiyonel ML ikinci-onay filtreli **araştırma / backtest /
sinyal üretim** sistemi.

> ### ⚠️ Bu proje ne YAPMAZ
> - **Canlı alım/satım emri vermez.** Emir iletme kodu yoktur, olmayacaktır.
> - **Yatırım tavsiyesi değildir.** Tüm çıktılar olasılıksal araştırma artefaktıdır.
> - **"Garantili kazanç" / "risksiz işlem" / "kesin kazandıran sistem" iddiası yoktur.**
>   Geçmiş performans gelecek sonuçların göstergesi değildir.
> - Canlı işlem kararı **tamamen kullanıcıya aittir.**

---

## 1. Durum

| | |
|---|---|
| Proje statüsü | **ARAŞTIRMA-KAPALI · watch_only** (Aşama 11 kapanışı, 2026-09-17) |
| Aşama | **0–9 ✅ · 11 ✅ TAMAM** · 10 (ML) `ml_policy.gate` KAPALI (Aşama 9: GEÇTİ=0) |
| Testler | **235/235 PASS** |
| Aşama 9 OOS hükmü | **GEÇTİ = 0** → BTC **KALDI** (VALID expR −0.32; TEST koşulmadı) · GOLD/SILVER **ZAYIF (örneklem)** · BIST30 sepet **KALDI** (VALID −0.06) · hepsi `watch_only` |
| Nihai kayıt | `reports/final_verdict.md` (hüküm + protokol günlüğü + look=1) |
| Model kartı | `models/model_card.md` (NEDİR / NE DEĞİLDİR / watch_only tanımı / ML gate KAPALI) |
| Operasyon | `ops_runbook.md` (aylık sinyal izleme — trade YOK · çeyreklik ÖN-KAYITLI yeniden değerlendirme, maks 4 look/yıl · look log'u) |
| Çekirdek portföy | BTC · GOLD · SILVER (hepsi **AMBER**, `usable_for_modelling=True`) |
| BIST30 hisse sepeti | **28 hisse** (ünivers 30; DSTKF ve TRALT elendi) · 1.436 4H bar/hisse (v1.1, ince bar yok) |
| Bağlam filtresi | `XU030.IS` — trade varlığı DEĞİL, long'lar için filtre |
| Rejim motoru | **6 durum**: `trend_up/trend_down/range` × `vol_high/vol_normal/vol_low` · fail-closed |
| XU030 filtresi | BIST30 hisseleri **LONG-ONLY**; yeni long yalnızca XU030 4H kapanış > EMA200 iken |
| Yapısal seviyeler | k=3 fraktal swing (onay gecikmesi 4 bar) + Donchian(20, yalnız KAPANMIŞ barlar) |
| Yapısal stop | long `swing_low − 1.0×ATR` · short (yalnız core) `swing_high + 1.0×ATR` · **DONDURULMUŞ** (`FrozenStop`) |
| Momentum | **tek kural**: `mom = (close/close[t−n] − 1) / (ATR14/close[t−n])`, n=10, m=1.0 ATR |
| Sinyal zinciri | rejim ∧ bağlam(BIST) ∧ tradable ∧ return_valid ∧ seviye ∧ momentum — hepsi fail-closed |
| Giriş tetiği | Donchian(20) kırılımı: `close > max(high[t-20..t-1])` — yeni indikatör YOK |
| İcra | sinyal bar **t kapanışı** → giriş bar **t+1 açılışı** (`execution_price = open[t+1]`) |
| Cooldown | 3 bar (12 saat); off-by-one sözleşmesi `s → s+4`, ölçülen `min_gap = 4` |
| Çıkış motoru | P0: dondurulmuş stop + time-stop 90 bar + TP 3R · aynı bar çakışması → **STOP** (pesimist) · P1–P3 karşılaştırıldı, SEÇİLMEDİ |
| Risk katmanı | eşit-risk %0.5 + tavanlar (toplam 6 · BTC 2 · GOLD/SILVER 1 · sepet 3 · metals tek kova · banka 2 · günlük %2/haftalık %5 · 4-kayıp freni) — tavanlar yalnız girişte |
| Baseline sonuç (in-sample) | **hiçbir varlık buy&hold'u geçemedi**; tavanlar maxDD −%17.7→−%7.8 indirdi |
| Sıradaki iş | YOK (araştırma-kapalı) — tek yol `ops_runbook.md` §B ön-kayıtlı çeyreklik look veya YENİ PROJE |

### Bu repo neyi KANITLADI / KANITLAMADI

**Kanıtlandı (yöntem):** ön-kayıt → inşa → OOS hüküm kapısı uçtan uca ÇALIŞIYOR: frozen sha256 kilitleri, look-ahead silme testleri, pesimist fill sözleşmesi, H35, tune yasakları (küme dışı ValueError), seçim dondurma + TEST RED kilidi, tek-look disiplini, 235 regresyon testi, tam denetim izi (H1–H45 + D1–D8). İn-sample'da ölçülen hiçbir sonuç OOS'a taşınmadı ve sistem bunu **dürüstçe KALDI/ZAYIF diye raporladı** — pipeline'ın overfit'e karşı direnci bizzat kendi çıktısıyla doğrulandı.

**Kanıtlanmadı (edge):** bu kural seti, bu varlıklarda, bu dönemde (2024–2026 tek yönlü boğa; TEST 159 gün; metaller 2.4 yıl) ölçülebilir bir edge ÜRETMEDİ. BTC ve sepet için OOS beklenen değer negatif; metaller için örneklem hüküm vermeye yetmiyor. **Sistem para kazanıyor DENEMEZ; kaybediyor da DENEMEZ** (GOLD/SILVER) veya **ölçülen dönemde edge gösteremedi** (BTC/sepet). Devamı yalnız runbook'taki ön-kayıtlı look'larla mümkün.

Ayrıntı ve tüm kayıtlı teşhisler için → **[`PROGRESS.md`](PROGRESS.md)**
Onaylanmış kullanıcı kararları için → **[`configs/user_decisions.yaml`](configs/user_decisions.yaml)**

---

## 2. Tasarım ilkesi: SADELİK (bağlayıcı)

Bu proje bilinçli olarak **dar** tutulur. Kullanıcı kararıyla yasaklanan kapsam:

**Çekirdek mantık — 4 bacak, hepsi okunabilir kural:**

| Bacak | Kural | Görsel karşılığı | Durum |
|---|---|---|---|
| Trend filtresi | `EMA200` yönü (close vs EMA + ATR-normalize eğim) | grafikte **tek** çizgi | ✅ Aşama 2 |
| Rejim | `ATR(14)` yüzdelik dilimi (500 bar geriye dönük) | sayısal, grafikte yok | ✅ Aşama 2 |
| Bağlam (BIST30) | XU030 4H kapanış > EMA200 → long izni | grafikte **tek** çizgi | ✅ Aşama 2 |
| Momentum onayı | `ATR-normalize ROC` (n=10, m=1.0 ATR) — TEK ölçüm | sayısal, grafikte yok | ✅ Aşama 4 |
| Yapısal stop | onaylı swing_low − 1.0×ATR (long) / swing_high + 1.0×ATR (short, core) | grafikte çizgi | ✅ Aşama 3 |
| Esnek kâr alma | partial + runner / trailing / time stop | grafikte hedef çizgisi | ⬜ Aşama 7 |

**Grafikte maksimum 3 öğe:** mum + EMA200 + yapısal stop/hedef çizgileri.

**YASAK (aşırı indikatör yığını):** ADX · Hurst · HMM · Choppiness · BB-width ·
Ichimoku · Supertrend · Keltner · Order block · Volume Profile/POC/HVN/LVN ·
Anchored VWAP · Fractal · StochRSI · MFI · OBV · RSI+MACD+BB+Stoch üst üste.

**ML politikası:** ML **zorunlu katman değildir**. Yalnızca *opsiyonel ikinci onay
filtresi*dir, varsayılan olarak kapalıdır ve sadece kural tabanlı çekirdeği
**out-of-sample'da geçerse** devreye girer.

---

## 3. Kurulum

```bash
cd quant4h
python3 -m pip install -r requirements.txt
```

> **LightGBM / XGBoost bilerek listede yok.** Bu ikisi `libgomp.so.1` (OpenMP)
> gerektirir; proje ortamında bu kütüphane yok ve kurulamadı. ML gerekirse
> `sklearn.ensemble.HistGradientBoostingClassifier` kullanılır — histogram tabanlı,
> LightGBM ile aynı aile, ek sistem paketi gerektirmez ve bu ortamda çalışıyor.

---

## 4. Kullanım

### Testleri çalıştır

```bash
for t in test_resample_qc test_adjust test_cleaning test_splits; do
    python3 -W ignore tests/$t.py                  # toplam 55/55 beklenir
done
```

`pytest` zorunlu değil; her dosya kendi çalıştırıcısını içerir.

### Veriyi indir + veri kalitesi raporu üret

```bash
python3 -W ignore scripts/run_data_qc.py \
    --assets BTC GOLD SILVER BIST30 \
    --start 2017-08-17 --timeframe 4h --min-rows 1500
```

Bu tek komut **resample → adjust → QC → rapor** zincirini çalıştırır (sıralama
önemlidir; ayrı çalıştırılırsa interim yeniden üretildiği için 1 bar kayar — H14).

Çıktılar:

| Dosya | İçerik |
|---|---|
| `reports/qc_report.md` | insan-okur rapor: özet tablo, zorunlu caveat'ler, varlık bazlı tüm bulgular |
| `reports/qc_report.json` | makine-okur rapor (CI / otomasyon için) |
| `reports/qc_findings.csv` | düz bulgu listesi (filtrelenebilir) |
| `reports/adjust_evidence.md` | **kanıt tablosu**: silinen/eklenen bar = 0, kesinti pencereleri, getiri düzeltmesi önce/sonra, roll adayları |
| `data/raw/*.parquet` | **immutable** ham veri |
| `data/interim/*_4h.parquet` | 4H'ye dönüştürülmüş kanonik veri |
| `data/processed/*_4h_adjusted.parquet` (+ `.attrs.json`) | işaretlenmiş veri: `non_tradable`, `return_valid`, `roll_candidate`, `close_raw`, `close_adjusted` |

### BIST30 hisse üniversali (Aşama 1.5)

```bash
python3 -W ignore scripts/run_bist_universe.py            # 30 hisse: indir + 4H + QC
python3 -W ignore scripts/run_bist_universe.py --limit 3  # duman testi
```

| Çıktı | İçerik |
|---|---|
| `reports/bist30_universe_qc.md` | hisse bazlı QC tablosu + eleme gerekçeleri + zorunlu caveat'ler |
| `reports/bist30_universe_qc.csv` / `.json` | aynı verinin makine-okur hâli |
| `data/raw/bist30/<CODE>_{1h,1d}_raw.parquet` | immutable ham (1h fiyat, 1d kurumsal aksiyon tespiti için) |
| `data/interim/bist30/<CODE>_4h.parquet` | 4H kanonik |
| `data/processed/bist30/<CODE>_4h_adjusted.parquet` | işaretli: `non_tradable`, `return_valid`, `corporate_action_flag`, `halt_or_limit_flag` |

**Kritik teknik bulgu:** Yahoo'nun **1h** BIST serisinde `adjclose == close`
(%100 ölçüldü) — intraday seri kurumsal aksiyon düzeltmesi **içermez**. Bu
yüzden tespit **günlük** seriden yapılır ve ex-date'ler `session_date` üzerinden
4H barlara taşınır. Politika: **otomatik düzeltme YOK, FLAG ONLY**.

### Rejim etiketleri + XU030 bağlam filtresi (Aşama 2)

```bash
python3 -W ignore scripts/run_regime_report.py
```

| Çıktı | İçerik |
|---|---|
| `reports/regime_report.md` | core + XU030 + **28 hisse** rejim dağılım tablosu, filtre ret sebepleri, final-long bileşimi |
| `reports/regime_report.json` | makine-okur hâli |
| `data/processed/regime/<KEY>_4h_regime.parquet` | 32 etiketli frame (`regime`, `long_regime_ok`, `longs_allowed`, `long_final_ok`, …) |

**Final long izninin bileşimi** (hisselerde):

```
long_final_ok = long_regime_ok      # trend_up VE ATR yüzdeliği <= 0.95
              AND longs_allowed      # XU030 4H kapanış > EMA200 (KAPANMIŞ bar, fail-closed)
              AND NOT non_tradable   # kesinti / ince açılış barı / oluşuyor / kurumsal aksiyon
              AND return_valid       # boşluğu veya ex-date'i atlayan getiri DEĞİL
```

Sepet genelinde **%19,4** bar final long izni alır (hisse bazında %4,7 … %27,6).
Bu düşüklük bir hata değil, **çift onay + veri kalitesi kapılarının** birleşik
etkisidir: amaç işlem sayısını değil, yanlış sinyal oranını düşürmektir.

### Baseline backtest (Aşama 6)

```bash
python3 -W ignore scripts/run_backtest.py
python3 -W ignore scripts/run_backtest.py --risk-profile conservative --time-stop 120 --tp 2.0
```

| Çıktı | İçerik |
|---|---|
| `reports/backtest_baseline.md` | **§0 ANA BULGU** · core tablosu · maliyet satırı · bootstrap CI · çıkış karışımı · basket agregasyonu · hisse appendix · zorunlu caveat'ler |
| `reports/backtest_baseline.json` | makine-okur hâli |
| `reports/trades_*.csv` | trade listeleri (BTC, GOLD, SILVER, bist30_basket) |
| `reports/figures/equity_*.png` | equity eğrileri |

**Çıkış motoru:** dondurulmuş yapısal stop · time-stop `90` bar · TP `3R`.
Aynı barda çakışma → **STOP** öncelikli (pesimist). Gap'lerde stop `open`'dan
(aleyhimize), TP `open`'dan. Time-stop kapanıştan. Giriş `open[t+1]`. Maliyet
iki tarafa da. **Geçerli stopu olmayan pozisyon ASLA açılmaz.**

Aday kümeler `{time-stop: 60, 90, 120}` × `{TP: 2R, 3R, 4R}` → **yalnızca Aşama 9**.
`ExitConfig(tune_now=True)` ve `same_bar_priority="tp"` config seviyesinde `ValueError`.

> **Dürüst sonuç:** bu parametre setiyle sistem **"para kazanıyor" denemez**;
> "kaybediyor" da denemez — örneklem yetersiz (GOLD 30, SILVER 34, hisse başına
> medyan 6 trade) ve dönem tek yönlü bir boğa piyasası. Tablo **in-sample**'dır.
> Aşama 7 + Aşama 9 (OOS) olmadan hiçbir karar verilmemelidir.

### Giriş tetiği ve sinyal montajı (Aşama 5)

```bash
python3 -W ignore scripts/run_signal_report.py
python3 -W ignore scripts/run_signal_report.py --cooldown-bars 3 --max-position-bars 90
```

| Çıktı | İçerik |
|---|---|
| `reports/signal_report.md` | varlık başına sinyal sayısı · yıllara göre dağılım · ort. sinyaller arası gün · zincir halkaları · uygulanamaz sinyaller |
| `reports/signal_report.json` | makine-okur hâli |
| `data/processed/signals/<KEY>_4h_signals.parquet` | 31 frame (`strict` akışı) — Aşama 2+3+4+5 kolonlarının tamamı |

```
tetik LONG  : close[t] > max(high[t-20 .. t-1])
tetik SHORT : close[t] < min(low[t-20 .. t-1])          (yalnız CORE)
zincir      : rejim ∧ bağlam(BIST) ∧ tradable ∧ return_valid ∧ momentum ∧ tetik ∧ stop_valid
icra        : sinyal bar t KAPANIŞI → giriş bar t+1 AÇILIŞI  (signal_bar_close P&L'de YOK)
cooldown    : 3 bar (12 saat) → sinyal barı s ise ilk yeniden sinyal s+4
```

> **`shift` notu:** `donchian_high` kolonu zaten `rolling(20).max().shift(1)`
> olduğu için tetikte **ikinci bir shift YOKTUR**. Olsaydı pencere 21 bara
> çıkar ve "önceki 20 kapanmış bar" kriteri bozulurdu. Eşdeğerlik ham `high`
> serisinden elle hesaplanarak test ile kilitlendi.

> **⚠️ Sinyal sayıları GEÇİCİDİR.** Pozisyon vekili yalnızca dondurulmuş
> stop'un bar içi ihlalini çıkış sayar; yapısal stop ~2,6–3,2 ATR geride
> olduğu için fiyat onu yıllarca ihlal etmeyebiliyor ve pozisyon ~%90 açık
> kalıp sinyalleri bastırıyor (CORE: 1.012 ham → 9 final). Bu bir kod hatası
> değil, **Aşama 7'nin (TP / trailing / time-stop) neden zorunlu olduğunun
> ölçülmüş kanıtıdır**. Rapor bu yüzden üç akışı birlikte verir:
> `strict` (şartname kuralı) · `capped` (+90 bar time-stop) · `cooldown_only`
> (cooldown etkisini izole eder).

### Momentum onayı + sinyal zinciri (Aşama 4)

```bash
python3 -W ignore scripts/run_momentum_report.py
```

| Çıktı | İçerik |
|---|---|
| `reports/momentum_report.md` | geçiş oranları + kalibrasyon bandı kontrolü + zincir halka sayıları + final sinyal özeti |
| `reports/momentum_report.json` | makine-okur hâli |
| `data/processed/signals/<KEY>_4h_signals.parquet` | 31 frame: Aşama 2+3+4 kolonlarının tamamı |

```
mom = (close[t] / close[t−n] − 1) / (ATR14[t] / close[t−n])      n=10, m=1.0
long onayı:  mom > +m        short onayı: mom < −m  (yalnız CORE)
long_final_ok = rejim ∧ bağlam(BIST) ∧ tradable ∧ return_valid ∧ seviye ∧ momentum
```

Aday küme `n∈{5,10,20}`, `m∈{0.5,1.0,1.5}` → **yalnızca Aşama 9**'da, yalnızca
core varlıklarda test edilir; küme dışı değer `ValueError`. Kalibrasyon bandı
`[0.10, 0.60]`: dışında ise **TUNE EDİLMEZ**, yalnızca bayraklanır
(`MomentumConfig(tune_out_of_band=True)` config seviyesinde hata verir).

### Yapısal seviyeler + dondurulmuş stop (Aşama 3)

```bash
python3 -W ignore scripts/run_levels_report.py
```

| Çıktı | İçerik |
|---|---|
| `reports/levels_report.md` | varlık başına stop mesafesi (medyan ATR katı + fiyatın %'si), breakout/temas sayıları, politika ve zorunlu not |
| `reports/levels_report.json` | makine-okur hâli |
| `data/processed/levels/<KEY>_4h_levels.parquet` | 32 frame: Aşama 2 + Aşama 3 kolonlarının tamamı |

Look-ahead sözleşmesi: swing **p+k < t** ise görünür (k=3 → 4 bar gecikme);
Donchian `shift(1)` ile yalnız **kapanmış** barları kullanır; `return_valid=False` /
`non_tradable=True` / `halt_or_limit_flag=True` barlar **anchor olamaz**; pencere
geçerlilik oranı < 0.90 ise Donchian **NaN** (fail-closed).

Stop **girişten önce** planlanır ve `FrozenStop` (frozen dataclass) ile dondurulur:
`widen()` / `move_against()` / `relax()` → `StopImmutabilityError`. Yalnızca pozisyon
lehine `tighten()` çağrılabilir ve o da **yeni bir nesne** döndürür; `initial_stop`
her zaman korunur. Buffer aday kümesi `{0.5, 1.0, 1.5}` **Aşama 9'da** test edilir —
şimdi seçim YOK, küme dışı buffer `ValueError` verir.

> **Zorunlu not:** BIST30 hisselerinde warmup nedeniyle TRAIN etiketli bar sayısı
> azdır (~426 tradable bar/hisse). Bu yüzden **hiçbir aşamada hisse başına in-sample
> parametre seçimi YAPILMAZ**. Parametre seçimi Aşama 9'da, küçük aday kümesiyle ve
> yalnızca **core varlıklar** üzerinde; hisseler **yalnızca OOS** raporlanır.
> Kod kilidi: `PER_ASSET_IN_SAMPLE_TUNING_ALLOWED = False`.

### Split ön-kaydı (pre-registration)

```bash
python3 -W ignore scripts/register_splits.py           # configs/splits_preregistered.yaml yaz
python3 -W ignore scripts/register_splits.py --check   # sha256 + çakışma doğrulaması
```

Test dönemi **herhangi bir sonuç görülmeden** sabitlenir. `--check` kaynak
dosyanın SHA-256'sını doğrular: veri değiştiyse ön-kayıt **GEÇERSİZ** ilan edilir.

Faydalı bayraklar: `--no-cache` (yeniden indir) · `--retries N --retry-sleep S`
(Yahoo 429 için) · `--with-context` (DXY/US10Y/USDTRY/SPX/VIX) · `--funding`
(BTC perp funding, yalnızca maliyet/bağlam).

---

## 5. Klasör yapısı

```
quant4h/
├── PROGRESS.md                  # << kaldığın yer. TEK kaynak.
├── README.md
├── requirements.txt
├── configs/
│   └── user_decisions.yaml      # onaylanmış kullanıcı kararları (bağlayıcı)
├── data/
│   ├── raw/                     # immutable ham veri (parquet)
│   ├── interim/                 # 4H kanonik veri
│   ├── processed/               # (Aşama 4+) feature matrisleri
│   └── external/                # kullanıcının kendi CSV/parquet dökümleri
├── docs/                        # mimari, model kartı, kullanım kılavuzu, güvenlik kuralları
├── pine/ + viz/                 # M9b: TradingView görselleştirme EKİ (UNTESTED-VIZ; doğruluk kaynağı DEĞİL — TEST_PLAN.md)
├── reports/                     # qc_report.{md,json}, qc_findings.csv
├── scripts/
│   └── run_data_qc.py           # Aşama 0/1 sürücüsü
├── src/quant4h/
│   ├── config.py                # varlık/risk/maliyet/split/rejim — TEK yer
│   ├── data/
│   │   ├── schema.py            # kanonik OHLCV şeması
│   │   ├── adapters.py          # binance · yahoo · user_csv
│   │   ├── resample.py          # seans takvimi duyarlı 4H dönüşümü
│   │   ├── qc.py                # 13 kontrol ailesi + portföy kontrolleri
│   │   └── cleaning.py          # açık, loglanan temizlik (henüz test edilmedi)
│   ├── features/ labels/ models/ strategy/ risk/
│   ├── backtest/ learning/ reporting/ utils/     # (Aşama 3+) henüz boş
└── tests/
    └── test_resample_qc.py      # 21 test, sentetik+deterministik, ağ yok
```

---

## 6. Veri katmanı sözleşmeleri (kritik — bakınız `resample.py` docstring)

### 6.1 Kanonik şema

| Kolon | Tip | Açıklama |
|---|---|---|
| `symbol` | str | kanonik enstrüman kimliği (`BTCUSDT`, `XAUUSD_PROXY_GC`, …) |
| `timestamp_utc` | datetime (tz-aware UTC) | **bar AÇILIŞ zamanı** |
| `open/high/low/close` | float | **ham** fiyat, düzeltme uygulanmaz |
| `volume` | float | base-asset hacim; feed'de yoksa 0 |
| opsiyonel | float | `funding_rate, open_interest, spread, quote_volume, trades, taker_buy_volume, dxy, usdtry, benchmark, n_src_bars, session_date` |

### 6.2 Look-ahead koruması (3 katman)

1. **Bar semantiği:** `T` damgalı bar `[T, T+4h)` aralığını kapsar ve ancak
   `T+4h`'te **bilinir**. O bar üzerinde hesaplanan sinyal `T+4h` açılışında
   uygulanabilir. Backtest motoru bunu zorunlu kılar.
2. **Oluşmakta olan son bar düşürülür:** `drop_partial=True` (varsayılan).
   Tek başına bu kural, el yapımı pipeline'lardaki en yaygın look-ahead
   hatasını engeller.
3. **Boşluğu atlayan getiri gerçek getiri değildir:** `continuity` kontrolü
   seans-beklenen boşluktan sapen barları işaretler; bu barların getirisi
   outlier/roll/label/backtest hesaplarından **hariç tutulur** (bar silinmez).

### 6.3 Seans takvimleri — üç ayrı kavram (H4'ün dersi)

| Kavram | Alan | Ne işe yarar |
|---|---|---|
| Bar grid'i | `bar_anchor_local` + `bar_anchor_mode` | 4H barların nerede açılacağı |
| Seans açılışı | `session_anchor_local` | bilgilendirme / gece rolü |
| **Seans günü başlangıcı** | `session_day_start_local` | bir barın hangi **seans gününe** ait olduğu |

Bu üçü **bilinçli olarak ayrılmıştır**; tek parametreyle çözmeye çalışmak
BIST30'da seans başına bar sayısını bozmuştu (bug H4).

| Varlık | Grid | Mod | Seans günü başlangıcı | Bar/seans | UTC saatleri |
|---|---|---|---|---:|---|
| BTC | 00:00 UTC | `utc` | 00:00 | 6 | 00/04/08/12/16/20 |
| GOLD (GC=F) | 18:00 NY | `local` | 17:30 | 6 | DST ile kayar |
| SILVER (SI=F) | 18:00 NY | `local` | 17:30 | 6 | DST ile kayar |
| BIST30 | 10:00 Istanbul | `local` | 05:00 | 3 | 03/07/11 (sabit, TR'de DST yok) |

**Sonuç:** BIST30 ile BTC'nin 4H grid'i 3 saat faz farkıyla oturur → aralarında
**ortak 4H bar yoktur (n=0)**. Varlıklar arası korelasyon **yalnızca günlük**
bazda hesaplanır ve risk limiti de günlük korelasyona göre uygulanır. Seans
bütünlüğü, faz hizalamasına bilinçli olarak tercih edildi.

---

## 7. Veri durumu ve bilinen sınırlar

### 7.0 Veri provenansı ve ToS notu (M4 kararı, 2026-09-17 — kullanıcı onaylı)

- **`data/raw/` repoda DAĞITILMAZ** (git takibinden çıkarıldı): ham katman, vendor
  kaynaklarından **yerelde** çekilir — Binance spot klines (public API), Yahoo Finance
  (`yfinance`, resmî olmayan istemci; Yahoo ToS kişisel kullanım, yeniden dağıtım
  yasak), BIST30 üniversal listesi web kaynaklarından (Investing.com ve diğerleri,
  `configs/bist30_universe.yaml → sources` içinde erişim tarihleriyle kayıtlı).
- Ham veriyi yeniden elde etmek: `scripts/run_data_qc.py ... --no-cache --start 2017-08-17`
  (core 4 varlık) ve `scripts/run_bist_universe.py` (hisseler) — runbook §A politikasıyla.
- **`data/frozen/`, `data/interim/`, `data/processed/` tekrarlanabilirlik için tracked
  KALIR** (sha256 kilitli ön-kayıt artefaktları + türetilmiş katmanlar).
- Repo PUBLIC kalır (kullanıcı kararı 2026-09-17); kod + raporlar + türetilmiş
  snapshot'lar araştırma kaydıdır, ham vendor verisi yeniden dağıtılmaz.
- Aylık raw-drift hash logu: `reports/monitor/*.md` (runbook §A.3b).

| Varlık | Enstrüman | Bar | Geçmiş | Kalite | En önemli sınır |
|---|---|---:|---|---|---|
| BTC | `BTCUSDT` (Binance spot) | 19.888 | 9,1 yıl | ✅ EN İYİ | — |
| GOLD | `GC=F` (COMEX ön-ay) | 3.606 | 2,4 yıl | 🟡 AMBER | roll **kesin tespit edilemez** (kontrat ayı kimliği yok) → adaylar yalnız işaretli; ~2,4 yıl intraday |
| SILVER | `SI=F` (COMEX ön-ay) | 3.606 | 2,4 yıl | 🟡 AMBER | aynı; ayrıca 2026-01-26..02-06 feed kalitesi çok düşük |
| BIST30 (endeks) | `XU030.IS` | 2.158 | 2,9 yıl | ⚠️ bağlam | trade varlığı DEĞİL; long'lar için bağlam filtresi |
| **BIST30 (sepet)** | **28 hisse** (`configs/bist30_universe.yaml`) | ~2.158/hisse | 2,9 yıl | 🟡 | survivorship bias kaçınılmaz; günde 2 tam + 1 ince bar |

**Kayıtlı teşhisler (tam liste `PROGRESS.md` ve `configs/user_decisions.yaml`):**

- `2026-01-30 15:00 → 2026-02-02 18:00 UTC` arasında GOLD **ve** SILVER'da
  75 saatlik veri kesintisi (Yahoo kaynaklı ortak sorun).
- **SILVER 2026-02-02 −%22 olayı: ne roll ne bad print** — kesintiyi atlayan
  sahte getiri. Bar silinmedi, işaretlendi.
- `2026-01-26 .. 2026-02-06` penceresinde feed kalitesi çok düşük
  (GOLD ≈ −%17, SILVER ≈ −%45 savrulma; hacim %38–42'ye düşüş).
- `GOLD|SILVER` günlük korelasyonu **+0.768** → `balanced` profilin 0.70
  limitini aşar. İkisi aynı yönde tek risk birimi sayılmalıdır (Aşama 8).

---

### 7.1 BIST30 netleştirmesi (2026-09-16)

Kullanıcı netleştirdi: **"BIST30" = BIST30 konstitüant HİSSELERİ**, XU030 endeksi değil.
Buna göre:

- `XU030.IS` **trade varlığı değildir** → yalnızca long'lar için **bağlam filtresi** (`BIST30_CONTEXT`).
- Sinyal motoru **hisse sepeti** olacak; üniversal `configs/bist30_universe.yaml` içinde
  **tarih damgasıyla** sabitlenecek (aksi hâlde look-ahead).
- Hacim/onay bacağı hisse verisinde hacim olduğu için Aşama 1.5 QC'sinden sonra
  **tekrar değerlendirilecek** (şu an endeks için kapalı).
- **Kaçınılmaz caveat:** serbest veride yalnızca *bugün* endekste olan hisseler
  indirilebilir → **survivorship bias** sonuçları YUKARI çeker. BIST30 sonuçları
  BTC/metallerle aynı güven düzeyinde değerlendirilemez.

## 8. Yol haritası

| Aşama | İçerik | Durum |
|---|---|---|
| 0 | Netleştirme, iskelet, config, kararlar | ✅ |
| 1 | Veri kalitesi (+ adjust + cleaning + split ön-kaydı) | ✅ **TAMAM** |
| 1.5 | BIST30 hisse üniversali (30 üye → 28 hisse sepete girdi) | ✅ **TAMAM** |
| 2 | Rejim: EMA200 yönü + ATR yüzdeliği + XU030 bağlam filtresi | ✅ **TAMAM** |
| 3 | Yapısal seviyeler: swing + Donchian(20) + ATR buffer stop | ✅ **TAMAM** |
| 4 | Momentum: ATR-normalize ROC | ✅ **TAMAM** |
| 5 | Çift onay: trend + momentum (ML opsiyonel 3.) | ⬜ |
| 6 | Baseline backtest: gerçek çıkış motoru + maliyet + metrikler + buy&hold | ✅ **TAMAM** |
| 7 | Esnek kâr alma (partial+runner, trailing, breakeven, time-stop) | ⬜ **yetki bekliyor** |
| 8 | Risk: pozisyon boyutu, günlük/haftalık limit, korelasyon, ısı | ⬜ |
| 9 | Robustluk: walk-forward, parametre duyarlılığı, Monte Carlo | ⬜ |
| 10 | Opsiyonel ML ikinci onay (purged + embargo + walk-forward) | ⬜ |
| 11 | Çıktılar: raporlar, model kartı, kullanım kılavuzu, güvenlik kuralları | ⬜ |

---

## 9. Çalışma kuralları

1. Her aşamada **önce plan → sonra uygulama → sonra test → sonra doğrulama**.
2. Tek mesajda devasa kod üretme; dosyaları **parça parça** yaz, her parça sonrası kısa doğrula.
3. Her aşama bitince `PROGRESS.md`'ye `TAMAMLANDI: <aşama> + 3 satır özet` yaz.
4. Hata alırsan **durma**; hatayı 2 satırda özetle, düzelt, devam et.
5. Bir scripti `grep`/`tail` ile filtreleyerek çalıştırma; önce tam çıktı + exit code al
   (ders: H5 hatası bu yüzden 3 çalıştırma boyunca görünmedi).
6. Emin olmadığın yerde **varsayım yapma**; sor veya alternatifleri listele.
7. **Veri asla sessizce değiştirilmez/silinmez.** Ham katman immutable'dır; her
   mutasyon `CleaningLog`'a yazılır ve orijinal değerler korunur.
8. Backtest sonuçları komisyon + spread + slippage dahil hesaplanır. Sıfır
   maliyette hayatta kalan strateji strateji değildir.

---

## 10. Sorumluluk reddi

Bu depo eğitim ve araştırma amaçlıdır. İçeriği yatırım tavsiyesi, portföy
yönetimi hizmeti veya getiri taahhüdü değildir. Kaldıraçlı ve vadeli
enstrümanlar sermayenin tamamının kaybıyla sonuçlanabilir. Burada üretilen
her metrik **geçmiş veriye** dayanır; geçmiş performans geleceğin göstergesi
değildir. Herhangi bir işlem kararı almadan önce lisanslı bir uzmana danışın.
