# PROGRESS.md — quant4h

> **Bu dosya projenin kaldığı yeri gösteren TEK kaynaktır.** Bir hata/kopma
> olursa buradan devam edilir. Her aşama kapanışında en üste yeni bir
> `TAMAMLANDI:` bloğu eklenir (en yeni en üstte).

**Proje:** BIST30 · Altın · Gümüş · BTC — 4H kural tabanlı çekirdek + opsiyonel ML onay filtresi
**Amaç:** backtest / validasyon / sinyal üretimi / risk yönetimi. **Canlı emir YOK, yatırım tavsiyesi YOK.**
**Son güncelleme:** 2026-09-17 (UTC)
**Test durumu:** **252/252 PASS**
`resample_qc` 21 · `adjust` 14 · `cleaning` 11 · `splits` 12 · `bist_universe` 12 · `regime_context` 14 · `levels` 23 · `momentum` 16 · `signals` 19 · `backtest` 26 · `basket_attrs` 6 · `exit_profiles` 19 · `risk` 15 · `stage9` 10 · `deliverables` 7

---

## TAMAMLANDI: M26-EVALFIX (mikro, 2026-09-19, kullanıcı onaylı TEK patch)

Özet: Windows TR locale (cp1254) çökmesi fix'i: `run_agent_eval.py` TÜM subprocess çağrıları `text=True + encoding="utf-8" + errors="replace"`; `_git()` ASLA None döndürmez (`(r.stdout or "").strip()`). Testler (sayı DEĞİŞMEDİ, mevcut 2 test sertleştirildi): cp1254 simülasyonu (`locale.getpreferredencoding` monkeypatch + child `PYTHONIOENCODING=cp1254`) · Türkçe commit mesajlı frozen tmp-repo fixture'da `sessions()` determinizmi · git yoksa gerçek-repo assert'i adaptif atlanır (sandbox tur-head dayanıklılığı). `test_sessions_detected` + `test_report_generation_skip_suite` yeşil. Suite **252/252** değişmedi. Hüküm/seçim/look YOK. Not: origin artık kümülatif commit `6c0c7f4`'te; M26 onun üstünde TEK commit.

## TAMAMLANDI: M24-AGENT-EVAL (2026-09-18/19, kullanıcı onaylı TEK patch) (2026-09-18/19, kullanıcı onaylı TEK patch)

Özet: `scripts/run_agent_eval.py` + `tests/eval/test_agent_eval.py` (6 test): son N patch oturumunu 5 kriterle skorlar → `reports/eval/2026-09-19.md`. **FORMAT**: commit konu tek satır + checkpoint öneki · PROGRESS bloğu ≤12 satır · patch/“TEK patch” atfı · suite satırı · DUR vekili (sınır satırı); sohbet satır sayısı repo'da tutulmadığından MANUAL işaretli. **FACTUALITY**: blok dosya yolları `ls` ile VAR (placeholder token muaf) · patch konu == commit konu (normalize) · blok suite x/x. **CONSISTENCY**: R09 çapraz sayaçlar (README==model_card==PROGRESS==iğne) + PROGRESS başlık == canlı suite (252). **REALISM**: cadence BAYAT damgası + QC RED→SORUN NOTU + pine SABİT banner + blok başına dürüst negatif token. **QUALITY**: insan rubric 1-5, LLM-judge YOK; `--quality N` ile PROGRESS'e işlenir:
<!-- quality-rubric --> Quality rubric (insan): BEKLEMEDE (1-5) — `run_agent_eval.py --quality N`.
İlk skor kartı (8 oturum): FORMAT 4–6/6 · FACTUALITY 2–4/4 · REALISM 3–4/4 · CONSISTENCY 2/2 ✅. Runbook §A kural 9: aylık pakete skor kartı eklendi. Sınırlar: hüküm/seçim/look YOK. Suite **246→252/252** (R09 senkronu).

## TAMAMLANDI: M23-PINE-BODY (2026-09-18, kullanıcı onaylı TEK patch) (2026-09-18, kullanıcı onaylı TEK patch)

Özet: Pine "The main body of the script is too long" hatası çözüldü: MULTI v3'te 4 blok × ~245 bar payload dizileri main body'de tanımlıydı; artık **her payload dizisi kendi fonksiyonunda** (`f_<blok><dizi>() => array.from<...>(...)`), main body yalnız `barstate.isfirst`'te aktif bloğun fonksiyonlarını çağırır (multi 36 fonksiyon, per-asset 9). Per-asset şablon da aynı biçime geçti (**viz v4**; gelecek pencere büyümelerine dayanıklı). PINE_STYLE **T15** (spec etiketi T13 çakıştı: T13=M15c scale kuralı; T15 olarak kaydedildi) + TEST_PLAN §3b M3c. Üreteç lint'ine "main body'de dizi literal satırı = 0" kontrolü eklendi (atama-biçimi `x = array.from<` RED). Golden'lar yenilendi; test_viz_multi 6 (yeni main-body testi), test_viz_generator 5. Suite **245→246/246** (R09 senkronu). Pencere değişmedi (~245 bar/blok @90 KB). Hüküm/seçim/look YOK.

## TAMAMLANDI: M22-TRADE-XLSX (2026-09-18, kullanıcı onaylı TEK patch) (2026-09-18, kullanıcı onaylı TEK patch)

Özet: `scripts/export_trade_report_xlsx.py` (openpyxl 3.1.5, requirements+lock'a eklendi): `reports/trades_*.csv` → `reports/xlsx/trades_<asset>.xlsx` (BTC 187 · GOLD 30 · SILVER 34 · basket 172 trade). Sayfalar: **TRADES** (başlık zemin+freeze A2+auto-filter+sütun genişlikleri; r_multiple koşullu yeşil/kırmızı; exit_reason renk kodu TP yeşil/stop kırmızı/time_stop amber/eod gri; sayılar 2-4 ondalık; zamanlar `yyyy-mm-dd hh:mm` naive-UTC) · **OZET** (trade sayısı, exit_reason dağılımı, ort/medyan R, win rate, maks ardışık kayıp, cost_total, net expectancy, equity maxDD — başlangıç 100k sabit) · **EGRI** (equity + openpyxl çizgi grafik). İki openpyxl tuzağı yakalandı: tz-aware datetime RED (naive UTC'ye normalize) + EGRI equity satır eşlemesi (i-1→i-2). Testler `tests/test_trade_xlsx.py` (5): sayfa adları+grafik, özetin CSV'den BAĞIMSIZ yeniden hesapla eşleşmesi, determinizm, biçim kilitleri, dağılım satırı. Runbook §A kural 8: aylık pakete xlsx eklendi. Sınırlar: yeni analiz YOK (salt renderer), hüküm/seçim/look YOK. Suite **240→245/245** (R09 senkronu).

## TAMAMLANDI: M21-DESCOPE (2026-09-18, kullanıcı onaylı TEK patch) (2026-09-18, kullanıcı onaylı TEK patch)

Özet: Pine viz indirgendi — trade-review overlay **TAMAMEN** çıkarıldı: trade dizileri (trETs/trEPx/trXTs/trXPx/trR), R etiketleri, kümülatif R, TRADE-REVIEW (ve simple_mode) toggle'ları, sigPrice dizisi ÜRETİLMİYOR; lint T14 bu üretimleri REDDEDER. Kalan: giriş/çıkış marker'ları (▲/✖ = SİNYAL kaydı, `close`'a çizilir) + EMA200 (toggle) + yapısal seviyeler (toggle) + watch_only/UNTESTED-VIZ SABİT banner (multi v3). **Trade verisi kaybı YOK:** kaynak `reports/trades_*.csv` duruyor (test kilitli: 187/30/34 satır). Pencere: overlay kalkınca multi oto-daraltma 187 → **245 bar/blok** (82 KB @90 KB bütçe, 0.8 adımlı); per-asset 750 sabit. NOT: spec tahmini ~350 idi; bağlayıcı olan TV kaynak limiti (~100 KB) — sapma kayıtlı (PINE_STYLE T14, TEST_PLAN §3b M3b). PINE_STYLE **T14** eklendi (spec etiketi T12 çakıştığı için T14 olarak kaydedildi: T12 M15b'de sürüm kuralına verildi). Golden'lar yenilendi; testler descope'a göre yeniden yazıldı (test_viz_multi 5 + test_viz_generator 5). Suite **240/240**. Hüküm/seçim/look etkisi YOK.

## TAMAMLANDI: M15c (mikro, 2026-09-18, kullanıcı hata raporu) (mikro, 2026-09-18, kullanıcı hata raporu)

Özet: Pine v5 hatası "The 'plot' function does not have an argument with the name 'scale'" — multi şablondaki kümülatif R çizgisi `plot(..., scale=scale.none)` kullanıyordu (v4 kalıntısı; overlay indicator'da kendi ölçekli çizgi MÜMKÜN DEĞİL). Çözüm: çizgi KALDIRILDI; kümülatif R bilgi olarak **label metnine** (`"1.2R (Σ3.4R)"`) + **banner ΣR satırına** taşındı (show_trades toggle'ında). PINE_STYLE **T13** + lint kuralı (`plot(..., scale=` üretimi RED); negatif yol doğrulandı. TEST_PLAN §3b M3 güncellendi. Golden'lar yenilendi (test_viz_generator 5/5 bayt-bayt). Suite **240/240**. Hüküm/seçim/look etkisi YOK.

## TAMAMLANDI: M15b (mikro, 2026-09-18, kullanıcı onaylı TEK patch) (mikro, 2026-09-18, kullanıcı onaylı TEK patch)

Özet: **(1)** multi şablonda `entryPx/exitPx/exitR = na` tipsizdi → Pine v5 "Value with NA type cannot be assigned"; artık `float entryPx = na` vb. **(2)** PINE_STYLE **T11**: "na atanan her değişken tip anahtar kelimesiyle (float/int/bool) tanımlanır"; `_lint_common` kuralı eklendi (negatif yol manuel doğrulandı); golden-file'lar yeniden üretildi (`test_viz_generator` bayt-bayt yeşil). **(3)** `//@version=5` **SABİT** (v6 migrasyonu kapsam dışı); TEST_PLAN notu: "PINE VERSION OUTDATED uyarısı kozmetiktir, hata değildir". Suite **240/240** değişmedi. Hüküm/seçim/look etkisi YOK.

## TAMAMLANDI: M15-PINE-FIX + SKILL (2026-09-18, kullanıcı onaylı TEK patch) + SKILL (2026-09-18, kullanıcı onaylı TEK patch)

Özet: **(1) HATA düzeltmesi:** üreteç boş trade dizilerini `array.from<T>()` (0 arg) yazıyordu → Pine "Wrong number of args: 0" (12 bulgu); artık `array.new<T>()`; lint kuralı: "array.from ≥1 arg ZORUNLU; boş küme → array.new". **(2) PENCERE:** viz penceresi parametreli `--bars` (varsayılan **750** ≈ 4 ay; varlık veri tavanı `min(N,len)`); üreteçte kaynak bütçesi assert'i (`BUDGET_BYTES`=90 KB, TV ~100 KB limiti payı); multi bütçeyi aşarsa **oto-daraltma** (≥120 bar; kanıt: 750→375→187 bar/blok). TAM geçmiş Pine'a GİREMEZ — yeri reports/CSV/run_dash; README §5 + TEST_PLAN §3c + PINE_STYLE §4'e yazıldı. **(3) GOLDEN-FILE:** `tests/fixtures/golden_viz_{multi,BTC}.pine` + `tests/test_viz_generator.py` (5 test): bayt-bayt golden eşleşmesi, lint kuralları (array.from arg · uzunluk==ts (tr* muaf) · strategy(/alert( yok · BEGIN/END dengeli · boş→array.new), pencere/bütçe. İlk denemede iki regex hatası yakalandı (greedy `.*`+re.S uzunluk kuralını sessiz etkisizleştiriyordu; trade dizileri bilinçli farklı uzunlukta → `tr*` muaf) — düzeltildi. **(4) SKILL:** `skills/pine/PINE_STYLE.md` — T1–T10 tuzak tablosu (kanıtlı vakalardan) + üreteç lint listesi + golden politikası + tam-geçmiş kuralı; README §5'e bootstrap okuma satırı eklendi. Suite **235→240/240** (R09 senkronu). Sınırlar: hüküm/seçim/look etkisi YOK; look hakkı tüketilmedi.

## TAMAMLANDI: M14-VIZ2 — viz sürüm 2: MULTI tek dosya + TRADE-REVIEW (salt renderer; 2026-09-18) — viz sürüm 2: MULTI tek dosya + TRADE-REVIEW (salt renderer; 2026-09-18)

Özet: `viz/quant4h_viz_multi_2026-09.pine` — TEK dosya, **4 gömülü payload bloğu** + `syminfo.ticker` eşlemesi (BTCUSDT · GC1!/GC=F/XAUUSD · SI1!/SI=F/XAGUSD · XU030); eşleşmeyen sembolde çizim YOK + "⚠ PAYLOAD YOK" banner'ı. **SADE MOD varsayılan:** yalnız ▲ "AL koşulu oluştu (sinyal kaydı)" + ✖ "SAT koşulu (sinyal kaydı)" marker'ları (bunlar backtest TRADE KAYIDIDIR, canlı sinyal/öneri DEĞİL); EMA200/seviyeler toggle-KAPALI; **UNTESTED-VIZ + watch_only banner'ı SABİT**. **TRADE-REVIEW overlay (toggle'lı, varsayılan kapalı):** giriş/çıkış eşleri + trade başına R etiketi + kümülatif R stepline (scale.none) — kaynak `reports/trades_*.csv` (capped P0xA0) GÖMÜLÜ diziler olarak; **Pine'da hesap YOK** (parite: BTC 187 / GOLD 30 / SILVER 34 / BIST30 0 == CSV satırları, test_kilit). BIST30 bloğunda trade-review YOK (endeks trade edilmez; sepet trade'leri hisse bazında, tek grafiğe eşlenemez). Şablon: `pine/quant4h_viz_multi.pine` (v5; master dizi seçimi ilk barda array.copy; giriş/çıkış işaretçileri O(1) amortize). Üretici: `export_viz_payload.py` artık trade dizilerini de gömüyor + `lint_multi` (4 blok × tanım tekilliği + strategy/alert yasağı + banner iğneleri). **Payload ufku:** runbook §A-cadence kural 7 (v1.4): her --fetch'li koşu multi dosyayı yeniler; banner'da ufku satırı. TEST_PLAN §3b M1–M8 listesi. Testler `tests/test_viz_multi.py` (5): blok/tekillik, CSV paritesi, sabit banner + SADE MOD varsayılanları, BIST30 trade-review YOK, üretici determinizmi (bayt-bayt). Suite **230→235/235** (R09 senkronu). Sınırlar: hüküm/seçim/look etkisi YOK; look hakkı tüketilmedi; emir/tavsiye YOK.

## TAMAMLANDI: M11-DASH — yerel terminal dashboard (salt renderer, watch_only; 2026-09-18) — yerel terminal dashboard (salt renderer, watch_only; 2026-09-18)

Özet: `scripts/run_dash.py` (rich 15.0.0, koyu tema, OpenTerminal-benzeri Layout): **header** (watch_only banner + son güncelleme + QC kararları) · **REJİM/BAĞLAM** (6'lı rejim + long/short_ok + XU030 close-vs-EMA200) · **SEVİYE+MOMENTUM** (swing/Donchian/stop_long + mom σ) · **SİNYAL log'u** (son final sinyaller: ham tetik→kapılar→final + 30g sayaç) · **CADENCE** (son bildirim dosyası + SAĞLIK satırı + slotlar + son fetch/rate kapısı) · **LOOK** (look #2 geri sayımı 2026-12-17 + kota 3/4 + "ön-kayıtsız look ihlal" uyarısı) · footer **EYLEM: YOK sabit**. Modlar: Live TUI (CTRL-C) / `--once` (tek kare, test/CI) / `--fetch` (runbook rate kapısı ≥200 dk, `cadence_4h_status.maybe_fetch` ile TEK kaynak + TAM zincir + QC RED fail-closed uyarısı). **Veri YALNIZ yerel artefaktlar** (processed frame'leri = Python motoru kolonları, qc_report.json, cadence dosyaları); ağ varsayılan KAPALI (`NETWORK_DEFAULT=False`); kendi indikatör/hesabı YOK — salt renderer. Testler `tests/test_dash.py` (5): deterministik panel snapshot'ı (sabit `now` ile bayt-bayt; golden-file YOK — veri restore'larında kırılgan olurdu, sözleşme = determinizm + iğneler) · panel/boundary iğneleri (watch_only/EYLEM/ağ KAPALI dahil) · look geri-sayım matematiği (46 gün / 0 gün) · render'ın state/QC dosyalarına YAN ETKİSİ yok (sha öncesi/sonrası) · fetch yolunun rate kapısına bağlılığı (inspect). Suite **225→230/230** (R09 senkronu: README/model_card/test iğnesi). Kanıt: `--once` render'ı tüm panellerle üretildi (ekran düzeni koyu tema); hüküm/seçim/look etkisi YOK; look hakkı tüketilmedi.

## TAMAMLANDI: M9c — Pine paste-hatası düzeltmesi: HAZIR dosya akışı (2026-09-18, kullanıcı hata raporu)

Özet: Kullanıcı TradingView'da M9b kurulumunda iki paste hatası yaşadı (ekran görüntüleriyle): (1) `Syntax error at input 'end of line without line continuation'` — `payload_*.txt` başlık yorumları `payloadMeta =` satırına karışmış (bölge ameliyatı hatası); (2) dört varlık bloğunun birlikte yapıştırılması → duplicate-declaration riski. Kök neden: M9b kurulumu manuel bölge değiştirme gerektiriyordu (kırılgan). **DÜZELTME (kök neden):** `export_viz_payload.py` artık varlık başına **GÖMÜLÜ payload'lı TAM .pine dosyası** üretiyor: `viz/quant4h_viz_<ASSET>_YYYY-MM.pine` → TradingView'da yeni sekme → dosyanın TÜMÜ yapıştırılır (bölge ameliyatı YOK). `payload_*.txt` yalnız referans döküme indirgendi (başlığına "DOĞRUDAN YAPIŞTIRMAYIN" uyarısı). Üreticiye **yapısal lint** eklendi (`lint_pine`): 12 payload tanımı TAM 1 kez + kod satırlarında `strategy(`/`alert(`/`alertcondition(` yasağı (yorumlar soyulur — H29/H33 deseni; şablonun kendi belge yorumu ilk denemede lint'i kırdı, düzeltildi) + şablon BEGIN/END eşleyici sertleştirildi. `pine/quant4h_viz.pine` KURULUM yorumu + `TEST_PLAN.md` §1 hazır-dosya akışına güncellendi + **hata-modları tablosu** (belirti→kök neden→çözüm) + P11 lint maddesi. Kanıt: 4 hazır dosya üretildi (BTC 93 bar/1 sinyal · GOLD-SILVER 61/1 · BIST30 22/0), lint temiz (tanımlar {1}, BEGIN/END 1/1, kodda yasak kelime yok). Suite **225/225** değişmedi. Kullanıcıya talimat: mevcut kırık paste'i SİL, `viz/quant4h_viz_BTC_2026-09.pine` (veya ilgili varlık) dosyasının tümünü yapıştır.

## TAMAMLANDI: M9b — BIST slot revizyonu + M9-PINE görselleştirme eki (2026-09-18, kullanıcı onaylı TEK patch)

Özet: **(1) Slot revizyonu (ONAY):** BIST30 slotları v1.1 ızgara KAPANIŞLARINA hizalandı: **14:00** (10:00–14:00 mumu, etiket 07:00 UTC) + **18:00** (14:00–18:00 mumu + seans sonu). CORE slotları (03–23) DEĞİŞMEDİ. Eski 11:00/15:00 BIST bildirimleri tarihî kayıt (demo dosyaları duruyor); 11:00/15:00 artık yalnız core slotu. `cadence_4h_status.py` + runbook §A-cadence (v1.3) güncellendi; slot-ızgara uyuşmazlık notu kaldırıldı (kanıt: `--slot 14:00` koşusu → grup YALNIZ BIST30, EXIT 0). **(2) M9-PINE:** `pine/quant4h_viz.pine` — **yalnız `indicator()`** (v5): Python'un ihraç ettiği marker/seviyeleri ÇİZER, HİÇBİR şeyi yeniden hesaplamaz; **`strategy()` YOK · `alert` YOK · icra/emir temsili YOK** (marker'lar KARAR barı kapanışında; open[t+1] gösterilmez); boş payload fail-safe (yalnız uyarı tablosu); kalıcı banner: "UNTESTED-VIZ · doğruluk kaynağı DEĞİLDİR · trade/emir/tavsiye YOK". `scripts/export_viz_payload.py` → `viz/payload_2026-09.txt` (4 varlık: BTC 93 bar/1 final sinyal · GOLD-SILVER 61 · BIST30 22; capped P0xA0; ts epoch-ms doğrulandı — ilk sürümdeki pandas 3.0 çözünürlük tuzağı (µs→ms) YAKALANDI ve çözünürlük-bağımsız hesapla düzeltildi; dizi uzunlukları tutarlı). `TEST_PLAN.md`: **UNTESTED-VIZ** tanımı + 10 maddelik manuel parite listesi (P1–P10; kaynak kolonlar = signals parquet) + **configs kilitli ayar tablosu** (EMA200/Donchian20/k3/buffer1.0/n10-m1.0/cooldown3/capped/P0xA0 — "Pine'da HESAPLANMAZ") + sembol eşleme dürüst notu (vendor farkı → parite ancak payload sembolünde). README §5 + model kartına tek satır: `pine/ = görselleştirme eki (UNTESTED-VIZ)`. **(3) Sınırlar:** hüküm/seçim/look etkisi YOK; suite **225/225** (yeni otomatik test YOK — TEST_PLAN manuel doğrulama aracı; pine yasak-kelime kilidi R11 ile gelecek ayın maint adayına not düşüldü). Pine derlemesi bu ortamda DOĞRULANAMAZ (TradingView yok) → UNTESTED-VIZ etiketi ilk kurulumda §2 listesinin elle uygulanmasını ZORUNLU kılar.

## TAMAMLANDI: M9-CADENCE — 4H mum kapanışı durum bildirimleri (2026-09-18, kullanıcı direktifi; watch_only)

Özet: `scripts/cadence_4h_status.py` (manuel tetik, **scheduler YOK**) → `reports/cadence/YYYY-MM-DD_HHMM.md`. Slotlar direktifle birebir (UTC+3): BIST30 11:00/15:00 (4H) + 18:00 (seans sonu); BTC/GOLD/SILVER 03/07/11/15/19/23 (4H); her bildirim son mum kapanışı + 15 dk tolerans. Şablon sabit: **SAĞLIK** (QC + tazelik + "+X bar" frozen/önceki bildirim baseline'ına göre) → **REJİM** (6'lı durum + long/short_ok) → **SEVİYE** (swing/Donchian destek-direnç + yapısal stop; BIST'te EMA200 bağlamı) → **MOMENTUM** (ATR-normalize ROC, σ) → **SİNYAL** (referans mumda ham→kapılar→final, capped akış + son 24h sayacı) → **EYLEM: YOK** (watch_only · GEÇTİ=0 · look #2 en erken 2026-12-17). Referans mum = "slot anında KAPALI olan son mum" (etiket+4h ≤ slot); **BAYAT bayrağı** takvim-duyarsız eşiklerle (BTC 6h, metaller/XU030 28h) — bayat bildirim "piyasa durumu İDDİASI içermez" damgalı. `--fetch`: rate kapısı ≥200 dk (`.state.json`) + TAM zincir (QC→regime→levels→momentum→signal — **demo2 dersi:** yalnız QC frame'leri tazelemiyor, düzeltildi). **QC RED → bildirim YAYIMLANMAZ, ⛔ SORUN NOTU üretilir (exit 3)** — §A fail-closed kuralının cadence karşılığı. Runbook'a **§A-cadence** eklendi (kurallar + restore politikası: fetch'li koşu sonrası `data/`+`reports/` checkpoint'e restore, `reports/cadence/` korunur, state baseline'a sıfırlanır; `last_fetch.log` gitignore). **Dürüstlük notu (direktif birebir uygulandı):** BIST 11:00/15:00 slotları v1.1 ızgara kapanışlarıyla (lokal 14:00/18:00) çakışmıyor → referans mum + yaşı açıkça raporlanıyor, slot revizyonu onaya bırakıldı.

İlk koşu kanıtı (3 dosya, 2026-09-18): **15:00** (BIST+CORE, fetch'siz): tüm varlıklar BAYAT damgalı — checkpoint verisi, dürüst yol. **19:00** (CORE, fetch'li): BTC **+14 bar** taze (son bar 2026-09-18 16:00 UTC, referans yaş 0.0h, rejim `trend_up|vol_high`, mom +4.48σ, referans mumda **final LONG sinyali** — raporlandı, EYLEM YOK); aynı koşuda Yahoo **rate-limit**'e takıldı (dünkü+bugünkü kesintili koşuların birikimi): GOLD/SILVER/BIST30 fetch'i "all fetch attempts failed" → QC **RED** — 19:00 dosyası bunu RED+BAYAT satırlarıyla DÜRÜSTÇE gösterdi (koşu, kapı eklenmeden ÖNCE gerçekleşti; kapı sonrası aynı durum yayımı durdurur). **18:00** (BIST, kapı sonrası): RED → ⛔ SORUN NOTU, exit 3 ✓. Koşu sonrası `data/`+`reports/` checkpoint'e restore edildi (frozen sha `--check` OK), `.state.json` baseline'a sıfırlandı (last_fetch_utc korundu). Suite **225/225** (yeni test yok — direktif kapsamında script manuel koşularla kanıtlandı; test matrisi R11 gelecek ay). Hüküm/seçim/veri etkisi YOK; look hakkı tüketilmedi.

## TAMAMLANDI: MAINT-BLOBFIX / M8 (2026-09-17, kullanıcı onaylı SON TEK patch — smudge-bağımsız hash testi)

Özet: `test_sha_normalization_crlf_bom_regression` yeniden tasarlandı — M7'deki ilk assert ("kaynak LF") working-tree smudge durumuna bağlıydı; Windows + OneDrive smudge'ında dosya CRLF yazılabiliyor (kullanıcı kanıtı: `checkout-index -a -f` sonrası working tree CRLF, `git status` TEMİZ, blob LF). Yeni tasarım: **(a)** kaynak içerik working tree'den DEĞİL **git blob'undan** okunur (`git show HEAD:configs/selected_cells.yaml`, bayt) ve `blob sha256 == final_verdict.md kayıtlı hash` assert'i KORUNUR (doc hash'leri LF, dokunulmadı); **(b)** CRLF+BOM normalizasyon assert'i **sentetik tmp kopya** üzerinde (kaynak: blob) — fixture-bayatlaması koruması (gerçekten CRLF+BOM mu + raw sha farklı mı) aynen kaldı; **(c)** working-tree smudge durumu assert DEĞİL **INFO satırı** (eol/BOM durumu + normalize==blob eşitliği raporlanır; canlı dosyanın normalize hash kilidi `test_final_verdict_content_and_live_hashes`'te duruyor). **Kanıt (yerel simülasyon):** working tree CRLF+BOM'a çevrildi (blob LF bırakıldı) → test 7/7 PASS, INFO: "CRLF içeriyor · BOM var · normalize(sha)==blob(sha): True"; ardından `git checkout` ile restore (LF ✓). Suite **225/225** (sayı değişmedi) + `pytest -q` 225 passed + `--check` EXIT 0. Kapsam: yalnız `tests/test_deliverables.py` (+`import subprocess`) ve bu blok — hüküm/seçim/veri etkisi YOK. Test artık git checkout'ta koşmayı gerektirir (CI'da her zaman geçerli; docstring'de notlu).

## TAMAMLANDI: MAINT-HASHFIX / M7 (2026-09-17, kullanıcı onaylı TEK patch — Windows-kırmızı/Linux-yeşil hash vakası)

Özet: maint_riskfix'te M5/M6 olarak anılan satır-sonu/hash normalizasyonu eksik kalmıştı; tamamlandı. **(a)** `.gitattributes` eklendi: `* text=auto eol=lf` + `*.parquet binary` + `*.png binary` — kök çözüm: metinler depoda VE working tree'de LF; binary'de eol dönüşümü asla (Windows CRLF checkout kaynağında kesilir). **(b)** `tests/test_deliverables.py → _sha()` artık içeriği NORMALİZE ediyor (UTF-8 BOM soy + CRLF→LF) sonra sha256; `final_verdict.md`'deki kayıtlı hash'ler LF üzerinden üretildiği için **DOKUNULMADI** (normalizasyon LF dosyada raw hash'i değiştirmez — testle sabit). **(c)** Regresyon testi `test_sha_normalization_crlf_bom_regression`: `selected_cells.yaml` içeriği tmp'ye **CRLF+BOM** ile yazılır → normalize sha == doc/live LF hash (fixture'ın gerçekten CRLF+BOM olduğu ve raw hash'in FARKLI olduğu da assert edilir — test bayatlarsa patlar). **(d)** Hash assert mesajları artık HESAPLANAN ve BEKLENEN değeri birlikte yazıyor. R09 kuplajı korundu: suite 224→**225** (deliverables 6→7) sayacı README/model_card/PROGRESS/test iğnesiyle SENKRON. Kapsam: `.gitattributes` (yeni) + `tests/test_deliverables.py` + doc sayaçları — motor/konfigürasyon/veri DEĞİŞMEDİ, hüküm/seçim etkisi YOK. Not: M4'te untrack edilen `data/raw/` parquet'leri `*.parquet binary` kuralıyla eol dönüşümünden kalıcı olarak korunur (Windows'ta force-add senaryosunda bile).

## TAMAMLANDI: MAINT-RISKFIX (2026-09-17, kullanıcı onaylı TEK patch — risk sicili azaltımları)

Özet: `docs/risk_register.md` siciline işli onaylı maddeler uygulandı (hüküm/seçim etkisi YOK; motor/konfigürasyon mantığı DEĞİŞMEDİ). **M1 requirements hijyeni (R02/R09):** `requirements.txt` saf ASCII'ye çevrildi (Windows cp1254 UnicodeDecodeError kanıtı yerelde görüldü) · `pytest==8.3.3` eklendi (CI girişi; house runner sayıları PROGRESS otoritesi kalır) · `scipy==1.17.1` pinlendi · `requirements.lock` (52 paket, tam freeze) + üretici `scripts/make_requirements_lock.py` (temiz venv politikası başlığında) · README/model_card/PROGRESS **224/224** senkronu (`test_deliverables` iğnesiyle birlikte — R09 kuplajı bilinçli korundu). **M2 minimal CI (R01/R07):** `.github/workflows/ci.yml` — push/PR/dispatch: py3.11 + pinned install + `pytest -q tests/` + house-runner döngüsü + `register_splits --check` + açık **frozen-sha bekçisi** (H17). Yerel doğrulama: pytest **224 passed** (20s), house **224/224**. CI'da `data/raw` bulunmaz (M4) → raw'a bağımlı tek test zarif SKIP verir, yeşil kalır. **M3 runbook v1.2 (R03/R04/R05):** §B **alpha-spending tarifesi** (kümülatif look 1–4: CI %95 · 5–8: %97.5 · 9+: %99; düzey §C log'undan OKUNUR, look ÖNCESİ kodda commit'lenir, yalnız SIKILAŞTIRIR; Aşama 9 = look #1, %95 ile tutarlı) · look başına **üniverse dondurma** (version+sha256 ön-kayda; üyelik değişirse yeni sürüm + **üyelik değişim logu** + karşılaştırılabilirlik notu) · §C zorunlu kayıt alanları · §A.3b **aylık raw-drift hash logu** (dosya başına sha256+satır; değişim → rapora — R04'ün kodsuz azaltımı) · `test_deliverables` v1.2 iğneleriyle kilitli. **M4 görünürlük/ToS kararı (R06 — KULLANICI KARARI, işlendi):** repo **PUBLIC KALIR**; `data/raw/` takipten ÇIKARILDI (`git rm -r --cached`, 70 dosya; yerel kopyalar durur; vendor ToS gereği yeniden DAĞITILMAZ) · README §7.0 **provenans notu** (kaynaklar + yeniden-çekim komutları) · `frozen/interim/processed` tekrarlanabilirlik için tracked KALIR. **Kapsam dışı bırakılanlar (kullanıcı):** R11 test matrisi (gelecek ayın maint'i) · metals kontrat-ay kaynağı (quant4h-M) · R08/R15 açık kaldı. Doğrulama: house 224/224 + pytest 224 passed + `--check` EXIT 0 + frozen 5/5 bayt-bayt aynı. Not: bu patch, henüz senkron edilmemiş **risk-audit commit'ini de içerir** (son senkron `2789bcf`).

## TAMAMLANDI: RİSK DENETİMİ (2026-09-17, salt-okunur) — `docs/risk_register.md`

Özet: Kullanıcı direktifiyle salt-okunur risk denetimi yapıldı (kod/config/veri DEĞİŞMEDİ; hüküm/tune yok; watch_only statüsü ve Aşama 9 hükmü aynı). **Tarama:** secret/.env sızıntısı HEAD+history → **TEMİZ (0 bulgu)** · requirements 9/10 tam pinli (`scipy>=1.14` gevşek, lock/hash yok) · `.gitignore` data/'yı ignore ediyor ama 306 data dosyası force-add tracked → yeni artefaktlar `git add`'i sessiz atlar (BOM var ama git tolere ediyor — `check-ignore --no-index` ile test edildi) · boyut sağlıklı (pack 77MiB, en büyük 4.6MB) · **doküman drift'i**: README/model_card "223/223" → fiilî 224/224 (test_deliverables iğnesi README'ye kilitli → ikisi birlikte güncellenmeli, onay bekliyor) · **test matrisi boşlukları**: çift taraflı gap+çakışma, sıfır-aralık bar fill'i, ısı==tavan sınırı, equity≤0, yıl-sınırı hafta rollover, L+S ortak fren · **lisans/ToS**: Yahoo (yeniden dağıtım yasağı) + scraping kaynakları + Binance klines PUBLIC repoda → R06 (P1). **DR tatbikatı:** temiz klon (`2789bcf`) + sıfır venv (3.8s) + `pip install -r requirements.txt` EXIT 0 (44s) + `pytest -q` → "No module named pytest" (olduğu gibi raporlandı; pytest bilinçli olarak requirements'ta YOK, house runner otorite) + house suite **224/224** + `register_splits --check` EXIT 0 → **DR BAŞARILI** (~1 dk). **Tohum liste: 8/8 DOĞRULANDI** (2'si genişletildi) + 7 yeni madde → sicil R01–R15 (önem/olasılık/azaltma/sahip). **TOP-5:** P1: (1) repo görünürlüğü/veri lisansı kararı [K], (2) minimal CI [O], (3) Look-2 öncesi alpha-spending politikası [O] · P2: (4) test matrisi maint patch'i [A-onayla], (5) fetch logu + metals kontrat-ayı kaynağı [O]. Tüm düzeltmeler ONAY BEKLİYOR; bu denetim hiçbir değişiklik yapmadı.

## TAMAMLANDI: BAKIM — test_splits frozen dokunulmazlığı (2026-09-17, kullanıcı onaylı; incident-3 teknik borcu KAPANDI)

Özet: `tests/test_splits.py` frozen snapshot'a ASLA yazmayacak şekilde düzeltildi — (1) `test_split_is_deterministic` + yeni regresyon testi `test_build_split_never_writes_real_frozen`: `RS.FROZEN_DIR` test süresince TMP'ye yönlendirilir; (2) iki tamper testi (`test_verify_detects_tampered_source`, `test_basket_split_verify_catches_tampering`) gerçek frozen/live yerine **TMP KOPYALAR** + fake yaml'a mutlak yol (`os.path.join(ROOT, abs)=abs`) üzerinde koşar — eski "gerçek dosyayı boz-geri yükle" deseni KALDIRILDI; (3) runner'a **frozen sha256 BEKÇİSİ**: her testin başında ve sonunda, ayrıca suite başında ve sonunda frozen haritası baseline ile karşılaştırılır; değişirse test/suite FAIL. Doğrulama: suite **224/224** (11→12 splits), frozen 5/5 bayt-bayt değişmedi, `register_splits --check` EXIT 0. Kapsam dışına dokunulmadı; Aşama 9 hüküm/seçim artefaktları (selected_cells.yaml, stage9 raporu, frozen'lar) ETKİLENMEDİ.

## TAMAMLANDI: watch_only aylık izleme 2026-09 (runbook §A) + runbook v1.1 düzeltmesi

Özet: İlk aylık izleme raporu üretildi → `reports/monitor/2026-09.md`. Zincir: canlı veri çekimi (BTC 19.895 bara, +7; metals/XU030 +1'er; son barlar 2026-09-17) → QC **4× AMBER, 0 ERROR** (RED kapısı geçildi) → regime→levels→momentum→signal raporları tazelenmiş (EXIT 0) → 30 günlük sayaçlar: **core+endekste 0 final sinyal** (ham 22+1'in tamamı pozisyon vekilince bastırıldı — Aşama 5'in bilinen capped-açlığı, arıza değil) · hisselerde zincir izni 182 bar · rejim son durum: BTC `trend_up|vol_normal` (long_ok), GOLD `range|vol_high`, SILVER `range|vol_normal`, XU030 EMA200 ÜSTÜ (bağlam izni AÇIK). `register_splits --check` EXIT 0 (drift BİLGİ; frozen'a dokunulmadı). **Üç vaka yaşandı ve raporda §6'ya işlendi:** (1) komutta eksik `--start` BTC raw cache'ini 1.000 bara kırptı → git'ten restore + tam çekim (kalıcı hasar YOK); (2) aynı gün ikinci `--no-cache` Yahoo rate-limit'iyle geçici RED üretti → taze cache ile AMBER'a dönüldü; (3) **KRİTİK:** drift varken suite koşulunca `test_splits.py` determinizm testi (`RS.build_split("BTC")`×2 → `_freeze`) frozen BTC snapshot'ını CANLI verinin üzerine yazdı — sha256 kilitleri YAKALADI (3 test dosyası RED), `git checkout -- data/` ile frozen+live checkpoint'e döndürüldü (frozen sha `aab99f83…` ✓, `--check` EXIT 0, suite 223/223); test düzeltmesi ONAY BEKLİYOR → teknik borca işlendi. **DÜZELTME:** `ops_runbook.md` v1→**v1.1** — §A komutuna `--start 2017-08-17`, veri çekim/cache politikası (aynı gün ikinci `--no-cache` YASAK), **restore adımı §A.5** (koşu sonrası `git checkout -- data/ reports/`; drift varken suite KOŞULMAZ; taze sayılar yalnız monitor raporunda taşınır → veri==rapor tutarlılığı), hisse kapsam notu ve aylık koşu log'u eklendi. Look hakkı TÜKETİLMEDİ (izleme ≠ look; 2026: 3/4 duruyor). Trade/hüküm/tune YOK. Testler: 223/223 (değişmedi).

## TAMAMLANDI: Aşama 11 — Teslimler + model kartı + watch_only runbook (ARAŞTIRMA-KAPALI)

Özet: Üç bağlayıcı belge üretildi ve test ile kilitlendi (`tests/test_deliverables.py`, 6 test): **(1)** `reports/final_verdict.md` — varlık başına hüküm + ÖLÜM NEDENİ ayrımı (BTC/sepet: **EDGE** — VALID expR negatif; GOLD/SILVER/core: **ÖRNEKLEM** — n<min, edge hükmü verilemez) + protokol günlüğü (split sha `9e1cf2fe…`, seçim dondurma sha `d7282b30…`, **look=1**, TEST yalnız GOLD/SILVER, 12 hücre yalnız TRAIN'de, eşikler `go_no_go` yaml'ı) + MC/duyarlılık kaydı + caveat'ler. **(2)** `models/model_card.md` — sistem NEDİR (katman tablosu) / NE DEĞİLDİR (canlı emir yok · tavsiye yok · **kanıtlanmış edge DEĞİL** · ML değil · tune edilmedi) · watch_only'nin bağlayıcı tanımı · **ml_policy_gate KAPALI** kaydı (gate koşulu "çekirdek OOS'ta GEÇERSE" sağlanmadı; Aşama 10 ancak look'larda GEÇTİ + kullanıcı yetkisiyle açılabilir). **(3)** `ops_runbook.md` — AYLIK sinyal izleme raporu (mevcut script zinciri; **trade/P&L/pozisyon YASAK**, şablon §A1) + ÇEYREKLİK ÖN-KAYITLI yeniden değerlendirme protokolü v1 (**maks 4 look/yıl**, erken look yasak, her look'ta YENİ split ön-kaydı v2/v3… + seçim dosyası arşivi, aynı kilitli eşikler/kümeler/fill kuralları — değişiklik yasağı, TEST look başına 1 kez) + **LOOK LOG'u** (1. kayıt: 2026-09-17, GEÇTİ=0; 2. look ≥2026-12-17) + **protokol ihlali tanımı ve yaptırımı** (ön-kayıtsız look → sayılar HÜKÜMSÜZ + damga + DÜZELTME bloğu) + veri hijyeni (drift BİLGİDİR, frozen'a dokunulmaz) + yeni hipotezler **YENİ PROJE** olarak aynı kapı pipeline'ına girer. **(4)** README §1 kapanış durumuna güncellendi + "Bu repo neyi KANITLADI/KANITLAMADI" bölümü eklendi (yöntem kanıtlandı · edge kanıtlanmadı).

**PROJE STATÜSÜ: ARAŞTIRMA-KAPALI · watch_only.** Sıradaki meşru işler YALNIZ: runbook §A aylık izleme, §B ön-kayıtlı çeyreklik look (2026 hakkı: 3/4 kaldı), §F yeni proje. Aşama 10 (ML) gate KAPALI. Yeniden seçim/tune/"bir bakış daha" YASAK (çoklu-test disiplini, kullanıcı onayı 2026-09-17). Testler: 217 → **223/223**.

## TAMAMLANDI: Aşama 9 — Walk-forward OOS + TEK seçim noktası + go/no-go (MAHKEME; protokol kilitli uygulandı)

Özet: `scripts/run_stage9.py` İKİ fazlı: `--phase select` (yalnız TRAIN; 12 kilitli hücre {P0..P3}×{A0..A2}; argmax TRAIN expR; n<50 → SEÇİM YOK, a-priori `P0xA0`) → seçim `configs/selected_cells.yaml`'a **frozen sha256 ile DONDURULARAK** yazılır; `--phase verdict` dosya yoksa/hash bozuksa/policy uyuşmazsa TEST'i **REDDER** (exit 2, test ile kilitli). VALID sağduyu: expR<0 veya CI üstü<0 → **KALDI, TEST KOŞULMAZ**. OOS havuzu = VALID+TEST; eşikler `go_no_go` (n≥100 core/150 basket · expR>0 · CI altı>0 · PF≥1.2 · maxDD≤%25). Pencereler ön-kayıtlı `used` blokları (purge 30 + embargo 12 düşülmüş); trade atfı GİRİŞ zamanına; gap'e düşen girişler dışlandı (BTC 2 · GOLD 2 · SILVER 2 · basket 14). Rapor: `reports/stage9_oos_verdict.md|json`.

### Aşama 9 HÜKÜM TABLOSU (TEST 1 KEZ koşuldu; seçim hiç dokunmadı)

| varlık | hücre | seçim | TRAIN | VALID | TEST | OOS | **HÜKÜM** | mod |
|---|---|---|---|---|---|---|---|---|
| BTC | `P2xA2` | **YAPILDI** (n=175, expR +0.2913) | +0.2913 | n=7, **−0.3207** ❌ | **KOŞULMADI** | — | **KALDI** | watch_only |
| GOLD | `P0xA0` | YOK (TRAIN n=12 <50 → ZAYIF) | +0.4334 | n=6, +1.3579 ✅ | n=10, +0.3430 | n=16 <100 | **ZAYIF (örneklem)** | watch_only |
| SILVER | `P0xA0` | YOK (TRAIN n=13 <50) | — | n=8, +0.9021 ✅ | n=11, −0.2790 | n=19 <100 | **ZAYIF (örneklem)** | watch_only |
| BIST30 sepet | `P0xA0` | YOK (TRAIN n=0 — 500 bar rejim ısınması, BIST grid'inde ≈250 iş günü, TRAIN penceresinin TAMAMI) | — | n=74, **−0.0569** ❌ | **KOŞULMADI** | — | **KALDI** | watch_only |
| CORE agregat | (üye hücreleri) | — | — | — | — | n=42 <100 | **ZAYIF (örneklem)** | watch_only |
| PORTFÖY-sepet | — | — | — | — | — | n=74 <150 + üye KALDI | **KALDI** | watch_only |

**SONUÇ: GEÇTİ = 0 → paper/observe adayı YOK; tüm varlıklar `watch_only` (edge hükmü verilmedi).** Bu hüküm Aşama 1c/6/7'nin tüm uyarılarıyla tutarlıdır: TEST pencereleri kısa (BTC 159 gün), dönem tek yönlü, örneklem yetersiz. Monte Carlo (OOS dizileri, B=1000, seed 42): P(maxDD>%25)=0.00, P(ruin<%50)=0.00 — küçük örneklemde bu bir GÜVENLİK KANITI DEĞİLDİR, dağılım bilgisidir. Duyarlılık: BTC seçili `P2xA2` (+0.2913) − en iyi komşu `P3xA2` (+0.2739) = +0.0174 → **overfit sivrilik bayrağı YOK** (gradyan yumuşak). MC/ruin tanımları raporda belgeli.

Dürüst notlar: (1) verdict fazı, portföy-sepet SATIR etiketi düzeltmesi için 1 kez yeniden üretildi — TEST sayıları deterministik ve birebir aynıdır (TEST'e ikinci şans VERİLMEDİ; BTC/basket TEST'i hiç koşulmadı). (2) KALDI üyeler (BTC, basket) core/basket agregatlarına YALNIZ VALID trade'leriyle dahil; gerekçeye işlendi. (3) **Onaylı senkron:** `max_open_positions` balanced 3→6 (`user_decisions.yaml` active+preset VE `config.py` — Aşama 8 direktifi). (4) Tek fold; çok katlı walk-fold ve daha uzun metaller geçmişi (2.4 yıl limiti) güç artırmadan sonuç değişmez — veri genişletme (ücretli/kurumsal kaynak) ancak kullanıcı kararıyla.

Testler: 207 → **217/217** (+10 `test_stage9.py`: pencere sırası/boşluklar, atama ayrıklığı, seçim argmax+min50+tie-break, sağduyu kuralları, go/no-go eşikleri, MC determinizmi, komşu/overfit, **dondurma RED kilidi**, teslimat artefakt hash tutarlılığı, yaml-config senkronu). Sırada: Aşama 10 (opsiyonel ML — GEÇTİ=0 olduğu için `ml_policy.gate` gereği DEVREYE GİREMEZ) ve Aşama 11 (çıktılar/model kartı) — İKİSİ DE YETKİ BEKLİYOR.

## TAMAMLANDI: Aşama 8 — Risk modülü + portföy simülatörü (tavanlı vs tavansız, IN-SAMPLE)

Özet: `src/quant4h/risk/limits.py` (RiskLimits: tavan kümesi + fail-closed doğrulama + `from_profile`; banka listesi DONMUŞ üniversalden `sector=="banka"` → AKBNK/GARAN/ISCTR/VAKBN/YKBNK) + `src/quant4h/risk/simulator.py` (event-driven portföy simülatörü: global timeline = akış timestamp BİRLEŞİMİ; **P0×A0 kilitli** — `profile!="P0"` → ValueError; fill kuralları Aşama 6 motoruyla birebir — `_close_trade` TEK kaynak; t+1 icra · D6 · H35 · çift taraf maliyet; ORTAK realized equity; boyutlama = risk/stop-mesafesi + kaldıraç kıskacı; **tavanlar YALNIZ GİRİŞTE, çıkışlara dokunmaz**) + `scripts/run_risk_report.py` → `reports/stage8_risk.md|json`. Bağlayıcı tavanlar (direktif 2026-09-17): toplam 6 · BTC 2 · GOLD 1 · SILVER 1 · sepet 3 · metals TEK kova ısı ≤1×rpt · basket ısı ≤3×rpt · hisse ≤1×rpt · banka ≤2 eşzamanlı · günlük %2 / haftalık %5 (realized baz, fail-closed) · 4 ardışık kayıp → 20 bar fren.

### Aşama 8 sonuç özeti (in-sample, balanced %0.5, 100k)

| ölçü | TAVANSIZ | TAVANLI |
|---|---:|---:|
| trade | 423 | **247** (red: basket_concurrent 137 · metals_heat 29 · fren 10) |
| net getiri (mtm) | +16.37% | **+17.68%** |
| max DD (mtm eğri) | −17.66% | **−7.76%** |
| exposure | %70.2 | %68.5 |
| tepe eşzamanlı / metals ısı / basket ısı / banka | 28 / %1.00 / %13.00 / 5 | **5 / %0.50 / %1.50 / 1** (hepsi tavan altında) |

Varlık bazında (TAVANLI, expR R-bazlı): BTC 177 trade +0.199 CI [−0.015,+0.405] · GOLD 17 ⚠ +0.476 · SILVER 18 ⚠ +0.018 · BASKET 35 ⚠ +0.126 (sepet eşzamanlı 3 tavanı trade sayısını 172→35'e indirir; hisse appendix'i kabul kriteri 6 gereği yalnız tanısal). Günlük/haftalık limitler bu örneklemde HİÇ tetiklenmedi (0 red).

### Aşama 8 kilitleri

1. **Regresyon kilidi:** TAVANSIZ koşu Aşama 7 P0×A0 hücreleriyle birebir (BTC 187/+0.2064 · GOLD 30/+0.6259 · SILVER 34/+0.0022 · BASKET 172/+0.077); `run_risk_report.py` exit code bu kilide bağlı. Tek-akış tavansız sim == Aşama 6 motoru alan-alan (test).
2. **Tavan ihlali SIFIR:** gerçek verili tavanlı koşuda [entry,exit) süpürmesiyle doğrulandı — toplam ≤6, BTC ≤2, GOLD/SILVER ≤1, sepet ≤3, metals birleşik ısı ≤%0.5, basket ısı ≤%1.5, banka ≤2 (test).
3. **Fren regresyon testli:** 4. ardışık kayıptan sonra 20 bar giriş yok; limitsiz koşuda aynı sinyal girer (test).
4. **Tavanlar çıkışı değiştirmez:** capped trade'lerin çıkış bar/fiyat/sebebi unlimited karşılığıyla birebir (test).
5. Dürüst notlar: günlük/haftalık limitler REALIZED P&L bazlıdır (mtm bazlı varyant ayrı onay ister) · `max_correlation` ayrıca zorlanmadı (metals tek kova zaten sınırlar; günlük korelasyon limiti Aşama 9 bağlamı) · **Stage 0 `RiskProfile.max_open_positions=3` bu direktifle SUPERSEDE edildi (toplam 6)** — yaml'a dokunulmadı, kayıt buradadır.
6. Testler: 192 → **207/207** (+15 `test_risk.py`).

**HÜKÜM ÜRETİLMEZ:** bu rapor in-sample'dır; go/no-go Aşama 9 OOS + `user_decisions.yaml → go_no_go` eşikleriyle. Aşama 9 YETKİ BEKLİYOR.

## TAMAMLANDI: Aşama 7 — Çıkış mimarisi grid'i (esnek TP + alternatif anchor'lar; KARŞILAŞTIRMA, SEÇİM YOK)

Özet: `ExitConfig.profile` enum'ı eklendi: **P0** baseline TS90+TP3R (varsayılan, Aşama 9'a kadar) · **P1** partial+runner (1R'de %50 + stop→BE + runner chandelier ATR×3; TS/TP YOK — şartname gereği) · **P2** trailing (girişten chandelier ATR×3, ratchet, TP YOK, TS90 emniyet) · **P3** breakeven (1R→BE + TP3R + TS90). Şartname sabitleri KİLİTLİ (`partial_frac=0.5`, `breakeven_trigger_r=1.0`, `chandelier_atr_mult=3.0`; küme/ profil dışı → ValueError). Stop anchor'ları `src/quant4h/backtest/anchors.py`: **A0** swing−1.0×ATR (mevcut, no-op) · **A1** Donchian(20) ters bandı · **A2** swing−0.5×ATR (`levels.add_structural_stop` buffer 0.5 ile YENİDEN kullanıldı — kilitli küme içi). Anchor override SİNYAL ÜRETİMİNDEN ÖNCE: `stop_valid` kapısı + capped proxy + motor AYNI stop'u görür. Grid: `scripts/run_exit_grid.py` → `reports/stage7_exit_grid.md|json` — 4 profil × 3 anchor × {BTC, GOLD, SILVER, basket(28 hisse)}; **tüm hücreler IN-SAMPLE etiketli, SEÇİM YOK** (seçim yalnız Aşama 9, OOS, core-only).

### Aşama 7 kilitleri ve bulguları

1. **P0×A0 regresyon kilidi:** grid'in P0×A0 hücreleri Aşama 6 baseline'ını (`reports/backtest_baseline.json`) birebir yeniden üretiyor (n_trades/win/PF/expR/maxDD/total_cost; script exit code bu kilide bağlı, UYUŞMAZSA 1). Motor refactor'ü baseline'ı DEĞİŞTİRMEDİ.
2. **D6 ÇÖZÜLDÜ:** bar `t` içinde kapanan pozisyonun ardından bar `t` AÇILIŞINDA yeni giriş YASAK (`exited_bar` kapısı) + `test_same_bar_exit_blocks_same_bar_entry`. Regresyon kilidi, bu kapının mevcut sonuçları değiştirmediğini kanıtladı (capped akışta erişilemezdi; artık test ile kilitli).
3. **Nedensellik:** BE/trailing güncellemeleri bar SONUNDA yazılır, bir SONRAKİ bardan geçerli (bar içi sıkılaştırma YOK); chandelier yalnız KAPALI barların HH/LL'si + `atr[t]` ile hesaplanır; P2 truncation (look-ahead silme) testi GEÇTİ. P1'de aynı barda stop+1R çakışırsa **STOP kazanır, partial YAPILMAZ** (kabul kriteri 2).
4. **Muhasebe:** partial tek Trade satırında (pozisyon başına 1 satır; `partial_*` alanları); maliyet bacaklara bölünür, TOPLAM = one_way × (giriş + tüm çıkış notional'ları) — test ile kilitli; `equity_after − equity_before == net_pnl`.
5. **Tanımlayıcı özet (ÖNERİ DEĞİL, in-sample expR):** BTC en iyi `P3xA2` +0.262 / en kötü `P1xA1` +0.109 · GOLD en iyi `P0xA0` +0.626 (⚠️ 30 trade) / en kötü `P2xA1` +0.190 · SILVER en iyi `P3xA2` +0.214 / en kötü `P2xA2` −0.135 · BASKET en iyi `P3xA2` +0.145 / en kötü `P2xA2` −0.062. Mimari gözlem: **P2 tutma süresini ve maruziyeti dramatik kısaltıyor** (BTC ort. 59.6→17.4 bar, exposure %57→%17, maxDD −7.05%→−2.80%) — maliyet/tur-over etkisi Aşama 8-9'da değerlendirilecek. P1'de TS olmaması tutmayı uzatıyor (BTC 75.7 bar).
6. **D1/D4/D5 işlendi (kullanıcı onayı 2026-09-17):** `user_decisions.yaml`'a `go_no_go` (OOS expR>0 + CI altı>0 · PF≥1.2 · maxDD≤%25 · min trade core≥100/basket≥150; değerlendirme Aşama 9) + `stage6_acceptance_criteria` (2/3/4/6/7/8 koddan yeniden kuruldu; **1 ve 5 KAYIP — reserve, uydurulmadı**) eklendi; `stage_gate` senkronlandı; `basket_policy.split_preregistration` v1.1 sayılarına düzeltildi (superseded_note ile).
7. Testler: 173 → **192** (+19 `exit_profiles`: enum/sabit/anchor kilitleri, D6, P1 partial+gap+çakışma+chandelier+TS-yok, P2 ratchet+TS90, P3 BE+TP+next-bar, short simetri, maliyet bölüşümü, look-ahead truncation, P0×A0 gerçek-veri regresyonu).

Caveat'ler aynen geçerli: in-sample · risk modülü YOK (Aşama 8: kova ısısı/korelasyon/tavanlar) · survivorship bias (sepet) · metallerde roll belirsizliği · bu tablolardan KARAR ÜRETİLMEZ.

## TAMAMLANDI: Aşama 6 DENETİMİ (2026-09-17, yeni oturum devralma — kod değişmedi)

Özet: Kullanıcı yetkisiyle (2a–2d) Aşama 6 çıktıları şartnameye karşı denetlendi: `reports/stage6_audit.md`. **Fill-kuralı denetimi 10/10 UYUMLU** (capped primary · open[t+1] · aynı-bar STOP öncelikli · gap fill · çift taraf maliyet · H35 kilidi testli · bootstrap CI seed=42/B=1000 · basket agregasyonu ana/hisse appendix · tune kilidi). **Go/no-go: GENEL NO-GO** (beklenen): Aşama 6 in-sample; OOS bacağı Aşama 9'da. In-sample: BTC GEÇTİ (CI altı +0.006 sınırda) · GOLD İSTATİSTİKSEL ZAYIF (30<100) · SILVER KALDI (CI 0'ı içeriyor, PF 0.935) · sepet KALDI (CI −0.133, PF 0.931; 172≥150 trade tamam). **Sapma listesi D1–D8** raporda; en kritikleri: go/no-go eşikleri + "kabul kriteri 1–8" listesi repoda KAYITLI DEĞİL (D1), `user_decisions.yaml` stage_gate (D4) ve basket_policy split sayıları (D5) BAYAT — düzeltmeleri ONAY BEKLİYOR, tek satır değiştirilmedi. **2d:** eksik `bist30_basket_4h_frozen.attrs.json` deterministik ÜRETİLDİ (`scripts/make_basket_attrs.py`, tarih damgasız, `--check` modlu) + `tests/test_basket_attrs.py` 6/6; frozen parquet sha256 değişmedi, `register_splits.py --check` önce ve sonra EXIT 0. **Suite: 167 → 173/173 PASS** (11 dosya).

## DÜZELTME (2026-09-17, yeni oturum devralma denetimi — kullanıcı onaylı)

1. **Bayat AŞAMA DURUM LİSTESİ:** Tabloda Aşama 3, 4 ve 6 satırları "⬜ YETKİ BEKLİYOR" olarak kalmıştı; oysa üçü için de bu dosyada TAMAMLANDI bloğu var (Aşama 6 denetimi de bunu teyit etti). Satırlar ✅ olarak GÜNCELLENDİ. Sıradaki yetki bekleyen aşama: **7 (esnek kâr alma)** ve 5b.
2. **KARAR 6 bloğundaki satır sayısı:** "bist30_basket_4h_frozen.parquet (**60.416 satır**)" ifadesi v1.0 dönemindendir (ince barlar elenmeden önce, grid 2.158). Gerçek frozen snapshot (policy **v1.1**, H27 ince-bar elemesi sonrası): **40.206 satır**, grid **1.436**, TRAIN 437 (medyan 426) · VALID 395 (385) · TEST 436 (425). sha256 (`218de18b…`) `splits_preregistered.yaml` kilidiyle birebir → VERİ SAĞLAM, metin bayattı. KARAR 6 blok metni tarihî kayıt olarak silinmedi; bağlayıcı sayı kaynağı `configs/splits_preregistered.yaml` (v1.1)'dir. Aynı v1.0 sayıları `user_decisions.yaml → basket_policy.split_preregistration` içinde de duruyor (D5 — senkronizasyonu onay bekliyor).

## KURAL: Patch-tabanlı senkron (2026-09-17, kullanıcı onaylı)

Sandbox'tan `git push` YOK (yetki yok); token sohbete ASLA girmez. Yeni senkron kuralı:
1. Her aşama/iş-birimi bitiminde: PROGRESS bloğu + **local commit**.
2. Patch üret: `git format-patch <son-senkron-commit>..HEAD --stdout > patches/stageN.patch` (bu birim: `patches/stage6_audit.patch`; son senkron commit: **`b58144b`**).
3. Kullanıcı patch'i indirir, local repoda `git am` + `git push` yapar → yeni son-senkron commit, uygulanan patch'in son commit'i olur (bir sonraki format-patch aralığı oradan başlar).
4. `patches/` klasörü repo dışında tutulur (untracked; yalnız teslimat artefaktı).
5. **Ortam notu (2026-09-17'de ölçüldü):** sandbox, turlar arasında `.git` geçmişini KORUMUYOR (yalnız normal dosyalar kalıcı). Bu yüzden her tur başında `.git` remote'tan yeniden kurulur (`git clone` → `.git` kopyala); local commit'ler tur içinde geçerlidir ve KALICI TESLİMAT ARACI `patches/*.patch` dosyalarıdır. Kullanıcı patch'i uygulayıp push ettikten sonra bir sonraki tur aynı commit'leri remote'tan görür.

## TAMAMLANDI: Aşama 6 — Baseline backtest (gerçek çıkış motoru + maliyet)

Özet: `src/quant4h/backtest/engine.py` + `scripts/run_backtest.py` → `reports/backtest_baseline.md|json`, `reports/trades_*.csv` (4), `reports/figures/equity_*.png` (4). **Çıkış motoru:** dondurulmuş yapısal stop + time-stop **90 bar** + basit TP **3R**; aynı barda çakışma → **STOP** (pesimist); gap'lerde stop **open**'dan (aleyhimize), TP **open**'dan (lehimize ama gerçekçi), time-stop kapanıştan. Giriş `open[t+1]`; maliyet (komisyon + yarım spread + slippage) **iki tarafa da**. Geçerli stopu olmayan pozisyon **ASLA** açılmıyor (H35 kilidi, `rejected_no_valid_stop` sayacı raporlanıyor). Primary akış **CAPPED**; `strict` yalnız tanısal, `cooldown_only` backtest EDİLMEDİ. Parametreler **VARSAYILAN**, tune YOK (`ExitConfig(tune_now=True)` → `ValueError`; aday kümeler `{60,90,120}` × `{2R,3R,4R}` Aşama 9'a kilitli).

### Aşama 6 sonuç tablosu (balanced %0,5 risk, 100.000 başlangıç, maliyet dahil)

| Varlık | trade (L/S) | win % | PF (net) | expectancy (R) | expR CI95 | P(expR>0) | ort. tutma | max DD | **net getiri** | **buy&hold net** | maliyet | zayıf |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
| BTC | 187 (100/87) | 40,1 | 1,31 | +0,206 | **[+0,006, +0,422]** | 0,98 | 59,6 bar | −7,05% | **+15,47%** | **+1.636,8%** | 4.904 | hayır |
| GOLD | 30 (23/7) | 56,7 | 2,67 | +0,626 | [+0,093, +1,194] | 0,99 | 67,8 bar | −2,12% | **+8,66%** | +86,3% | 895 | ⚠️ EVET |
| SILVER | 34 (26/8) | 41,2 | 0,93 | +0,002 | **[−0,419, +0,428]** | 0,49 | 60,4 bar | −2,88% | **−0,64%** | +136,6% | 616 | ⚠️ EVET |
| **BIST30 sepet** | 172 (28 hisse) | 38,4 | 0,93 | +0,077 | **[−0,133, +0,283]** | 0,76 | 56,0 bar | −0,78% (equity) | **−0,14%** (equity) | hisse medyanı +79% | 10.348 | hayır* |

\* Sepet 172 trade ile eşik üstü ama **hisse başına medyan yalnız 6 trade** (min 3, max 9) → hisse bazlı hiçbir sonuç anlamlı değil; 28/28 hisse `İSTATİSTİKSEL ZAYIF` bayraklı ve appendix'te.
Çıkış karışımı: BTC {time_stop 80, stop 80, TP 27} · GOLD {time_stop 16, stop 7, TP 6, eod 1} · SILVER {stop 17, time_stop 16, TP 1} · sepet {stop 85, time_stop 61, TP 20, eod 6}.

### DÜRÜST SONUÇ (raporun §0'ı)

1. **Hiçbir varlık buy&hold'u geçemedi, çoğu açık farkla geride.** Bu bir hata değil: ölçülen dönem (2024-2026) şiddetli boğa piyasası ve sistem %0,5 risk/işlem + düşük maruziyetle çalışıyor; buy&hold ise TAM maruziyet.
2. **Expectancy pozitif ama güven aralıkları geniş.** BTC CI 0'ı dışlıyor (+0,006…+0,422, 187 trade) ama etki küçük; GOLD CI 0'ı dışlıyor fakat yalnız 30 trade; **SILVER CI 0'ı İÇERİYOR → sıfırdan ayırt edilemez**; sepet de 0'ı içeriyor.
3. **Maliyet sonucu değiştiriyor ama core'da tersine çevirmiyor** (BTC brüt +20,37% → net +15,47%). Sepette net ≈ 0 → maliyet öncesi de anlamlı pozitif değil.
4. **Bu tablo in-sample'dır**: train/valid/test ayrımı bu raporda UYGULANMADI. OOS ölçümü Aşama 9'da, ön-kayıtlı split'lerle yapılacak.
> **Bu parametre setiyle sistem "para kazanıyor" DENEMEZ; "kaybediyor" da denemez — örneklem yetersiz ve dönem tek yönlü.** Aşama 7 + Aşama 9 olmadan bu tablo üzerinden HİÇBİR karar verilmemelidir.

## NOT: Aşama 5 sinyal sayıları GEÇİCİDİR

Aşama 5'te raporlanan sinyal sayıları (`reports/signal_report.md`) **pozisyon vekiline** dayanıyordu ve **GEÇİCİ** olarak işaretlenmişti. Aşama 6'da gerçek çıkış motoru (stop + time-stop 90 + TP 3R) yazıldı; primary akış olarak **CAPPED** varyantı kullanıldı. `strict` akış (yalnız stop vekili) Aşama 5'te ölçüldüğü gibi sinyalleri açlıktan öldürüyor (CORE 1.012 ham → 9 final) ve **yalnız tanısal** olarak taşınıyor. Aşama 7'de esnek kâr alma (partial + runner, trailing, breakeven) geldiğinde her iki akışın sayıları da YENİDEN üretilecek; bu yüzden Aşama 5 raporundaki hiçbir sayı kalıcı kabul edilmemelidir.

## TAMAMLANDI: Aşama 5 — Giriş tetiği ve sinyal montajı

Özet: `src/quant4h/strategy/signals.py` + `scripts/run_signal_report.py` → `reports/signal_report.md`. **Tetik (yeni indikatör YOK):** LONG `close > max(high[t-20..t-1])`, SHORT (yalnız core) `close < min(low[t-20..t-1])`. **Açık shift kararı:** `donchian_high` kolonu ZATEN `rolling(20).max().shift(1)` olduğu için tetikte İKİNCİ bir `shift(1)` **UYGULANMADI** — uygulansaydı pencere 21 bara çıkar ve "önceki 20 KAPANMIŞ bar" kriteri bozulurdu. Eşdeğerlik, ham `high` serisinden elle hesaplanarak `test_trigger_equals_manual_20_bar_breakout` ile kilitlendi. **İcra:** sinyal bar `t` KAPANIŞINDA, giriş bar `t+1` AÇILIŞINDA (`execution_price = open[t+1]`); `signal_bar_close` P&L'de kullanılmaz; `t+1` yoksa `execution_valid=False` (uygulanamaz sinyal). Look-ahead silme testi GEÇTİ. **Cooldown:** `cooldown_bars=3` → off-by-one sözleşmesi "giriş barı + 3" = sinyal barı `s` ise ilk yeniden sinyal `s+4` (12 saat); **tüm 31 varlıkta ölçülen `min_signal_gap_bars=4`** ile doğrulandı. Pozisyon açıkken yeni sinyal YOK.

### ⚠️ AŞAMA 5'İN ANA BULGUSU: pozisyon vekili sinyalleri açlıktan öldürüyor

Yapısal stop girişten ~2,6–3,2 ATR geride olduğu için fiyat onu **yıllarca** ihlal etmeyebiliyor. Pozisyon vekili (yalnız dondurulmuş stop'un bar içi ihlali) neredeyse hiç çıkmıyor → pozisyon sürekli açık kalıyor ve ham sinyallerin büyük bölümü bastırılıyor. **Bu bir kod hatası değil**; Aşama 3'te öngörülen "yapısal stop geniş" sonucunun ölçülmüş kanıtı ve **Aşama 7'nin (partial+runner / trailing / time-stop) neden zorunlu olduğunun** göstergesi. Bu yüzden rapor ÜÇ akışı birlikte verir ve sayılar **GEÇİCİ** olarak işaretlenir.

| Akış | Tanım | CORE (BTC+GOLD+SILVER+XU030) | 28 HİSSE |
|---|---|---|---|
| **A) strict** | şartname kuralı: pozisyon açıkken sinyal yok + cooldown 3 | ham 1.012 → **final 9** (short 6) · poz açık ~%90 · bastırılan 1.422 | ham 960 → **final 74** · bastırılan 886 |
| **B) capped** | A + zorunlu time-stop (90 bar) | **final 158** (short 106) · ort. aralık 33 gün | **final 172** · ort. aralık 94 gün |
| **C) cooldown_only** | pozisyon takibi yok, yalnız cooldown | **final 592** (short 282) · bastırılan(cooldown) 563 · ort. aralık 9,2 gün · **min_gap=4** | **final 568** · bastırılan 392 · ort. aralık 26,7 gün · **min_gap=4** |

Varlık bazlı (strict long/short): BTC 3/3 · GOLD 1/0 · SILVER 3/0 · XU030 2/3 (**trade edilmez, yalnız tanısal**) · hisselerde short **0** (28/28 ✅ LONG-ONLY). Uygulanamaz sinyal: **0**.
Yıllara göre (28 hisse, cooldown_only): 2024 → 44 · 2025 → 264 · 2026 → 260. 2024'ün düşük olması **rejim ısınmasının** (ilk 500 bar etiketsiz) doğrudan sonucudur — bu, hisse başına in-sample tuning yasağının gerekçesini bir kez daha doğrular.

### Zincir (strict) ve ek halka kararı

`long = long_regime_ok ∧ longs_allowed(BIST) ∧ ~non_tradable ∧ return_valid ∧ momentum_ok ∧ trigger_long ∧ **stop_valid_long**`
`stop_valid` halkası şartname listesinde açıkça YOKTU; **fail-closed** ilkesi gereği EKLENDİ (dondurulacak stop yoksa pozisyon açılamaz, dolayısıyla sinyal de üretilemez). Kaldırmak için `require_valid_stop=False` verilebilir. Bir kapı kolonu frame'de yoksa sonuç **False**'tur (test ile kilitli).

## TAMAMLANDI: Aşama 4 — Momentum onayı (çift onayın 2. bacağı)

Özet: `src/quant4h/features/momentum.py` — **TEK kural**: `mom = (close/close.shift(n) − 1) / (ATR14/close.shift(n))`, yani "son n barda fiyat ATR cinsinden kaç birim yer değiştirdi". Varsayılan **n=10, m=1.0 ATR**; long `mom > +m`, short `mom < −m` (short yalnız core). Aday kümesi `{n: 5,10,20} × {m: 0.5,1.0,1.5}` **Aşama 9'a kilitli** — küme dışı değer hem `MomentumConfig.__post_init__` hem `add_momentum` içinde `ValueError`. **RSI/MACD/Stochastic/MFI/OBV/CCI/Williams YOK** (test, `ast` ile docstring'i hariç tutup yalnız çalışan kodu tarıyor). Ölçü birimsiz olduğu için fiyatı 1000× çarpmak `mom`'u değiştirmiyor (test ile kilitli). Formül elle hesapla birebir doğrulandı. Look-ahead silme testi **GEÇTİ**: son 400 bar silindiğinde geçmiş `mom`/`ok` değerleri birebir aynı.

Özet (guard + zincir): Guard fail-closed — ATR NaN/≤0, `close[t−n]` NaN/≤0, `non_tradable`, `return_valid=False` ve ilk n bar (warmup) → `momentum_valid=False` ve `momentum_ok=False`; guard asla "0 varsay" demiyor (test: ATR'yi tümüyle NaN yapınca hiçbir bar onay almıyor). **ATR politikası:** kolon varsa KULLANILIR (Aşama 2 ile aynı seri), yalnızca yoksa hesaplanır — tamamen NaN olsa bile yeniden hesaplanmaz, çünkü bu guard'ı sessizce atlatırdı (bulunan hata H32). Zincir: `long_final_ok = rejim ∧ bağlam(BIST) ∧ tradable ∧ return_valid ∧ seviye ∧ momentum`; bir kapı kolonu frame'de YOKSA sonuç False (fail-closed, test ile kilitli).

### Aşama 4 sonuç tablosu (n=10, m=1.0 — VARSAYILAN, optimize edilmedi)

| Varlık | bar | mom geçerli % | **long geçiş %** | short geçiş % | bant [10,60] | rejim→seviye→**momentum** | **FINAL long** | % | FINAL short |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| BTC | 19.888 | %99,9 | **%30,5** | %26,7 | ✅ | 8.489 → 8.244 → **3.206** | **3.206** | %16,12 | 2.412 |
| GOLD | 3.606 | %98,8 | **%37,2** | %26,8 | ✅ | 1.932 → 1.834 → **816** | **816** | %22,63 | 281 |
| SILVER | 3.606 | %98,8 | **%36,0** | %27,3 | ✅ | 1.615 → 1.569 → **661** | **661** | %18,33 | 279 |
| XU030 (bağlam) | 1.435 | — | %43,0 | — | ✅ | — | trade YOK | — | — |
| **28 hisse** | 40.206 | — | **medyan %37,7** (%29,8–%43,3) | üretilmez | ✅ **28/28** | ör. AEFES 356→316→**144** | **5.042** | **%12,54** | politika: 0 |

**Kalibrasyon: BANT DIŞI VARLIK YOK** (28/28 hisse + 3 core + XU030 hepsi [%10, %60] içinde) → bayrak yok, `TUNE` yapılmadı. Bant dışı durum için mekanizma hazır: `calibration_flag` metni üretiliyor ve `MomentumConfig(tune_out_of_band=True)` config seviyesinde `ValueError` veriyor (otomatik ayarlama kod yolu olarak kapalı).

## TAMAMLANDI: Aşama 3 — Yapısal seviyeler ve dondurulmuş yapısal stop

Özet: `src/quant4h/features/levels.py` — **yeni indikatör YOK**, yalnızca 3 kavram: k-bar fraktal swing (k=3, onay gecikmesi **k+1=4 bar**), Donchian(20) (**son 20 KAPANMIŞ bar**, mevcut bar pencereye girmez), ATR buffer'lı yapısal stop (long = onaylı `swing_low − 1.0×ATR`; short yalnız core = `swing_high + 1.0×ATR`). Buffer aday kümesi `{0.5, 1.0, 1.5}` **Aşama 9'a** bırakıldı, şimdi seçim YOK (küme dışı buffer `ValueError`). Stop **girişten önce** belli ve `FrozenStop` (frozen dataclass) ile **DONDURULMUŞ**: `widen/move_against/relax` → `StopImmutabilityError`; yalnızca pozisyon lehine `tighten()` YENİ nesne döndürür ve `initial_stop` korunur. Look-ahead testi geçti: son 300 bar silindiğinde tüm seviyeler birebir aynı. Rapor: `reports/levels_report.md`.

Özet (anchor kısıtı + kritik tasarım kararı): `return_valid=False`, `non_tradable=True`, `halt_or_limit_flag=True` ve OHLC'si bozuk barlar ne swing ne Donchian anchor'ı olamaz (FLAG-ONLY sürüyor; veri silinmiyor). **Ölçülen kritik bulgu:** ince "açılış anı" barı tutulduğunda 28 hissede **swing=0, Donchian=0, stop=0** oluyordu — çünkü BIST'in 3 barlık grid'inde k=3 fraktalın 6 komşusu HER ZAMAN en az bir anchor-uygun olmayan bara denk geliyordu. Çözüm: `AssetSpec.min_source_bars_per_target` alanı eklendi ve BIST için **3** yapıldı (≥%75 kapsama) → ince bar hiç üretilmiyor, günde **2 TAM bar** (07/11 UTC) kalıyor. Bedeli caveat olarak kayıtlı: 09:30-10:00 açılış hareketi 4H'de temsil edilmez. Bu değişiklik BIST30 bar sayısını 2.158 → **1.435**'e indirdi; split ön-kaydı bu yüzden **policy v1.0 → v1.1** olarak YENİDEN üretildi ve v1.0 `configs/splits_preregistered.v1.0.archived.yaml` içinde SAKLANDI (silinmedi).

### Aşama 3 sonuç tablosu (buffer = 1.0 ATR, varsayılan)

| Varlık | bar | anchor_ok % | swing_low / high | Donchian % | breakout ↑ / ↓ | stop_long (ATR) | stop_long (% fiyat) | planlanabilir long % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 19.888 | %100,0 | 2.014 / 2.014 | %99,9 | 1.449 / 1.216 | **2,58** | %4,11 | %92,1 |
| GOLD | 3.606 | %99,1 | 338 / 313 | %99,5 | 347 / 192 | **2,91** | %2,01 | %92,2 |
| SILVER | 3.606 | %99,1 | 331 / 316 | %99,5 | 336 / 233 | **2,85** | %3,65 | %91,4 |
| XU030 (bağlam) | 1.435 | %98,2 | 111 / 109 | %98,7 | 141 / 97 | 3,24 | %4,33 | %86,6 |
| **28 hisse (medyan)** | 1.436 | %97,6 | 106 / — | %94,8 | toplam 3.539 ↑ | **2,86** (2,38–3,35) | **%5,95** (4,35–7,64) | %86,7 (81,5–91,6) |

Hisselerde `swing_low` teması toplam **10.194**, FINAL long izni medyan **%26,8** (aralık %3,6–%39,3). **Hisselerde short stop üretilmedi** (28/28 `short_produced=False`, KARAR 4 LONG-ONLY testiyle kilitli).

### Yorum (dürüst): yapısal stop GENİŞ

Eşit-risk politikasında pozisyon büyüklüğü = `risk_per_trade / stop_mesafesi`. Medyan stop **~2,9 ATR / %6 fiyat** demek, %0,5 riskle hisse başına ~%8 pozisyon demektir. Bu bir hata değil, stop'un **yapısal** (son onaylı swing) olmasının doğrudan bedelidir. Aşama 7'de alternatif anchor'lar (Donchian-low, daha yakın swing) ve partial+runner/trailing test edilecek — **şimdi seçim yapılmıyor**.

## ZORUNLU NOT (kullanıcı kararı, 2026-09-16 — kod düzeyinde kilitli)

> BIST30 hisselerinde **warmup** nedeniyle TRAIN döneminde etiketli bar sayısı azdır
> (TRAIN ~426 tradable bar/hisse). Bu yüzden **hiçbir aşamada hisse başına in-sample
> parametre seçimi YAPILMAYACAK**. Parametre seçimi **Aşama 9**'da, **küçük bir aday
> kümesiyle** ve yalnızca **core varlıklar** (BTC / GOLD / SILVER) üzerinde yapılacak;
> **hisseler yalnızca OOS raporlanacak**. Kural kodda: `config.PER_ASSET_IN_SAMPLE_TUNING_ALLOWED = False`,
> `PARAM_TUNING_UNIVERSE = ("BTC","GOLD","SILVER")`, `PARAM_TUNING_STAGE = 9`.

## TAMAMLANDI: Aşama 2 — Piyasa rejimi + XU030 bağlam filtresi

Özet: `src/quant4h/features/regime.py` — **yalnızca 2 ölçüm**: EMA200 yönü (close vs EMA + ATR-normalize eğim) ve ATR(14) yüzdelik dilimi (500 bar geriye dönük) → `trend_up|trend_down|range × vol_high|vol_normal|vol_low` = **6 durum**. Isınma (ilk 500 bar) etiketsiz bırakılır ve `fail_closed=True` → rejim bilinmiyorsa sinyal YOK. Yasaklı indikatörler (ADX/Hurst/HMM/Choppiness/BB/Ichimoku/Supertrend/Keltner) `RegimeConfig`'ten **tamamen silindi** (kullanılmayan parametre = overfitting yüzeyi). Look-ahead testi: gelecek 300 bar silindiğinde geçmiş etiketler birebir aynı kalıyor → **GEÇTİ**.

Özet (XU030 filtresi): `src/quant4h/features/context.py` — KARAR 4 kodlandı. BIST30 hisseleri **LONG-ONLY**; yeni long yalnızca **kapanmış** XU030 4H barı EMA200 üstündeyken (karar anı = `bar_open − 4h`, as-of merge). **Fail-closed**: ısınma/bayat/kayıp bağlamda long YOK (maks bağlam yaşı 120h). Core varlıklar (BTC/GOLD/SILVER) filtreye tabi değil, long+short. Rapor: `reports/regime_report.md` + 32 etiketli frame `data/processed/regime/`.

### Aşama 2 sonuç tablosu

| Varlık | bar | etiketli | etiketsiz % | trend_up | trend_down | range | long OK | short OK |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 19.888 | 19.388 | %2,5 | 9.024 | 8.358 | 2.006 | 8.489 (%42,7) | 7.759 (%39,0) |
| GOLD | 3.606 | 3.106 | %13,9 | 2.092 | 692 | 322 | 1.932 (%53,6) | 678 (%18,8) |
| SILVER | 3.606 | 3.106 | %13,9 | 1.846 | 851 | 409 | 1.615 (%44,8) | 803 (%22,3) |
| XU030 (bağlam) | 2.158 | 1.658 | %23,2 | 988 | 420 | 250 | — (trade yok) | — |
| **28 hisse TOPLAM** | 60.416 | 46.424 | %23,2 | 22.378 | 17.680 | 6.358 | 21.132 (rejim) | **politika gereği 0** |

XU030 filtresi (sepet toplamı): `context_ok` **39.472** · `below_ema200` **15.260** (yeni long engellendi) · `warmup` 5.572 · `stale` 84 · `missing` 28.
**FINAL long izni** = rejim ∧ bağlam ∧ tradable ∧ return_valid → **11.720 bar / 60.416 = %19,4** (hisse bazında %4,7 SASA … %27,6 ASELS).

## TAMAMLANDI: KARAR 6 — sepet politikası + basket split ön-kaydı

Özet: Dört açık karar `configs/user_decisions.yaml → basket_policy` ve `xu030_context_filter` altında bağlayıcı olarak işlendi. (1) **Split**: `configs/splits_preregistered.yaml → bist30_basket` — 28 hisse için **TEK ortak takvim penceresi** (2023-10-27 → 2026-09-16, ızgara 2.158 bar), hisse başına ayrı split YOK, core ile aynı purge (30) + embargo (12), frozen snapshot `data/frozen/bist30_basket_4h_frozen.parquet` (60.416 satır, sha256 kilitli). TRAIN 678 ızgara barı (hisse başına medyan 449 tradable) · VALID 635 (421) · TEST 677 (448, **333 takvim günü**). (2) **Ağırlıklandırma: EŞİT-RİSK** — her sinyal aynı risk bütçesi, sermaye ağırlıklandırması YOK, likidite yalnız uygunluk şartı. (3) **Sinyal: HİSSE BAŞINA**; portföy tavanları (maks eşzamanlı pozisyon, sektör tavanı, basket ısısı) Aşama 8'e bırakıldı. (4) **XU030 filtresi** Aşama 2'de kodlandı.

## TAMAMLANDI: AŞAMA 1.5 — BIST30 hisse üniversali

Özet: Ünivers **30 üye** olarak `configs/bist30_universe.yaml`'a tarih damgasıyla (`2026-09-16.v1`) sabitlendi; 30. üye **FROTO** ancak Investing.com'un tam listesiyle bulunabildi (Midas/HangiKredi 29 veriyor, uzmanpara bayat). 30 hisse için Yahoo **1h + 1d** indirildi (küçük batch + retry + bekleme), ham veriler hisse başına ayrı immutable parquet. İstanbul lokal grid'inde 4H'ye çevrildi → günde **2 TAM bar** (10-14, 14-18) + **1 ince bar** (06-10, yalnızca 09:30 açılış anı printi). Sonuç: **28 hisse sepete GİRDİ, 2 ELENDİ** (DSTKF: %10 halt/marj + 68 sıfır-aralık bar; TRALT: 605 bar / 296 gün — halka arz yeni). Rapor: `reports/bist30_universe_qc.{md,csv,json}`.

Özet (kritik teknik bulgu): Yahoo'nun **1h** BIST serisinde `adjclose == close` (**%100 ölçüldü**) → intraday seri kurumsal aksiyon düzeltmesi İÇERMİYOR; bu yüzden tespit **GÜNLÜK** serinin `adjclose/close` adım değişiminden yapılıp ex-date'ler `session_date` üzerinden 4H barlara taşınıyor. Politika adjust.py felsefesiyle birebir: **OTOMATİK DÜZELTME YOK, FLAG ONLY** — ex-date barı ve sonrakinde `return_valid=False` + `non_tradable=True`, hiçbir fiyat yazılmıyor, hiçbir bar silinmiyor. Tespit: **482 kurumsal aksiyon olayı / 298 işaretli bar / 0 bölünme adayı** (dürüst sınır: kural yalnızca >%25 sıçramalı bölünmeleri yakalar; Mart–Haziran temettü mevsimiyle uyumlu). Maliyet **120 bp gidiş-dönüş** (config.py'de `assert` ile kilitli).

## TAMAMLANDI: XU030 rolü netleşti — bağlam filtresi

Özet: `XU030.IS` **trade varlığı değildir**; `watch_only` modunda kalır ve yalnızca **long'lar için bağlam filtresi** olarak kullanılır (ör. endeks EMA200 altındayken hisse LONG sinyalleri bastırılır). Endeks getirisi portföy performansına YAZILMAZ. VİOP maliyet proxy'si **GEÇERSİZ** kılındı; hisse sepeti için ayrı maliyet modeli (10 bp komisyon + 60 bp tam spread + 20 bp slippage = **120 bp**) `config.make_bist_stock_spec()` içine işlendi.

## TAMAMLANDI: Aşama 1c — Split ön-kaydı (pre-registration)

Özet: `scripts/register_splits.py` → `configs/splits_preregistered.yaml` (+ `data/frozen/*_frozen.parquet` snapshot'ları). Politika **sabit bar sayısı** (test 1000 / valid 800), yüzde değil — çünkü varlık geçmişleri 4 kat farklı ve yüzde kullanılsa metallerin test penceresi ~28 güne düşerdi. Test = en yeni dönem; her sınırda **purge 30 + embargo 12 bar**; sayımlar yalnızca **tradable** barlar üzerinden. **Dondurulmuş snapshot'ın** SHA-256'sı gömülü: snapshot değişirse `--check` ön-kaydı GEÇERSİZ ilan eder; canlı verinin yeni bar alması ise hata değil, `drift_report()` ile bilgilenmedir (yeni barlar ancak policy_version artırılıp YENİ ön-kayıt yazılarak çalışmaya girer). Sonuç: BTC 18.044/716/958 · GOLD & SILVER 1.733/716/958 · BIST30 437/395/436. Dört varlıkta da test penceresi <365 gün ve <200 seans → **istatistiksel güç DÜŞÜK** uyarısı kayıtlı; asıl OOS aracı Aşama 9 walk-forward.

## TAMAMLANDI: Aşama 1b — cleaning.py testleri

Özet: `cleaning.py` yeniden yazıldı ve `tests/test_cleaning.py` (11 test) eklendi. Politika netleşti: **yalnızca NaN / pozitif-olmayan satırlar düşürülür**; OHLC zarfı bozuk barlar SİLİNMEZ, `repair_ohlc_envelope` ile onarılır (open/close asla oynatılmaz). `winsorise_returns` sadece İŞARETLER, değer değiştirmez ve `return_valid=False` olan (kesinti atlayan) getirileri şişman kuyruk saymaz. `dedupe_and_sort`'ta "first/last" artık **geliş sırasına** göre tanımlı (önceden satır sırasına göre idi → belirsizdi). Her adım `CleaningLog`'a satır sayısı ile yazılır.

## TAMAMLANDI: Aşama 1a — adjust.py (roll + veri kesintisi) → GOLD/SILVER RED'den çıktı

Özet: `src/quant4h/data/adjust.py` + `scripts/run_adjust.py` + `reports/adjust_evidence.md`. Kanıt: 4 varlıkta da **satır sayısı değişmedi (silinen 0, eklenen 0)**, timestamp'ler ve `close_raw` bayt bayt aynı. 75 saatlik kesinti pencere olarak raporlandı; kesintiyi atlayan getiriler `return_valid=False` yapıldı (SILVER max|getiri| **0.2222 → 0.1665**, GOLD **0.0797 → 0.0466**). SILVER 2026-02-02 barı duruyor ve `gap_anomaly=True / outage_resumption=True / non_tradable=True / roll_candidate=False` olarak bayraklı. **DÜRÜST SINIR:** feed'de kontrat ayı kimliği olmadığı için roll ile gerçek ekstrem hareket AYIRT EDİLEMEZ → fiyatlar otomatik DÜZELTİLMİYOR (adaylar yalnızca işaretli: GOLD 10, SILVER 6, BTC 0, BIST30 0); kalıcılık testi bad print'i ayırt ETMİYOR, ayırt edici sezgi hacim. QC yeniden çalıştı: **GOLD ve SILVER RED → AMBER, usable_for_modelling=True**.

## ONAY İŞLENDİ: GOLD|SILVER tek risk kovası

Özet: Kullanıcı 2026-09-16'da öneriyi ONAYLADI. `configs/user_decisions.yaml → risk.correlation_buckets`: `precious_metals = [GOLD, SILVER]` TEK risk birimi; kova içi birleşik ısı `bucket_heat <= risk_per_trade` (balanced %0.5). Yani ikisi aynı anda ayrı ayrı %0.5 riskle açık TUTULAMAZ. Reddedilen alternatifler de kayıtlı (cross-hedge uygulanmadı; limiti 0.80'e çıkarmak REDDEDİLDİ = overfitting). Uygulama noktası: **Aşama 8 risk modülü**.

## DÜZELTME: BIST30 kararı yanlış anlaşılmıştı

Özet: Kullanıcı netleştirdi — "BIST30" = **BIST30 KONSTİTUANT HİSSELERİ**, XU030 endeksi DEĞİL. `configs/user_decisions.yaml` güncellendi: `instrument_type=stock_basket`, üniversal `configs/bist30_universe.yaml`'da tarih damgasıyla sabitlenecek, XU030 artık **trade varlığı değil, long'lar için bağlam filtresi**. VİOP maliyet proxy'si GEÇERSİZ kılındı → hisse maliyet modeli (10+30+20 bp ≈ 120 bp gidiş-dönüş, kalibrasyon Aşama 1.5'te). **AŞAMA 1.5 kuyruğa eklendi** (6 adım + kabul kriterleri). Zorunlu caveat: serbest veride yalnızca BUGÜN endekste olan hisseler indirilebilir → **SURVIVORSHIP BIAS kaçınılmaz ve sonuçları YUKARI çeker**; BIST30 sonuçları BTC/metallerle aynı güven düzeyinde değerlendirilemez.

## TAMAMLANDI: Aşama 0 — İskelet, config ve ortam

Özet: Proje iskeleti (`src/quant4h/{data,features,labels,models,strategy,risk,backtest,learning,reporting,utils}`), kanonik OHLCV şeması, 3 risk profili ve varlık bazlı maliyet modelleri yazıldı. Ortam kuruldu: Python 3.11 + pandas 3.0.5 + sklearn 1.9.1 + matplotlib + statsmodels + shap + pyarrow + yfinance. LightGBM/XGBoost `libgomp.so.1` eksikliğinden ÇALIŞMIYOR → ML için sklearn `HistGradientBoosting` kullanılacak.

## TAMAMLANDI: Aşama 1 (veri toplama) — 4 varlık + funding + makro kontekst

Özet: Binance spot klines (BTC 4H, 2017-08-17 → bugün, 19.888 bar, gerçek hacim) ve Yahoo Finance (GC=F/SI=F 1h → 4H, XU030.IS 1h → 4H) indirildi; ham veriler `data/raw/*.parquet` altında **immutable** saklandı. BTC perpetual funding (500 kayıt) ve DXY / US10Y / USDTRY / SPX / VIX günlük serileri kontekst olarak çekildi. Yahoo `interval=1h & period=max` **boş** döndürüyor → adaptör 730 güne düşürülüyor.

## TAMAMLANDI: Aşama 1 (4H dönüşüm) — seans takvimi duyarlı resampler

Özet: Her varlık kendi seans takviminde 4H'ye çevrildi: BTC = UTC grid (00/04/08/12/16/20), GOLD/SILVER = 18:00 America/New_York lokal grid (DST'de lokal saatler sabit, UTC saatleri kayar), BIST30 = 10:00 Europe/Istanbul lokal grid (Türkiye'de DST yok → UTC saatleri yıl boyu sabit: 03/07/11). **Oluşmakta olan son bar otomatik düşürülüyor** (birincil look-ahead koruması) ve DST "var olmayan saat" artefaktları tekrarlanan UTC damgası üretmeden temizleniyor.

## TAMAMLANDI: Aşama 1 (veri kalitesi) — QC motoru + rapor

Özet: 13 kontrol ailesi (şema, timestamp/grid hizası, eksik bar, OHLC zarfı, **seans-beklenen boşluk analizi**, outlier/MAD, hacim, opsiyonel kolonlar, resample denetimi, tazelik, geçmiş uzunluğu, seans şekli, düzeltme kapısı) + portföy düzeyi kontroller. Çıktı: `reports/qc_report.md|.json|qc_findings.csv`. Ham veri ASLA değiştirilmiyor; temizlik ayrı ve loglanan bir adım (`data/cleaning.py`).

---

## GÜNCEL DURUM TABLOSU (Aşama 1 kapanışı)

| Varlık | Mod | 4H bar | tradable bar | QC kararı | ERROR | WARN | Model uygun | non-tradable | geçersiz getiri | roll adayı |
|---|---|---:|---:|---|---:|---:|---|---:|---:|---:|
| BTC | `core` | 19.888 | 19.886 | **AMBER** | 0 | 5 | ✅ EVET | 2 | 3 | 0 |
| GOLD | `core` | 3.606 | 3.575 | **AMBER** ⬅️ RED'den | 0 | 8 | ✅ EVET | 31 | 32 | 10 (yalnız işaretli) |
| SILVER | `core` | 3.606 | 3.575 | **AMBER** ⬅️ RED'den | 0 | 9 | ✅ EVET | 31 | 32 | 6 (yalnız işaretli) |
| BIST30 | `watch_only` | 1.435 | 1.410 | **AMBER** | 0 | 13 | ⚠️ güç ÇOK düşük | 25 | 25 | 0 |

**Çekirdek backtest portföyü:** BTC + GOLD + SILVER · **İzleme modu:** BIST30

### Ön-kayıtlı split'ler (`configs/splits_preregistered.yaml`, policy v1.0)

| Varlık | TRAIN | VALID | TEST | TEST gün | TEST seans | purge+embargo | OOS için yeterli |
|---|---:|---:|---:|---:|---:|---|---|
| BTC | 18.044 | 716 | 958 | 159 | 161 | 30 + 12 bar | ⚠️ bar olarak evet, güç DÜŞÜK |
| GOLD | 1.733 | 716 | 958 | 233 | 165 | 30 + 12 bar | ⚠️ aynı |
| SILVER | 1.733 | 716 | 958 | 233 | 165 | 30 + 12 bar | ⚠️ aynı |
| BIST30 | 437 | 395 | 436 | 321 | 146 | 30 + 12 bar | ⚠️ aynı |

Günlük log-getiri korelasyonu: `GOLD|SILVER = +0.768` ⚠️ (risk limitini aşıyor), `BTC|SILVER = +0.265`, `BTC|GOLD = +0.180`, BIST30↔hepsi ≤ 0.086.
4H seviyesinde BTC↔diğerleri arasında **ortak bar yok (n=0)** — grid faz farkı nedeniyle; korelasyon limiti yalnızca **günlük** bazda uygulanır.

---

## KAYITLI TEŞHİSLER (kodda `caveats` olarak da gömülü)

1. **BIST30 doğrudan trade edilemez.** `XU030.IS` endeksin kendisi: hacim her bar 0 → hacim/onay bacağı iptal. Execution VİOP XU030 vadeli maliyet modeliyle **varsayımsal** modellenir (komisyon 6bp + spread 15bp + slippage 15bp ≈ gidiş-dönüş 57bp).
2. **BIST30 ince bar oranı %33,5.** Her günün 03:00 UTC (06:00 lokal) barı yalnızca Yahoo'nun 09:30 "açılış anı" printini içerir (`n_src_bars=1`). Barlar **silinmez**, `n_src_bars` ile işaretlenir; bu barlar tam barlarla 1:1 karşılaştırılmamalı.
3. **GOLD/SILVER veri kesintisi:** `2026-01-30 15:00 UTC → 2026-02-02 18:00 UTC` arası 75 saat kayıp (normal hafta sonu 80 bar; burada Pazartesi 00:00–15:00 UTC de yok). 2026-02-02 günü yalnızca 5 bar gelmiş (normal ~23). **İki varlıkta da birebir aynı tarihlerde** → Yahoo kaynaklı ortak sorun.
4. **SILVER 2026-02-02 −%22 olayı (KARAR 3 teşhisi): NE ROLL NE BAD PRINT.** Yukarıdaki veri kesintisini atlayan **sahte** bir getiridir. Bar silinmedi; "boşluğu atlayan getiri" olarak işaretlendi ve getiri/roll/label hesaplarından hariç tutuluyor.
5. **2026-01-26 .. 2026-02-06 penceresinde feed kalitesi ÇOK düşük.** GOLD 5.626 → 4.653 (≈ −%17), SILVER 121.79 → 66.88 (≈ −%45); günlük hacim önceki dönemin %38 (GOLD) / %42 (SILVER)'sine düşüyor. Bu pencereye dayandırılan sonuçlara güvenilemez.
6. **GC=F/SI=F ön-ay vadeli** → roll gap düzeltmesi yok. `requires_adjustment=True` olduğu için düzeltme çalıştırılana kadar QC bu iki varlığı **RED** olarak kilitler (bilinçli kapı).
7. **Metaller yalnızca ~2,4 yıl intraday** (Yahoo 1h limiti 730 gün). BTC 9,1 yıl. Bu, varlıklar arası karşılaştırmayı asimetrik yapar: metallerde walk-forward kat sayısı sınırlı kalır.
8. **BIST30 grid faz farkı.** Barlar 03/07/11 UTC'de, BTC 00/04/08 UTC'de açılır → 4H ortak bar yok. Seans bütünlüğü tercih edildi (bilinçli bedel).
9. **Exchange tatil takvimi kullanılmıyor.** "Beklenmedik boşluk" kuralı sezgiseldir (`gap > modal_gap(gün, saat) + 4 bar`); uzun dini/millî tatiller yanlış pozitif üretebilir. Bu yüzden kural tek başına ERROR üretmez (ERROR eşiği: barların >%5'i).
10. **BTC'de 2 gerçek ekstrem bar:** 2017-09-15 +27,2% ve 2020-03-12 −22,9% (bitişik barlarda, veri hatası değil). Silinmez, işaretlenir.

---

## DÜZELTİLEN HATALAR (kayıt)

| # | Hata | Kök neden | Çözüm | Regresyon testi |
|---|---|---|---|---|
| H1 | Test UTC saat beklentisi yanlış | Grid fazı yanlış hesaplanmış | Test beklentisi düzeltildi | `test_local_mode_grid_alignment_is_not_flagged` |
| H2 | Hafta sonu/tatil boşlukları "eksik bar" sayıldı | Sabit `>4 bar` eşiği | Seans-duyarlı eşik `max(16, ceil(bps×5)+1)` | `test_weekend_gaps_are_not_flagged_as_missing_bars` |
| H3 | `KeyError 'BTC\|BIST30'` | Korelasyon anahtarı sütun sırasına bağlı | Anahtar `sorted()` ile kanonik | `test_portfolio_correlation_is_pairwise_complete` |
| H4 | BIST30'da seans başına bar sayısı bozuk (2 yerine 3 olmalı) | `session_date()` grid anchor ile seans açılışını karıştırıyordu | **3 ayrı kavram** ayrıldı: `bar_anchor_local` / `session_anchor_local` / `session_day_start_local` | `test_session_date_uses_explicit_day_start`, `test_metals_session_date_uses_halt_aware_day_start` |
| H5 | `ValueError: nonexistent time due to DST` (2025-03-09 02:00 NY) — script BTC'den sonra **sessizce** çöküyordu | Lokal-naive grid, DST'de var olmayan saat üretiyor | `nonexistent="shift_forward"` + UTC damgası tekilleştirme | `test_dst_transition_produces_no_duplicate_or_crash` |
| H6 | BIST30'da barların %33'ü "veri kesintisi" sayıldı | Ham `gap > 1 bar` kuralı seans sonu normal gece boşluğunu yakalıyordu | Modal boşluk bazlı anomali kuralı | `test_normal_session_gaps_are_not_flagged_as_outage` |
| H7 | Tüm opsiyonel kolonlar "populated" raporlandı | Kanonik şema hepsini NaN olarak üretiyor | "bilgi taşıyor mu" testi eklendi | `test_all_nan_optional_columns_are_not_reported_populated` |
| H8 | SILVER −%22 "outlier" olarak sınıflandırıldı | Boşluğu atlayan getiri gerçek getiri sayılıyordu | `logret_clean` + `continuity` kontrolü | `test_gap_crossing_return_is_not_treated_as_real_return` |
| H9 | Testler `min_bars_fill=2` ile ince barları sessizce siliyordu | Veri kaybı şeffaf değildi | `min_bars_fill=1` + `n_src_bars` ile işaretleme | `test_bist_local_anchor` |
| H10 | `grep` ile filtrelenince script çökmesi görünmüyordu | Hata yönetimi yoktu | Çıktı log'a alınıp `exit code` kontrol edildi | — (süreç değişikliği) |

| **H11** | `ValueError: nonexistent time due to DST` → sonra **back-adjustment faktörü her barda kayıyordu** | `ratio_np[1:] = r` ile TÜM getiriler yazılıyordu; sadece roll pozisyonlarına yazılmalıydı | `ratio_np[1:][applied[1:]] = r[applied[1:]]` + saf numpy `cumprod` | `test_back_adjustment_removes_exactly_the_roll_jump` |
| **H12** | BTC spot'ta **118 sahte "roll"** bulundu | Roll tespiti `requires_adjustment`'a kapalı değildi; spot'ta roll tanım gereği imkânsız | Tespit yalnızca vadeli serilerde; ayrıca "roll" iddiası tümüyle bırakıldı → `big_move_candidate` | `test_spot_and_index_never_get_a_roll` |
| **H13** | Bad print ile roll ayırt edilemiyordu; kalıcılık testi işe yaramadı | Kalıcılık testi ayırt ETMEZ: print sonrası seviye kaymış görünür. Gerçek ayırt edici **hacim**dir ve o da kanıt değil | Otomatik sınıflandırma kaldırıldı → FLAG ONLY + `bad_print_candidate` (hacim sezgisi) + dürüst sınır belgelendi | `test_bad_print_heuristic_uses_volume_not_persistence` |
| **H14** | BIST30'da bar sayısı çalıştırmalar arasında 2157↔2158 kaydı; `adjust` ile `QC` farklı frame üzerinde çalıştı | `run_adjust.py` ayrı çalışıp eski interim'i okuyordu; interim her QC'de yeniden üretiliyor | QC içine `--adjust` zinciri eklendi: aynı `target` frame üzerinden resample→adjust→QC | `test_splits.py::test_verify_detects_tampered_source` (sha256 kayması yakalar) |
| **H40** | HİÇ trade üretilmiyordu (`rejected_no_valid_stop` sürekli artıyordu) | `_as_bool(out.get("stop_valid_long"), out.index, False)` → ikinci argüman olarak **kolon değil index** geçiriliyordu; kolon hiç okunmuyordu | İmza `_as_bool(s, n: int, default)` yapıldı; çağıran kolonun kendisini geçirmek zorunda | `test_entry_is_next_bar_open_and_costs_are_charged_both_sides` |
| **H41** | `stop_valid_long` **object dtype** olunca `pd.to_numeric` NaN üretiyor, `fillna(0)` ile TÜM kolon sessizce False oluyordu | Python bool'ları `to_numeric`'te sayıya dönüşmüyor | object dtype için `arr.astype(bool)`; test tarafında dtype açıkça `bool` | aynı + `test_position_without_valid_stop_is_never_opened` |
| **H42** | `ValueError: truth value of an array is ambiguous` | `max(1e-9, np.array(...))` → Python `max` diziyle karşılaştırıyor | `np.maximum(eq_before, 1e-9)` | `test_equity_recomputed_from_trades_matches_engine` |
| **H43** | "Pozisyon yokken equity düz" denetimi patlıyordu | `position_open[t]` çıkış barında 0'a dönüyor ama equity aynı barda gerçekleşen değere atlıyordu | Maruziyet bayrağı bar BAŞINDA (çıkıştan önce) yazılıyor | `test_equity_recomputed_from_trades_matches_engine` |
| **H44** | Bootstrap CI yalnızca trade<100 iken hesaplanıyordu → BTC (187) ile GOLD (30) KARŞILAŞTIRILAMIYORDU | "zayıf örneklem" bayrağı ile CI hesabı birbirine karıştırılmıştı | CI **her zaman** hesaplanır (n≥5); bayrak yalnız eşik altında | `test_metrics_and_weak_sample_flag` |
| **H45** | Test verisinde giriş barı ile gap barı AYNI bardı → `open=85 < stop=90` olup geometri kontrolü (doğru olarak) reddediyordu | Test kurulumu, motor değil | Sinyal/giriş/olay barları ayrıldı; frozen-stop testi artık donmuş ile izleyen stop'u **ayırt ediyor** (bar 10/90 vs bar 9/99) | `test_stop_gap_fill_uses_open_when_open_is_worse`, `test_stop_is_frozen_throughout_the_position` |
| **H34** | `execution_timestamp_utc` tz bilgisini kaybediyordu → `== timestamp_utc[t+1]` karşılaştırması patlıyordu | `np.where(..., datetime64[ns])` tz'yi düşürüyor (H20 ile aynı desen) | `pd.Series.shift(-1).where(sig_any)` ile tz-aware tutuldu | `test_execution_is_next_bar_open_not_signal_close` |
| **H35** | `entry_stop` sinyal barında NaN kalıyordu | Döngüde `entry_stop[t]`, pozisyon açılmadan ÖNCE yazılıyordu | Sinyal barında da `cur_stop` yazılıyor; ayrıca stop NaN ise pozisyon HİÇ açılmıyor (fail-closed) | `test_no_signal_while_position_is_open`, `test_invalid_stop_blocks_position_opening` |
| **H36** | `position_exit_proxy="none"` pozisyonu sonsuza dek açık bırakıyordu → tek sinyal | "none" yalnızca çıkış KURALINI kapatmalı, pozisyon takibini değil | `proxy="none"` ise pozisyon aynı barda kapatılıyor (yalnız cooldown aktif) | `test_cooldown_off_by_one_is_exactly_as_documented` |
| **H37** | Cooldown off-by-one: belgelenen `s+4` yerine `s+5` üretiyordu | `blocked_until` + `t <= blocked_until` ikili belirsizliği | `resume_at` semantiğine geçildi (ilk UYGUN bar konumu), `t < resume_at` ile bastırma | `test_cooldown_off_by_one_is_exactly_as_documented` |
| **H38** | `from .levels import anchor_eligible` → `ModuleNotFoundError: quant4h.strategy.levels` | `signals.py` `strategy/` paketinde; `levels` `features/` altında | `from ..features.levels import anchor_eligible` | tüm `test_signals` paketi |
| **H39** | `signals_per_year` tek sinyalde `1e9` (saçma değer) üretiyordu | Sıfıra bölme `max(1e-9, ...)` ile "gizlenmişti" | Span 0 gün ise `None` döner | `test_stats_per_year_is_none_for_single_signal` |
| **H32** | Guard testi başarısız: ATR'yi tümüyle NaN yapınca yine de 287 bar "geçerli" çıktı | `add_momentum`, mevcut ama tamamen NaN olan `atr` kolonunu **sessizce yeniden hesaplıyordu** → guard atlanıyordu | Politika netleşti: kolon VARSA kullanılır, YOKSA hesaplanır; NaN olsa bile yeniden hesaplanmaz (guard yakalar) | `test_guard_never_defaults_to_zero_or_pass` |
| **H33** | "Yasaklı momentum indikatörü yok" testi kendi docstring'ine takıldı | Düz metin taraması; docstring "RSI/MACD yoktur" diyordu | `ast` ile docstring+yorum soyulup yalnızca ÇALIŞAN KOD taranıyor (H29 ile aynı desen) | `test_no_forbidden_momentum_indicator` |
| **H27** | 28 BIST hissesinde **swing=0, Donchian=0, stop=0** → sepet hiç sinyal üretemiyordu | 3 barlık BIST grid'inde her 3 barda bir ince (anchor-uygun olmayan) bar var; k=3 fraktalın 6 komşusu HER ZAMAN en az birine denk geliyor | `AssetSpec.min_source_bars_per_target` eklendi; ince bar hiç üretilmiyor → günde 2 TAM bar | `test_istanbul_grid_gives_two_full_bars_only` |
| **H28** | `min_source_bars_per_target=4` **tüm sepeti** eledi (eksik %26,5) | Yahoo BIST 1h feed'inde 17:30 printi günlerin ~%45'inde YOK → 14:00-18:00 bin'i çoğu gün 3 bar | Eşik **3** (=%75 kapsama, projenin "ince bar" tanımıyla tutarlı) | `test_istanbul_grid_gives_two_full_bars_only` |
| **H29** | "Yasaklı indikatör yok" testi **kendi docstring'ime** takıldı | Düz metin taraması; docstring "RSI/MACD yığını yok" diyordu | `ast` ile docstring+yorum çıkarılıp yalnızca ÇALIŞAN KOD taranıyor | `test_no_forbidden_indicator_in_levels_module` |
| **H30** | Donchian `min_periods=n` ile pencerede TEK bayraklı bar varsa sonsuza dek NaN | maskelenmiş değer NaN → rolling tüm pencereyi NaN yapar | `min_periods=1` + geçerlilik-oranı kapısı (`min_valid_frac_in_window=0.90`) | `test_non_tradable_and_halt_bars_are_excluded_from_donchian` |
| **H31** | İki farklı gap eşiği birbirini yalanladı: BIST tatilleri hem "anomali" hem "şüpheli boşluk" sayıldı | Biri sabit bar, diğeri `bps×5` idi | TEK seans-bazlı yardımcı: `_gap_tolerance_bars` (24/7 → 2 seans, seanslı → 8 seans, tavan 25 bar); şüpheli-boşluk eşiği `max(16, bps×8+2)` | `test_weekend_gaps_are_not_flagged_as_missing_bars` |
| **H23** | `merge_asof` → `MergeError: datetime64[us, UTC] vs datetime64[ms, UTC]` | parquet `us`, `to_datetime` `ms`/`ns` üretiyor; pandas iki tarafta aynı çözünürlüğü istiyor | Her iki anahtar `datetime64[ns, UTC]`'ye normalize edildi | `test_context_uses_only_closed_index_bars` |
| **H24** | `TypeError: ufunc 'bitwise_and' not supported` | Operatör önceliği: `a & b <= 0` içinde `<=` parantezsizdi | `(np.nan_to_num(above, nan=0.0) <= 0.0)` | `test_context_filter_blocks_longs_below_ema200` |
| **H25** | Bağlam filtresi "look-ahead KALDI" verdi | **Test yanlıştı**: endeksin son 200 barı silinince o barlardan sonraki hisse barlarında bağlam gerçekten yok; `fail_closed` doğru olarak reddediyordu | Test yeniden kuruldu: kesim öncesi **birebir aynı**, grace içinde aynı, grace dışında **red** | `test_context_truncation_only_affects_bars_after_the_cut` |
| **H26** | İnce barların bağlam yaşı 120h grace'i aşıp sebepsiz `stale` üretiyordu | Grace `3 bar + 1h` = 13h idi; BIST ince barı (03:00 UTC) XU030'da 23:00 barı olmadığı için **zaten 12h** yaşında → tek eksik endeks barı tüm günü reddediyordu | Varsayılan grace **120h** (5 gün: hafta sonu + resmî/dinî tatiller) | `test_context_thin_bar_age_is_within_grace` |
| **H18** | Maliyet modeli 120 bp yerine **90 bp** üretti | `CostModel.spread_bps` TAM spread'tir (tek tarafa yarısı yazılır); 30 verilince 60 değil 30 bp toplam etki yaptı | `spread_bps=60` + `config.py` içinde `assert abs(rt-120)<1e-9` kilidi + iki YAML'da birim sözleşmesi belgelendi | `test_stock_cost_model_is_120bp_round_trip` |
| **H19** | Kurumsal aksiyon tespiti **0 olay** buldu | Yahoo **1h** BIST serisinde `adjclose == close` (%100) → intraday seri düzeltme İÇERMİYOR | Tespit GÜNLÜK seriye taşındı (`corporate_actions_from_daily` + `flag_corporate_actions_from_dates`); QC'ye "intraday adjclose trap" kontrolü eklendi | `test_1h_adjclose_trap_is_real_and_documented` |
| **H20** | Ex-date eşleşmesi **sessizce 0** dönüyordu | `pd.DatetimeIndex(datetime64[us, UTC])` tz bilgisini SESSİZCE düşürüyor → `isin()` hep False | `pd.to_datetime(..., utc=True)` ile tz korundu + eşleşme sayısı doğrulanıyor + eşleşme 0 ise pencere içi/dışı ayrımıyla **uyarı veya bilgi notu** üretiliyor | `test_corporate_action_matching_is_not_silently_fooled_by_tz` |
| **H21** | Tüm hisseler "sıfır hacim %16.5" gerekçesiyle ELENDİ | Sıfır hacimli barların %100'ü ince açılış-anı barındaydı (09:30 printi ~%49 hacimsiz); tam barlarda sıfır hacim YOK | Kalite kapısı **TAM barlar** üzerinden ölçülüyor (`n_src_bars>=3`); ince bar oranı ayrıca raporlanıyor | `test_zero_volume_is_confined_to_the_thin_opening_bar` |
| **H22** | Ünivers 29 üyeyle "tamam" sanıldı | 4 kaynağın hiçbiri tek başına 30'u vermiyordu; 3'ü oybirliğiyle 29 dedi | Investing.com tam liste + üyelik değişikliği kanıtlarıyla çapraz doğrulama (CIMSA→DSTKF Oca 2026, ULKER→yedek 2Ç 2026) → **FROTO 30. üye** | `test_universe_matches_investing_full_list` |
| **H17** | Split ön-kaydı, canlı veri her çalıştırmada yeni bar aldığı için **anında geçersiz** oluyordu (`source_sha256` uyuşmuyor) | sha256 canlı dosya üzerinden alınıyordu; canlı dosya sürekli büyüyor | Ön-kayıt **dondurulmuş snapshot**'a (`data/frozen/*_frozen.parquet`) bağlandı; canlı büyüme `drift_report()` ile BİLGİ olarak raporlanıyor | `test_verify_detects_tampered_source` (frozen değiştir → GEÇERSİZ; canlı büyür → geçerli + drift notu) |
| **H15** | `dedupe_and_sort`'ta "first" belirsizdi: sıralı mı geliş sırası mı? | `drop_duplicates(keep='first')` satır sırasına bakar, çağırının concat sırasına göre sonuç DEĞİŞİR | `_arrival` kolonu ile geliş sırası açıkça kaydedildi; politika parametrik ve test edildi | `test_dedupe_keeps_first_by_arrival_order` |
| **H16** | Testler kendi hatasıyla 3 kez FAIL verdi (beklenti yanlış) | Spike 4H barın ortasına denk geldi; `drop()` sonrası index kaydı; dup satır orijinalden önce geldi; `tz` yanlış | Test verisi kurulumu düzeltildi; `_ny_hourly` yardımcısı OHLC zarfını garanti ediyor | — (test hijyeni) |

**Süreç kuralı (H10'dan çıkan ders):** Bir script `grep`/`tail` ile filtrelenerek çalıştırılmaz; önce `> log 2>&1; echo $?` ile tam çıktı ve çıkış kodu alınır.

---

## SIRADAKİ İŞ

- [x] ~~**1a. Roll / veri-kesintisi düzeltme modülü**~~ ✅ `src/quant4h/data/adjust.py` + `scripts/run_adjust.py` + `reports/adjust_evidence.md`
- [x] ~~**1b. `cleaning.py` testleri**~~ ✅ `tests/test_cleaning.py` (11 test)
- [x] ~~**1c. Split ön-kaydı**~~ ✅ `scripts/register_splits.py` + `configs/splits_preregistered.yaml` (9 test)
- [x] ~~**AŞAMA 1.5 — BIST30 hisse üniverseli**~~ ✅ 6 adımın tamamı bitti (bkz. TAMAMLANDI bloğu)
- [x] ~~**AŞAMA 2 — Piyasa rejimi + XU030 bağlam filtresi**~~ ✅ (bkz. TAMAMLANDI bloğu)
- [x] ~~**AŞAMA 3 — Yapısal seviyeler + dondurulmuş stop**~~ ✅ (bkz. TAMAMLANDI bloğu)
- [x] ~~**AŞAMA 4 — Momentum onayı**~~ ✅ (bkz. TAMAMLANDI bloğu)
- [x] ~~**AŞAMA 5 — Giriş tetiği + sinyal montajı**~~ ✅ (bkz. TAMAMLANDI bloğu)
- [x] ~~**AŞAMA 6 — Baseline backtest**~~ ✅ (bkz. TAMAMLANDI bloğu)
- [x] ~~**AŞAMA 7 — Esnek kâr alma + alternatif stop anchor'ları**~~ ✅ (2026-09-17 — KARŞILAŞTIRMA grid'i; SEÇİM YOK, seçim Aşama 9 OOS. Bkz. en üstteki TAMAMLANDI bloğu + `reports/stage7_exit_grid.md`)
      *(Tarihî kuyruk notu — Aşama 6/7 kapanışında işlendi; kapsamın karşılanan kısmı
      TAMAMLANDI bloğunda, kalan 5b işleri aşağıda duruyor:)*
      Kapsam: partial TP + runner, trailing stop, breakeven after 1R,
      volatility-adjusted trailing, time-based exit. Her varlık için ayrı
      test; TP/SL oranı risk yönetimiyle birlikte değerlendirme.
      **Neden kritik:** Aşama 6'da çıkışların çoğu `time_stop` (BTC 80/187,
      sepet 61/172) — yani pozisyonlar hedefe ulaşmadan süresi doluyor.
      TP 3R yalnızca BTC'de 27, sepette 20 kez çalıştı. Esnek kâr alma olmadan
      expectancy'nin yükselmesi beklenmemeli.
      Hazır girdi: `data/processed/signals/<KEY>_4h_signals.parquet` + `engine.py`
      (çıkış motoru `_close_trade` üzerinden genişletilecek).
      Zincir zaten kodlu (`add_signal_chain`). Aşama 5'te kalan iş: sinyal
      frekansı/precision-recall ölçümü, eşiklerin overfit'siz seçimi ve
      ML'in **opsiyonel 3. filtre** olarak eklenmesi (varsayılan KAPALI).
      Hazır girdi: `data/processed/signals/<KEY>_4h_signals.parquet` (31 dosya, `strict` akışı) —
      Aşama 2+3+4+5 kolonlarının TAMAMI: `dc_high_prev20`, `dc_low_prev20`,
      `trigger_long/short`, `long_signal_raw`, `long_signal`, `short_signal`,
      `suppressed_by_position`, `suppressed_by_cooldown`, `position_open`,
      `entry_stop`, `signal_bar_close`, `execution_bar`, `execution_price`,
      `execution_timestamp_utc`, `execution_valid`, `signal_side`.
      **Aşama 6'nın ilk işi:** gerçek çıkış motoru (stop ihlali + TP + time-stop)
      ile `strict` akışındaki sinyal açlığını gidermek ve next-bar-open
      icrasıyla maliyet dahil P&L üretmek.
      Hazır girdiler: `data/processed/levels/<KEY>_4h_levels.parquet` (32 dosya) içinde
      Aşama 2 + Aşama 3 kolonlarının TAMAMI: `ema_trend`, `atr`, `atr_pct`,
      `atr_percentile`, `trend_state`, `vol_state`, `regime`, `long_regime_ok`,
      `short_regime_ok`, `longs_allowed`, `anchor_ok`, `last_swing_high/low`,
      `highest_swing_high`, `lowest_swing_low`, `donchian_high/low`,
      `donchian_valid_frac`, `stop_long/short`, `stop_*_atr_mult`, `stop_*_pct_price`,
      `stop_valid_long/short`, `non_tradable`, `return_valid`.

- [x] ~~**AŞAMA 8 — Risk modülü**~~ ✅ (2026-09-17 — `risk/limits.py` + `risk/simulator.py` + `scripts/run_risk_report.py` → `reports/stage8_risk.md|json`; tavanlar yalnız girişte; tavansız koşu Aşama 7 P0×A0 ile birebir; bkz. TAMAMLANDI bloğu)
- [x] ~~**AŞAMA 9 — Robustluk + TEK seçim noktası + go/no-go**~~ ✅ (2026-09-17 — `scripts/run_stage9.py` iki fazlı, seçim `configs/selected_cells.yaml`'a hash'le donduruldu; HÜKÜM: **GEÇTİ=0**, BTC/basket KALDI (VALID sağduyu), GOLD/SILVER/core-agregat ZAYIF (örneklem); hepsi `watch_only`; bkz. TAMAMLANDI bloğu + `reports/stage9_oos_verdict.md`)
- [ ] **AŞAMA 10 — Opsiyonel ML ikinci onay** ← **YETKİ BEKLİYOR** (`ml_policy.gate`: kural tabanlı çekirdek OOS'ta GEÇMEDİ → gate KAPALI; yetki verilirse kapsam yine de HistGradientBoosting + purged K-fold + embargo olarak hazırlanabilir, ama DEVREYE ALINAMAZ)
- [x] ~~**AŞAMA 11 — Çıktılar**~~ ✅ (2026-09-17 — `reports/final_verdict.md` + `models/model_card.md` + `ops_runbook.md` + README kapanış bölümü; `test_deliverables.py` 6 testle kilitledi)
- **ARAŞTIRMA-KAPALI (2026-09-17):** Bu repoda sıradaki MEŞRU iş: `ops_runbook.md` §A aylık izleme (trade YOK), §B çeyreklik ÖN-KAYITLI look (2026: 3/4 hak kaldı; en erken ≥2026-12-17), §F yeni hipotez → YENİ PROJE. Aşama 10 (ML) gate KAPALI. Yeniden seçim/tune/ekstra look YASAK.

### Aşama 1.5'ten bağımsız, bilinen teknik borç

- [ ] **M9-PINE otomatik kilidi (R11 batch, gelecek ayın maint adayı):** pine dosyasında `strategy(`/`alert(`/`alertcondition(` yasak-kelime testi + `export_viz_payload` çıktı yapı doğrulaması (dizi uzunlukları/ts monotonluğu) — TEST_PLAN.md §0'da P3 olarak kayıtlı.

- [x] ~~**`test_splits.py` determinizm testi frozen'ı DESTRÜKTİF yeniden yazar**~~ ✅ **ÇÖZÜLDÜ (2026-09-17, kullanıcı onaylı bakım):** `build_split` çağrıları `RS.FROZEN_DIR` tmp yönlendirmesiyle koşuyor; her iki tamper testi TMP KOPYA + fake yaml (mutlak yol) üzerinde; runner'a frozen sha BEKÇİSİ eklendi (her testin başı+sonu, suite başı+sonu); regresyon testi `test_build_split_never_writes_real_frozen` eklendi. Suite 223→**224/224**, frozen 5/5 bayt-bayt değişmedi. Hüküm/seçim etkisi YOK.

- [ ] Roll adaylarının **insan incelemesi**: GOLD 10 + SILVER 6 aday `reports/adjust_evidence.md` §5'te listeli. Kesin çözüm = kontrat ayı kimliği olan bir continuous future kaynağı.
- [ ] `2026-01-26 .. 2026-02-06` düşük-kalite penceresi için `low_quality_window` bayrağı (şu an yalnızca caveat olarak kayıtlı).
- [ ] Exchange tatil takvimi yok → "beklenmedik boşluk" kuralı sezgisel; uzun tatiller yanlış pozitif üretebilir (ERROR eşiği %5'e çekilerek telafi edildi).
- [ ] **Hisse sepeti için split ön-kaydı YOK**: `configs/splits_preregistered.yaml` şu an yalnızca BTC/GOLD/SILVER/BIST30(endeks) içeriyor. 28 hisse için ayrı ön-kayıt üretilmeli (Aşama 2 öncesi önerilir).
- [x] ~~Sepet ağırlıklandırma~~ → EŞİT-RİSK (KARAR 6, `basket_policy`)
- [ ] **Split v1.1 hisse bazlı etiketli bar sayısını azalttı** (TRAIN ~426 tradable bar/hisse). Bu, hisse başına in-sample tuning yasağının gerekçesidir; Aşama 9'da parametre seçimi YALNIZCA core varlıklarda yapılacak.
- [ ] **Stop mesafesi geniş** (medyan ~2,9 ATR / %6 fiyat): eşit-risk'te küçük pozisyon demek. Aşama 7'de alternatif anchor'lar test edilecek.
- [ ] **`levels_report.md` XU030'u hem `core_assets` hem `context_source` altında göstermiyor**; `context_source` anahtarı `BIST30` iken `XU030` olarak da anılıyor — Aşama 4'te isimlendirme netleştirilecek.
- [ ] **Sepet ağırlıklandırma politikası belirlenmedi**: eşit ağırlık mı, likidite ağırlıklı mı, piyasa değeri mi? Ayrıca hisse başına mı yoksa sepet başına mı sinyal üretileceği netleşmeli.
- [ ] **XU030 bağlam filtresi kodlanmadı**: rol YAML/config'te tanımlı ama "endeks EMA200 altındayken long bastır" kuralı henüz kod değil.
- [ ] DSTKF ve TRALT elendi; ikisi de BIST30 üyesi. Sepet 28 hisseyle BIST30'u TAM temsil etmiyor → bu bir temsil caveat'idir.
- [ ] `register_splits.py` her çalıştırmada snapshot'ı YENİDEN yazar. Sonuçlar görüldükten sonra yeniden çalıştırmak ön-kaydı fiilen SIFIRLAR → bu dosya bir kez yazılıp `--check` ile korunmalı; yeniden yazmak gerekirse `policy_version` artırılmalı ve eski YAML silinmemeli.
- [ ] `scripts/run_adjust.py` artık `run_data_qc.py --adjust` ile aynı işi yapıyor; ikisi birlikte çalıştırılırsa 1 bar kayabilir → tek komut olarak `run_data_qc.py` tercih edilmeli.

## AŞAMA DURUM LİSTESİ

| Aşama | Ad | Durum |
|---|---|---|
| 0 | Netleştirme / iskelet / config | ✅ Tamam (kararlar `configs/user_decisions.yaml`) |
| 1 | Veri kalitesi | ✅ **TAMAM** — toplama + 4H + QC + adjust + cleaning + split ön-kaydı (55/55 test) |
| 1.5 | BIST30 hisse üniversali | ✅ **TAMAM** — 30 üye sabitlendi, 28 hisse sepete girdi, rapor üretildi |
| 2 | Piyasa rejimi (EMA200 yönü + ATR yüzdeliği) + XU030 bağlam filtresi | ✅ **TAMAM** — 6 durum, fail-closed, look-ahead testi geçti |
| 3 | Yapısal seviyeler (swing + Donchian20 + ATR buffer stop) | ✅ **TAMAM** — 23 test, FrozenStop kilidi (DÜZELTME 2026-09-17: tablo bayattı) |
| 4 | Momentum onayı (ATR-normalize ROC) | ✅ **TAMAM** — 16 test, aday kümesi Aşama 9'a kilitli (DÜZELTME 2026-09-17) |
| 5 | Giriş tetiği + sinyal montajı + cooldown + icra zamanı | ✅ **TAMAM** — 19 test, 31 varlık, 3 akış raporlandı |
| 5b | Çift onayın KAPATILMASI: precision/recall/F1/false-positive + opsiyonel ML 3. filtre | ⬜ **YETKİ BEKLİYOR** |
| 6 | Baseline backtest (maliyet dahil, next-bar-open) | ✅ **TAMAM** — 26 test, `reports/backtest_baseline.*` + **2026-09-17 denetimi: 10/10 uyumlu, NO-GO (in-sample; bkz. `reports/stage6_audit.md`)** |
| 6d | Aşama 6 denetimi (şartname + go/no-go + sapma listesi + basket attrs) | ✅ **TAMAM** — 173/173, D1–D8 bulguları onay bekliyor |
| 7 | Stop / esnek kâr alma (partial+runner, trailing, breakeven, time-stop) | ✅ **TAMAM** (2026-09-17) — grid 4 profil × 3 anchor × 4 varlık, IN-SAMPLE, **SEÇİM YOK** (Aşama 9); P0×A0 regresyon kilidi OK; D6 çözüldü; 192/192 |
| 8 | Risk modülü (pozisyon boyutu, günlük/haftalık limit, korelasyon, ısı) | ✅ **TAMAM** (2026-09-17) — portföy simülatörü + tavanlar; regresyon kilidi OK; 207/207 |
| 9 | Robustluk (walk-forward, parametre duyarlılığı, Monte Carlo) | ✅ **TAMAM** (2026-09-17) — protokol kilitli; **GEÇTİ=0, tümü watch_only**; TEST 1 kez; `reports/stage9_oos_verdict.md` |
| 10 | Opsiyonel ML ikinci onay (HistGradientBoosting + purged/embargo) | ⬜ **YETKİ BEKLİYOR** — NOT: `ml_policy.gate` = "yalnız kural tabanlı çekirdek OOS'ta GEÇERSE"; Aşama 9'da GEÇTİ=0 → gate şu an KAPALI |
| 11 | Çıktılar (raporlar, model kartı, kullanım kılavuzu, güvenlik kuralları) | ✅ **TAMAM** (2026-09-17) — `reports/final_verdict.md` + `models/model_card.md` + `ops_runbook.md` + README kapanışı · **ARAŞTIRMA-KAPALI / watch_only** · 223/223 |

## İPTAL EDİLEN / YASAKLANAN KAPSAM (kullanıcı kararı)

- ❌ ADX · Hurst · HMM · Choppiness Index · BB-width · Ichimoku · Supertrend · Keltner · Order block · Volume Profile/POC/HVN/LVN · Anchored VWAP · Fractal · StochRSI · MFI · OBV yığını
- ❌ Grafikte indikatör kalabalığı → **maksimum 3 görsel öğe:** mum + EMA200 + yapısal stop/hedef çizgileri
- ❌ ML zorunlu katman → ML yalnızca **opsiyonel ikinci onay filtresi**
- ❌ Perp sinyali (BTC funding yalnızca maliyet/bağlam)
- ✅ Kalan çekirdek: **trend yönü (EMA200) + momentum onayı (ATR-normalize ROC) + yapısal stop + esnek kar alma**

## ÇALIŞTIRMA

```bash
cd /home/user/quant4h
python3 -W ignore tests/test_resample_qc.py                 # 21/21 beklenir
python3 -W ignore scripts/run_data_qc.py --timeframe 4h --min-rows 1500
# raporlar: reports/qc_report.md · reports/qc_report.json · reports/qc_findings.csv
```
