# PINE_STYLE.md — Pine v5/v6 üretici stil rehberi + tuzaklar (M15, 2026-09-18)

*Bakım belgesidir (kod değil). `scripts/export_viz_payload.py` ve `pine/*.pine`
üretiminin bilinen tuzaklarını ve üreteç lint listesini tutar. Yeni oturum
bootstrap okuma listesine M15 ile eklendi (PROGRESS).*

## 1) Tuzaklar (kanıtlı vakalardan)

| # | tuzak | doğru kullanım | kanıt |
|---|---|---|---|
| T1 | `array.from<T>()` (0 arg) → Pine "Wrong number of args: 0" | boş küme → `array.new<T>()`; `array.from` YALNIZ ≥1 argümanla | M15 hata raporu (12 bulgu) |
| T2 | na semantiği: `array.from<float>(na, 1.5)` geçerli; ama `plot(na)` çizmez; `na == na` FALSE | eşleşmelerde `na` karşılaştırma YAPMA; `not na(x)` kullan | M9b/M14 şablonları |
| T3 | kaynak/dizi limitleri: TAM geçmiş Pine'a GİREMEZ (TV kaynak ~100 KB; dizi başına eleman sınırı) | pencere `--bars` (varsayılan 750 ≈ 4 ay); üreteç bütçe assert'i 90 KB; multi oto-daraltma (≥120 bar alt sınır) | M15 bütçe vakası (BTC@750=78 KB tek dosya OK; multi 187 bar/blok'a daraldı) |
| T4 | `max_bars_back` / geçmiş derinliği: döngü ile `time` eşleme O(n); büyük dizide bar başına lineer arama pahalı | M14: giriş/çıkış işaretçileri sıralı dizilerde O(1) amortize; seviye eşlemesi tek lineer arama (≤750 eleman) | M14 şablonu |
| T5 | `syminfo.ticker` öneksiz gelir ("BTCUSDT"), prefix'li bekleme hatası | eşleme TABLOSU tut (BTCUSDT / GC1!·GC=F·XAUUSD / SI1!·SI=F·XAGUSD / XU030); eşleşmeyende çizim YOK + banner | M14 multi |
| T6 | input.toggle varsayılanları kullanıcıya bırakılırsa SADE MOD bozulur | `simple_mode=true`, `show_ema/levels/trades=false` SABİT varsayılan; banner'lar input DEĞİL | M14 spec |
| T7 | virgülle çoklu atama (`a := 1, b := 2`) Pine'da YOK | her atama ayrı satır | M14 şablon ilk deneme hatası |
| T8 | `strategy()`/`alert()`/`alertcondition()` watch_only ihlalidir | YALNIZ `indicator()`; lint kod satırlarında yasak-kelime taraması (yorumlar soyulur) | M9b/M15 lint |
| T9 | epoch ms hesabında pandas çözünürlük tuzakları (`astype("int64")` us/ms verir) | `(ts - Timestamp(1970, tz=UTC)) // Timedelta(milliseconds=1)` | M9c vakası |
| T10 | Türkçe/unicode string literal'ler PINE'da OK ama payload META dışına taşmasın | meta tek satır string; banner sabit | M9b |
| T11 | tipsiz `na` ataması → Pine v5 "Value with NA type cannot be assigned..." | `float x = na` / `int x = na` / `bool x = na`; üreteç lint'i tipsiz `x = na` satırını REDDEDER | M15b hata raporu (entryPx/exitPx/exitR) |
| T12 | `//@version=5` SABİTTİR; TV "PINE VERSION OUTDATED" uyarısı KOZMETİKTİR, hata DEĞİL | v6 migrasyonu kapsam dışı; uyarıyı bastırmaya ÇALIŞMA | M15b kullanıcı kararı |

## 2) Üreteç lint listesi (`export_viz_payload.lint_pine / lint_multi / _lint_common`)

1. `array.from<...>()` (boş arg) YASAK → boş küme `array.new`.
2. `array.from` dizi uzunlukları == `ts` uzunluğu (`tr*` trade dizileri MUAF — bilinçli farklı).
3. `strategy(` / `alert(` / `alertcondition(` kod satırlarında YOK (yorumlar soyulur).
4. `PAYLOAD-BEGIN` / `PAYLOAD-END` çiftleri dengeli (tek dosya 1, multi 4).
5. Her payload tanımı (`ts, ema200, ..., payloadOK, trETs...`) prefix başına TAM 1 kez.
6. Kaynak bütçesi: dosya bayt < `BUDGET_BYTES` (90 KB; TV ~100 KB limiti, 10 KB marj).
7. Banner iğneleri: UNTESTED-VIZ · watch_only · "doğruluk kaynağı DEĞİL" · payload ufku · "PAYLOAD YOK" (multi).

## 3) Golden-file politikası

* Golden'lar `tests/fixtures/golden_viz_{multi,BTC}.pine` — TÜRETİLMİŞTİR (veri checkpoint'ine bağlı).
* Veri restore'u/üreteç değişikliği sonrası BİLİNÇLİ yenileme:
  `python3 scripts/export_viz_payload.py --out tests/fixtures/_gen && cp ... golden_*`.
* Test: `tests/test_viz_generator.py` (bayt-bayt eşleşme + lint kuralları + pencere/bütçe).

## 4) Tam geçmiş nereye?

Pine YALNIZ son `--bars` penceresini taşır. TAM geçmişin yeri:
`reports/*.md|json`, `reports/trades_*.csv`, `data/processed/*` ve
`scripts/run_dash.py` (yerel dashboard). Pine'a tam geçmiş koymaya ÇALIŞMA
(T3); görsel ihtiyaç = son ~4 ay + trade-review kayıtları.
