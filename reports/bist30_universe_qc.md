# AŞAMA 1.5 — BIST30 Hisse Üniversesi QC Raporu

*Üretim: 2026-09-16 13:55:53 UTC* · ünivers sürümü **2026-09-16.v1** (dondurulmuş: 2026-09-16T12:10:00Z) · timeframe **4h** · maliyet **120 bp gidiş-dönüş**

## ZORUNLU CAVEAT'LER

- **[KRİTİK] SURVIVORSHIP_BIAS** — SURVIVORSHIP BIAS: Serbest kaynaklardan yalnızca BUGÜN (2026-09-16) BIST30'da olan hisseler indirilebilir. Geçmişte endekste olup sonradan ÇIKAN hisseler (endeksten düşme, birleşme, delist) veri setinde YOKTUR. Bu nedenle sepet backtest'i sistematik olarak YUKARI YÖNLÜ ÇARPITILMIŞTIR: geçmiş, bugünün kazananlarıyla test edilmektedir. BIST30 sonuçları BTC/GOLD/SILVER ile AYNI güven düzeyinde DEĞERLENDİRİLEMEZ.
- **[KRİTİK] POINT_IN_TIME_MISSING** — Point-in-time (tarihsel) üyelik verisi YOKTUR. Hangi hissenin hangi tarihte endekste olduğu bilinmediği için "o günkü endeks" yeniden KURULAMAZ. Uygulanan yaklaşım: sabit bugünkü liste + bu bias'ın açıkça raporlanması. Doğru çözüm, tarihsel üyelik verisi olan bir sağlayıcıdır.
- **[YÜKSEK] SOURCE_NOT_OFFICIAL** — Liste resmî Borsa İstanbul API'sinden DOĞRULANAMADI (DNS erişilemedi). Üç ticari kaynağın oybirliğine dayanır. Üyelik 3 ayda bir değişir; bu sürüm 2026-09-16 anına aittir.
- **[YÜKSEK] INTRADAY_LIMIT** — Yahoo 1h limiti 730 gün: hisse başına intraday geçmiş EN FAZLA ~2.4 yıl. BIST seansı 6.5 saat olduğu için günde yalnızca ~2 adet TAM 4H bar üretilir.
- **[ORTA] HALT_AND_PRICE_LIMITS** — BIST'te günlük fiyat marjı sınırlıdır ve devre kesici (halt) uygulanır. Marja yapışan barlar sinyalde KULLANILABİLİR ama gerçekçi execution VARSAYILAMAZ; bu barlar ayrıca işaretlenir.
- **[ORTA] COST_IS_APPROXIMATE** — Hisse maliyet modeli (10 bp komisyon + 30 bp spread + 20 bp slippage ≈ 120 bp gidiş-dönüş) YAKLAŞIKLAMADIR ve kullanıcının gerçek aracılık komisyonuyla değiştirilmelidir; sonuçları doğrudan etkiler.

## ÖZET

- Ünivers üyesi: **30** · İndirme başarılı: **30** · başarısız: **0**
- **SEPETE GİREN: 28** · **ELENE: 2**
- Medyan 4H bar sayısı: **1436** (min 403, max 1436)
- Medyan eksik bar oranı: **%4.77** · medyan thin bar oranı: **%0.0**
- Kurumsal aksiyon **olayı**: 4H penceresi içinde **482** (tüm geçmişte 482) · işaretli bar: **223** · bölünme adayı: 0 · halt/marj bayrağı: **161** · beklenmedik boşluk: **259**
- Ort. günlük TL hacim (son 60 seans): medyan **2,379 mn TL**

## HİSSE BAZLI QC TABLOSU

| Hisse | 4H bar | tam bar | ince bar | seans | gün | eksik % | thin % | sıfır-hacim (tam) | halt | k.a. olay (pencere) | k.a. işaretli bar | bölünme adayı | maks. oran adımı | gap | geçersiz getiri | ort. günlük hacim (mn TL) | QC | Durum |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| **TRALT** | 403 | 403 | 0 | 203 | 296 | %5.4 | %0 | %0.0 | 3 | 0 | 0 | 2 | 9 | 5,051 | AMBER (insufficient history) | ❌ ELENDİ |
| **DSTKF** | 797 | 797 | 0 | 401 | 587 | %5.1 | %0 | %0.0 | 89 | 0 | 0 | 5 | 16 | 1,556 | RED | ❌ ELENDİ |
| **THYAO** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 0 | 4 | 0 | 9 | 26 | 12,294 | AMBER | ✅ GİRDİ |
| **ASELS** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 0 | 6 | 0 | 9 | 26 | 10,741 | AMBER | ✅ GİRDİ |
| **AKBNK** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 4 | 6 | 0 | 9 | 26 | 8,468 | AMBER | ✅ GİRDİ |
| **ASTOR** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 3 | 4 | 0 | 9 | 26 | 7,430 | AMBER | ✅ GİRDİ |
| **TUPRS** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 0 | 10 | 0 | 9 | 26 | 7,322 | AMBER | ✅ GİRDİ |
| **YKBNK** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 2 | 2 | 0 | 9 | 26 | 6,747 | AMBER | ✅ GİRDİ |
| **ISCTR** | 1435 | 1435 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 1 | 6 | 0 | 9 | 27 | 6,742 | AMBER | ✅ GİRDİ |
| **SASA** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 8 | 0 | 0 | 9 | 26 | 6,084 | AMBER | ✅ GİRDİ |
| **EREGL** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 0 | 6 | 0 | 9 | 26 | 4,776 | AMBER | ✅ GİRDİ |
| **KCHOL** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 0 | 6 | 0 | 9 | 26 | 4,242 | AMBER | ✅ GİRDİ |
| **GARAN** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 0 | 6 | 0 | 9 | 26 | 3,317 | AMBER | ✅ GİRDİ |
| **BIMAS** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 0 | 17 | 0 | 9 | 26 | 3,078 | AMBER | ✅ GİRDİ |
| **SAHOL** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 1 | 6 | 0 | 9 | 26 | 2,540 | AMBER | ✅ GİRDİ |
| **TCELL** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 0 | 8 | 0 | 9 | 26 | 2,476 | AMBER | ✅ GİRDİ |
| **EKGYO** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 4 | 4 | 0 | 9 | 26 | 2,283 | AMBER | ✅ GİRDİ |
| **SISE** | 1435 | 1435 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 2 | 6 | 0 | 9 | 27 | 2,156 | AMBER | ✅ GİRDİ |
| **KRDMD** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 1 | 2 | 0 | 9 | 26 | 2,022 | AMBER | ✅ GİRDİ |
| **TTKOM** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 3 | 0 | 0 | 9 | 26 | 1,781 | AMBER | ✅ GİRDİ |
| **PETKM** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 2 | 0 | 0 | 9 | 26 | 1,475 | AMBER | ✅ GİRDİ |
| **MGROS** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 1 | 10 | 0 | 9 | 26 | 1,392 | AMBER | ✅ GİRDİ |
| **FROTO** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 0 | 12 | 0 | 9 | 26 | 1,385 | AMBER | ✅ GİRDİ |
| **VAKBN** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 5 | 0 | 0 | 9 | 26 | 1,365 | AMBER | ✅ GİRDİ |
| **PGSUS** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 0 | 0 | 0 | 9 | 26 | 1,338 | AMBER | ✅ GİRDİ |
| **GUBRF** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 24 | 0 | 0 | 9 | 26 | 1,095 | AMBER | ✅ GİRDİ |
| **ENKAI** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 2 | 14 | 0 | 9 | 26 | 962 | AMBER | ✅ GİRDİ |
| **TOASO** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 1 | 6 | 0 | 9 | 26 | 914 | AMBER | ✅ GİRDİ |
| **TAVHL** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 0 | 2 | 0 | 9 | 26 | 735 | AMBER | ✅ GİRDİ |
| **AEFES** | 1436 | 1436 | 0 | 722 | 1055 | %4.8 | %0 | %0.0 | 5 | 6 | 0 | 9 | 26 | 729 | AMBER | ✅ GİRDİ |

## ELENEN HİSSELER VE GEREKÇELERİ

> Eleme = **işaretleme**. Veri SİLİNMEZ; hisse `data/processed/bist30/` altında durur ve raporda görünür. Yalnızca sepet performansına alınmaz.

- **TRALT** (Türk Altın İşletmeleri A.Ş.) — bar sayısı 403 < 800; geçmiş 296 gün < 300 gün
- **DSTKF** (Destek Finans Faktoring A.Ş.) — bar sayısı 797 < 800; halt/marj bayrağı %11.2 > %5; 1 QC ERROR: 52 zero-range bars (high==low==open==close): 6.52% of data

## KURUMSAL AKSİYON POLİTİKASI (adjust.py felsefesiyle tutarlı)

- **OTOMATİK DÜZELTME YOK.** `close_raw` ve `adjclose` ayrı kolonlarda korunur.
- **Tespit GÜNLÜK seriden yapılır.** Ölçüldü: Yahoo'nun **1h** BIST serisinde `adjclose == close` (%100), yani intraday seri kurumsal aksiyon düzeltmesi İÇERMİYOR. Günlük seride `adjclose/close` oranı her ex-date'te adım değiştirir ve olay tarihleri 4H barlara `session_date` üzerinden taşınır.
- Sınıflandırma: adım + |log getiri| > 0.25 → `split` adayı; değilse `dividend_or_other`. **DÜRÜST SINIR:** bu kural yalnızca BÜYÜK (>%25 fiyat sıçramalı) bölünmeleri yakalar; 1.05:1 gibi küçük oranlı bölünmeler `dividend_or_other` olarak sınıflandırılır. Bu ünivers için tespit edilen bölünme adayı sayısı **0**'dır ve tüm olaylar yıllık temettü mevsimiyle (Mart–Haziran) uyumludur; yine de 'bölünme yoktur' iddiası DEĞİL, '>%25 sıçramalı bölünme yoktur' iddiasıdır.
- Etki: olay barı ve sonraki bar `return_valid=False` + `non_tradable=True`. Ex-date'i atlayan getiri **gerçek getiri değildir**.
- Hiçbir fiyat YAZILMAZ/DEĞİŞTİRİLMEZ; hiçbir bar SİLİNMEZ.

## XU030 ENDEKSİNİN ROLÜ

- `XU030.IS` **trade varlığı DEĞİLDİR**; `watch_only` modundadır.
- Rolü: **long'lar için bağlam filtresi** (ör. endeks EMA200 altındayken hisse LONG sinyalleri bastırılır).
- Endeks getirisi portföy performansına **YAZILMAZ**.
- Veri: `data/interim/bist30_4h.parquet` · maliyet modeli hisse sepeti için **120 bp** gidiş-dönüş (endeks için VİOP proxy'si GEÇERSİZ).
