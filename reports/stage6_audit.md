# AŞAMA 6 DENETİM RAPORU — stage6_audit

*Tarih: 2026-09-17 · Denetleyen: yeni oturum (devralma) · Yetki: kullanıcı onayı 2026-09-17 (madde 2a–2d)*
*Yöntem: rapor/kod/test OKUMA + doğrulama çalıştırmaları. Mevcut koddan TEK SATIR değiştirilmedi. Tek yeni kod, 2d'nin açık yetkisiyle eklenen `scripts/make_basket_attrs.py` + `tests/test_basket_attrs.py` (yeni dosyalar; mevcut dosyalara dokunmaz).*
*Ortam: Python 3.11.2 · pandas 3.0.5 · numpy 2.4.6 (requirements.txt ile birebir) · clone `b58144b`, ağaç temiz.*

---

## 0) ÖZET HÜKÜM

- **2a şartname denetimi: 10/10 madde UYUMLU.** Fill kuralları (open[t+1], aynı-bar STOP önceliği, gap doldurma, çift taraf maliyet, H35 kilidi, tune yasağı, bootstrap CI, capped primary, basket agregasyonu/appendix ayrımı) kod + test + rapor üçgeninde doğrulandı.
- **2b go/no-go: GENEL NO-GO (beklenen durum).** Aşama 6 in-sample baseline'dır; "OOS expectancy" koşulu bu aşamada ÖLÇÜLEMEZ (Aşama 9). In-sample sayılarla bile SILVER ve BIST30 sepeti PF/CI eşiklerini geçemiyor; GOLD istatistiksel zayıf. Raporun kendi dürüst sonucuyla tutarlı: bu tablodan karar üretilmez.
- **2c sapma listesi: 8 bulgu (D1–D8), hiçbiri fill-kuralı ihlali değil.** En önemlileri: go/no-go eşiklerinin ve "kabul kriteri 1–8" listesinin repoda KAYITLI OLMAMASI (D1) ve `user_decisions.yaml`'daki iki bayat blok (D4, D5). Hiçbir düzeltme onaysız yapılmadı.
- **2d: `bist30_basket_4h_frozen.attrs.json` DETERMİNİSTİK ÜRETİLDİ + 6 testle kilitlendi.** Frozen parquet'in sha256'sı değişmedi; `register_splits.py --check` üretimdensonra da GEÇİYOR.
- **Test durumu: 173/173 PASS** (denetim öncesi 167 + yeni `basket_attrs` 6).

---

## 1) 2a — ŞARTNAME DENETİMİ (madde madde kanıt)

| # | Şartname maddesi | Hüküm | Kanıt (kod · test · rapor) |
|---|---|---|---|
| 1 | Primary akış **capped** | ✅ | `run_backtest.py:52 PRIMARY_VARIANT="capped"`; `backtest_baseline.json → primary_variant:"capped"`; rapor başlığı; STRICT yalnız tanısal tablo, COOLDOWN_ONLY backtest EDİLMEDİ (rapor §giriş + json `signal_variant_note`) |
| 2 | İcra **open[t+1]** | ✅ | `engine.py` adım 2: `prev=t−1` sinyali → `entry_px=open_[t]`; testler `test_entry_is_next_bar_open_and_costs_are_charged_both_sides`, `test_signal_on_last_bar_produces_no_trade`, `test_backtest_has_no_lookahead_on_truncated_data`; signals tarafı `test_execution_is_next_bar_open_not_signal_close` |
| 3 | Aynı-bar çakışmada **STOP öncelikli** | ✅ | `engine.py`: `if hit_stop and hit_tp → reason="stop"` (pesimist gap fill ile); `config.py:696–699`: `same_bar_priority != "stop"` → ValueError; test `test_same_bar_stop_and_tp_collision_is_pessimistic` |
| 4 | Maliyetler **çift taraf** (komisyon+spread+slippage) | ✅ | `engine._close_trade`: `c_entry + c_exit = one_way × notional (her iki bacak)`; `apply_costs_both_sides=True` (default); testler `test_total_cost_equals_sum_of_per_trade_costs`, `test_costs_turn_a_gross_winner_into_a_net_loser_is_reported`; json: BTC 31bp / GOLD-SILVER 20bp / basket 120bp gidiş-dönüş; `config.py` 120bp assert kilidi (H18) |
| 5 | **H35 kilidi** (geçerli stopu olmayan pozisyon açılmaz) testli mi | ✅ | `engine.py`: `require_valid_stop and (not sv or not finite(sp)) → rejected_no_stop`; ek geometri reddi (stop girişin yanlış tarafında); testler `test_position_without_valid_stop_is_never_opened`, `test_stop_on_wrong_side_of_entry_is_rejected`, `test_entry_on_non_tradable_bar_is_rejected`; üretim koşusunda `rejected_no_valid_stop=0` (sinyal katmanı `stop_valid` ile ön-filtreli — sayaç raporlanıyor) |
| 6 | **Bootstrap CI** var mı | ✅ | `engine.bootstrap_ci` (seed=42, B=1000, trade-resampling); n≥5 ise HER zaman hesaplanır (H44); test `test_metrics_and_weak_sample_flag`; raporda 3 core + basket için CI95 + P(expR>0) tabloları mevcut |
| 7 | Hisse tarafı **basket agregasyonu** (hisse bazlı tablo yalnız appendix) | ✅ | Rapor §2 "ANA SONUÇ (BASKET AGREGASYONU)" · §3 "EK (APPENDIX) — HİSSE BAZLI TABLO" + kabul kriteri 6 notu; 28/28 hisse ⚠ İSTATİSTİKSEL ZAYIF bayraklı; json'da `basket` ile `stocks_appendix` ayrı anahtarlar |
| 8 | Parametreler varsayılan, **tune yok** | ✅ | json `exit_config`: TS=90, TP=3.0, `tuned_now:False`, `tuning_stage:9`, adaylar [60,90,120]×[2,3,4]; `config.py:694–695 tune_now → ValueError`; engine girişte ikinci kontrol; buffer {0.5,1.0,1.5} `config.py:571` + levels ValueError kilidi |
| 9 | Gap doldurma规则leri | ✅ | Stop gap'i → open (aleyhimize), TP gap'i → open (lehimize/gerçekçi limit-fill), time-stop → kapanış; testler `test_stop_gap_fill_uses_open_when_open_is_worse`, `test_take_profit_gap_fill_uses_open_when_open_is_better`, `test_stop_normal_fill_uses_stop_price`, `test_take_profit_normal_fill_uses_tp_price`, `test_time_stop_fires_at_exact_bar_count` |
| 10 | Stop pozisyon boyunca **dondurulmuş** | ✅ | `test_stop_is_frozen_throughout_the_position`; equity bağımsız yeniden hesabı `equity_from_trades` (kabul kriteri 8) + `test_equity_recomputed_from_trades_matches_engine` |

**Fill-kuralı ihlali BULUNAMADI.** Tek teorik kenar durum → D6.

## 2) 2b — GO/NO-GO DEĞERLENDİRMESİ

**Ön bulgu (D1):** Kullanıcının atıf yaptığı eşikler (`OOS expectancy>0 ve CI altı>0 · PF≥1.2 · max DD≤%25 · min trade core≥100/basket≥150`) **user_decisions.yaml'da veya repoda KAYITLI DEĞİL** (arama: "no-go" 0 sonuç; repoda mevcut yakınları: `min_trades_for_significance=100` config.py:680, DD −%25 uyarısı engine.py, kodda atıf yapılan "kabul kriteri 2/3/4/6/7/8" numaraları — liste repoda tanımsız). Değerlendirme, kullanıcının bu oturumda yazılı verdiği eşiklerle yapıldı; eşiklerin yaml'a işlenmesi ONAY BEKLİYOR.

**Kritik kapsam notu:** Aşama 6 raporu **IN-SAMPLE**'dır ("Train/valid/test ayrımı UYGULANMADI" — rapor caveat). Bu yüzden 1. koşulun **OOS** bacağı hiçbir varlık için ölçülemez; aşağıdaki CI/expR değerleri in-sample okumadır. Nihai go/no-go Aşama 9'da.

| Varlık | expR>0 | CI altı>0 (in-sample) | PF≥1.2 | max DD≤%25 | min trade | **HÜKÜM** |
|---|---|---|---|---|---|---|
| **BTC** | ✅ +0.206 | ✅ +0.006 (sınırda) | ✅ 1.307 | ✅ −7.05% | ✅ 187≥100 | **GEÇTİ (in-sample)** · OOS Aşama 9'da · zayıf değil |
| **GOLD** | ✅ +0.626 | ✅ +0.093 | ✅ 2.673 | ✅ −2.12% | ❌ 30<100 | **İSTATİSTİKSEL ZAYIF** (diğerleri IS geçse de karar üretmez) |
| **SILVER** | ~ +0.002 (nominal) | ❌ −0.419 | ❌ 0.935 | ✅ −2.88% | ❌ 34<100 | **KALDI** (CI 0'ı içeriyor + PF<1.2 + zayıf) |
| **BIST30 sepet** | ~ +0.077 (nominal) | ❌ −0.133 | ❌ 0.931 | ✅ −0.78% (equity) / −8.19% (trade) | ✅ 172≥150 (ve ≥100) | **KALDI** (CI + PF) · survivorship bias caveat'li |

**GENEL: NO-GO** — Aşama 6 bir baseline'dır; PROGRESS ve raporun kendi hükmü gereği Aşama 7 + Aşama 9 olmadan bu tablodan HİÇBİR karar üretilemez. Denetim bu hükmü TEYİT eder, değiştirmez.

Not: sepette 172 trade her iki eşiği de (100/150) geçtiği için D2'deki eşik farkı bu koşuda sonucu etkilemiyor.

## 3) 2c — SAPMA / BULGU LİSTESİ (kod değiştirilmedi; tümü onay bekliyor)

| # | Bulgu | Önem | Öneri |
|---|---|---|---|
| **D1** | Go/no-go eşikleri + "kabul kriteri 1–8" listesi repoda kayıtlı değil (kod/rapor numaralara atıf yapıyor; liste kayıp Part 1/2 şartname mesajındaydı) | YÜKSEK (yönetişim) | Eşikler + kabul kriterleri `user_decisions.yaml`'a karar bloğu olarak işlensin (onayla) |
| **D2** | Basket min-trade eşiği: kod tek eşik kullanıyor (100); kullanıcı ifadesi basket için 150 | DÜŞÜK (bu koşuda etkisiz) | D1 ile birlikte netleştirilsin |
| **D3** | Go/no-go'nun OOS bacağı Aşama 6'da ölçülemez (rapor zaten in-sample olduğunu söylüyor) | KAPSAM NOTU | Aşama 9'da ön-kayıtlı split'lerle ölçülecek |
| **D4** | `user_decisions.yaml → stage_gate` BAYAT: `current_stage:"1"`, `next_stage:"3"` — PROGRESS'e göre sıra Aşama 7 | ORTA (doküman) | Onayla güncellensin |
| **D5** | `user_decisions.yaml → basket_policy.split_preregistration` v1.0 sayıları içeriyor (grid 2158; TRAIN 678/449 · VALID 635/421 · TEST 677/448); bağlayıcı kaynak `splits_preregistered.yaml` v1.1: grid 1436; TRAIN 437/426 · VALID 395/385 · TEST 436/425; frozen 40.206 satır | ORTA (doküman) | Onayla v1.1'e senkronlansın |
| **D6** | Engine döngü sırası: aynı iterasyonda önce çıkış (adım 1) sonra giriş (adım 2) → teorik olarak bar t içinde kapanan pozisyonun aynı barın AÇILIŞINDA yeni girişe izin vermesi mümkün. Capped akışta ERİŞİLEMEZ (sinyal bastırma + cooldown≥4 + engine ömrü ≤ proxy ömrü), ama bunu kilitleyen test YOK | DÜŞÜK (teorik) | Aşama 7 çıkış motorunu değiştirirken kilitleyici test eklensin |
| **D7** | Aşama 6 toplamında kova ısısı UYGULANMAMIŞ (GOLD\|SILVER tek kova, korelasyon +0.77) — rapor "RİSK MODÜLÜ ÖNCESİ ÖNİZLEME" diye açıkça bayraklı | KAPSAM NOTU (Aşama 8) | Beyanla uyumlu; sapma değil, kayıt |
| **D8** | `end_of_data` zorunlu kapanışları: GOLD 1, basket 6 trade — ayrı reason + warning ile şeffaf | KAPSAM NOTU | Test ile kilitli (`test_open_position_at_end_is_closed_transparently`) |

Ayrıca bkz. PROGRESS'e işlenen DÜZELTME bloğu: (a) bayat AŞAMA DURUM tablosu (3/4/6 satırları) düzeltildi; (b) KARAR 6 bloğundaki "60.416 satır" ve eşlik eden v1.0 split sayıları → gerçek 40.206 (v1.1). KARAR 6 blok METNİ tarihî kayıt olarak silinmedi; düzeltme bloğuyla hükümsüz kılındı.

## 4) 2d — `bist30_basket_4h_frozen.attrs.json`

**Durum: DETERMİNİSTİK → ÜRETİLDİ + TEST EDİLDİ.**
- Kök neden: `register_splits._freeze` tek varlıklarda sidecar'ı kopyalıyor; `build_basket_split` basket parquet'ini yazıyor ama sidecar üretmiyordu.
- Çözüm: YENİ `scripts/make_basket_attrs.py` — girdileri `splits_preregistered.yaml (bist30_basket)` + frozen parquet (YALNIZ OKUMA) + 28 hisse sidecar'ı; çıktı tarih damgası İÇERMEZ → bayt-bayt yeniden üretilebilir. `--check` modu CI için.
- İçerik: şema notu (3 kolonlu takvim/tradability tablosu, OHLCV içermez), rows=40.206, n_stocks=28, stock_list, excluded (DSTKF, TRALT), per_stock_rows, tradable_rows, ortak pencere, grid_bars=1436, frozen_sha256 (H17 kilidiyle eşleşme bayrağı), 28 sidecar'dan toplanan bayrak toplamları (tam-geçmiş notuyla).
- Doğrulama: frozen parquet sha256 ÜRETİM ÖNCESİ=SONRASI aynı (`218de18b…f521`); `register_splits.py --check` üretimden sonra da EXIT 0; `tests/test_basket_attrs.py` **6/6** (determinizm, commit'li dosya eşitliği, parquet uyumu, sha/H17, toplamların bağımsız yeniden sayımı, --check exit kodları).

## 5) Koşulan doğrulamalar (olduğu gibi)

```
git clone → b58144b (ağaç temiz)
pip install -r requirements.txt → EXIT 0 (pandas 3.0.5, numpy 2.4.6, pyarrow 25.0.1, sklearn 1.9.1 …)
python scripts/register_splits.py --check → EXIT 0 "DOĞRULAMA OK … çakışma yok" (üretim öncesi VE sonrası)
test suite (11 dosya, kendi çalıştırıcıları) → 173/173 PASS
  adjust 14 · backtest 26 · basket_attrs 6 · bist_universe 12 · cleaning 11 · levels 23
  momentum 16 · regime_context 14 · resample_qc 21 · signals 19 · splits 11
frozen sha256: 5/5 YAML kilidiyle birebir (btc aab99f83… · gold f7d53a8e… · silver 1df18551… · bist30 ddc9669d… · basket 218de18b…)
```

## 6) SONUÇ ve ÖNERİLER (onay bekliyor; hiçbir kod/config değişikliği yapılmadı)

1. **Aşama 6 fill-kuralı ve kapsam açısından şartnameye UYGUN.** Sapma yok; 8 bulgunun 2'si yönetişim/doküman (D1, D4/D5), gerisi kapsam notu veya düşük riskli.
2. **Go/no-go: NO-GO (doğru davranış).** BTC in-sample eşikleri geçiyor ama OOS ölçümü Aşama 9'da; GOLD zayıf; SILVER ve sepet in-sample'da da kalıyor.
3. Onaya sunulan işler: (a) D1 eşiklerini + kabul kriterlerini `user_decisions.yaml`'a işlemek; (b) D4/D5 bayat blokları senkronlamak; (c) Aşama 7'de D6 için kilitleyici test.
4. **Aşama 7 (esnek kâr alma) YETKİ BEKLİYOR** — bu denetim onu başlatmaz.

*Bu rapor yatırım tavsiyesi değildir; tüm sayılar in-sample'dır ve geçmiş performans gelecek sonuçların göstergesi değildir.*
