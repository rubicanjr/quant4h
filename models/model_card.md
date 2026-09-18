# MODEL KARTI — quant4h (kural tabanlı 4H çekirdek + risk katmanı)

*Sürüm kimliği: repo `rubicanjr/quant4h` · Aşama 11 kapanışı 2026-09-17 · suite 225/225 · statü: **watch_only (araştırma-kapalı)***

## 1. Bu sistem NEDİR

BIST30 hisse sepeti (28 hisse, long-only) + GOLD/SILVER (GC=F/SI=F ön-ay, long+short) + BTC (Binance spot, long+short) üzerinde **4 saatlik** zaman diliminde çalışan, **kural tabanlı, deterministik ve tamamen ön-kayıtlı protokolle doğrulanmış** bir araştırma/sinyal sistemidir. Katmanlar:

| katman | kural | modül |
|---|---|---|
| Rejim | EMA200 yönü + ATR(14) yüzdelik dilimi → 6 durum; ilk 500 bar etiketsiz; fail-closed | `features/regime.py` |
| Bağlam | BIST long'ları yalnız KAPANMIŞ XU030 4H barı > EMA200 iken (as-of, maks yaş 120h) | `features/context.py` |
| Seviyeler | k=3 fraktal swing (onay +4 bar) · Donchian(20) yalnız KAPANMIŞ barlar · yapısal stop = swing ∓ buffer×ATR, **FrozenStop** (gevşetilmez) | `features/levels.py` |
| Momentum | TEK ölçüm: ATR-normalize ROC (n=10, m=1.0) — birimsiz, ölçekten bağımsız | `features/momentum.py` |
| Tetik | Donchian(20) kırılımı (`close > max(high[t-20..t-1])`) — yeni indikatör YOK | `strategy/signals.py` |
| İcra | sinyal bar t KAPANIŞI → giriş **open[t+1]** · aynı-bar çakışmada **STOP** öncelikli · gap'ler pesimist · maliyet çift taraf (BTC 31bp, metals 20bp, hisse 120bp gidiş-dönüş) · geçerli stopu olmayan pozisyon ASLA açılmaz (H35) | `backtest/engine.py` |
| Çıkış | P0: dondurulmuş stop + TS90 + TP3R (varsayılan, Aşama 9'da da a-priori) · P1–P3 mimarileri yalnız KARŞILAŞTIRILDI, seçilmedi | `backtest/engine.py`, `ExitConfig` |
| Risk | eşit-risk boyutlama (risk/stop-mesafesi, balanced %0.5) · tavanlar: toplam 6, BTC 2, GOLD 1, SILVER 1, sepet 3 · metals TEK kova ≤1×rpt · basket ≤3×rpt · banka ≤2 · günlük %2/haftalık %5 (realized, fail-closed) · 4 ardışık kayıp→20 bar fren · tavanlar YALNIZ girişte | `risk/limits.py`, `risk/simulator.py` |
| Doğrulama | ön-kayıtlı split'ler (v1.1, frozen sha256) · look-ahead silme testleri her katmanda · 225 regresyon testi · TEST tek look | `scripts/register_splits.py`, `run_stage9.py` |

## 2. Bu sistem NE DEĞİLDİR

- **Canlı işlem sistemi DEĞİLDİR** — emir iletim kodu yoktur, olmayacaktır.
- **Yatırım tavsiyesi DEĞİLDİR** — tüm çıktılar olasılıksal araştırma artefaktıdır.
- **Kanıtlanmış edge DEĞİLDİR** — Aşama 9 OOS hükmü: **GEÇTİ=0**; BTC ve BIST30 sepet KALDI (VALID expR negatif), GOLD/SILVER ZAYIF (örneklem yetersiz). Bkz. `reports/final_verdict.md`.
- **ML sistemi DEĞİLDİR** — ML yalnız opsiyonel ikinci onay olarak tasarlandı ve **gate KAPALI** (bkz. §4).
- **Tune edilmiş bir sistem DEĞİLDİR** — tüm parametreler varsayılan/kilitli aday kümeli; hisse başına in-sample tuning baştan YASAKTI (`PER_ASSET_IN_SAMPLE_TUNING_ALLOWED=False`); seçim tek noktada, yalnız TRAIN'de yapıldı.
- **"Garantili kazanç" iddiası YOKTUR** — hiçbir aşamada böyle bir dil kullanılmadı; kullanılamaz.

## 3. watch_only TANIMI (bağlayıcı)

`watch_only` = sistemin **hiçbir varlıkta** trade/paper-trade/pozisyon önerisi üretmediği statü:
1. **Emir YOK, pozisyon YOK, P&L takibi YOK, tavsiye YOK.**
2. Yalnız `ops_runbook.md`'deki **aylık sinyal izleme raporu** (sayaçlar + rejim durumu; trade üretmez) ve **çeyreklik ÖN-KAYITLI yeniden değerlendirme** (maks 4 look/yıl) yapılabilir.
3. Statü değişikliği (watch_only → paper/observe) YALNIZ: ön-kayıtlı yeni bir look'un `go_no_go` eşiklerini GEÇTİ vermesi + kullanıcı onayı + PROGRESS'e işlenmesi ile mümkündür.
4. KALDI hükmü veren varlıkta (BTC, BIST30 sepet) edge iddiası kurulamaz; ZAYIF varlıkta (GOLD, SILVER) hiçbir yönde iddia kurulamaz.

## 4. ml_policy_gate: **KAPALI** (kayıt)

`configs/user_decisions.yaml → ml_policy.gate`: *"yalnızca kural tabanlı çekirdeği OUT-OF-SAMPLE'da geçerse devreye girer"*. Aşama 9'da kural tabanlı çekirdek OOS'ta GEÇEMEDİ (GEÇTİ=0) → **gate KAPALI**. Sonuç: HistGradientBoosting tabanlı ikinci onay filtresi İNŞA EDİLEMEZ/DEVREYE ALINAMAZ; Aşama 10 ancak (a) runbook look'larında çekirdeğin GEÇTİ alması ve (b) açık kullanıcı yetkisi ile açılabilir. Bu kayıt 2026-09-17 itibarıyla bağlayıcıdır.

## 5. Performans özeti (kısaltılmış — tamamı raporlarda)

| ölçüm | değer | kaynak |
|---|---|---|
| OOS hüküm (VALID+TEST, ön-kayıtlı) | GEÇTİ 0 · KALDI 2 (BTC, basket) · ZAYIF 2 (GOLD, SILVER) | `reports/stage9_oos_verdict.md` |
| BTC seçili hücre VALID | n=7, expR −0.321 → TEST koşulmadı | `stage9_oos_verdict.json` |
| In-sample baseline (karar değeri YOK) | BTC net +%15.5 (PF 1.31) · sepet ≈ başabaş · hiçbir varlık buy&hold'u geçemedi | `reports/backtest_baseline.md` |
| Risk katmanı etkisi (in-sample) | maxDD −%17.7 → −%7.8; tepe ısı tavanlar altında | `reports/stage8_risk.md` |
| MC (OOS dizileri, B=1000) | P(maxDD>%25)=0.00 · P(ruin)=0.00 — küçük örneklem, güvenlik kanıtı DEĞİL | `stage9_oos_verdict.json` |

## 6. Bilinen sınırlar (dürüstlük kaydı — PROGRESS "KAYITLI TEŞHİSLER" tam liste)

Survivorship bias (sepet yalnız bugünkü üyeler; yukarı yönlü çarpık — buna rağmen KALDI) · metaller ~2.4 yıl intraday · TEST 159 gün (BTC) · ön-ay vadeli roll belirsizliği (FLAG-ONLY) · 2026-01/02 düşük-kalite feed penceresi · BIST 09:30-10:00 açılışı 4H'de temsil edilmez · tek fold walk-forward · grid faz farkı nedeniyle 4H ortak bar yok (korelasyon limiti yalnız günlük).

## 7. Yasaklı kapsam (bağlayıcı, `user_decisions.yaml → simplicity_rules`)

ADX · Hurst · HMM · Choppiness · BB-width · Ichimoku · Supertrend · Keltner · Order block · Volume Profile/POC · Anchored VWAP · Fractal levels · StochRSI · MFI · OBV · RSI+MACD+BB+Stoch yığını — kodda `ast` tabanlı testlerle kilitli. Grafikte maks **3 öğe**: mum + EMA200 + yapısal seviyeler.

## 8. Yeniden üretilebilirlik

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/register_splits.py --check     # ön-kayıt + frozen sha DOĞRULAMA
for t in tests/test_*.py; do .venv/bin/python -W ignore $t; done   # 225/225 beklenir
.venv/bin/python -W ignore scripts/run_stage9.py --phase verdict  # hükmü yeniden üretir (TEST'e YENİ look EKLEMEZ; deterministik)
```

Veri: `data/frozen/*` sha256 ile kilitli; canlı veri büyürse `drift_report` BİLGİ üretir, ön-kayıt ANCAK policy_version artırılarak yenilenir (eski dosya silinmez).

*Bu kart yatırım tavsiyesi değildir. Geçmiş performans gelecek sonuçların göstergesi değildir.*
