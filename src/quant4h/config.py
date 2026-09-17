"""
Central configuration for the 4H multi-asset signal research system.

Design rules
------------
* Every assumption that can be wrong is written down here, in one place.
* Nothing in this module fetches data or trains models; it is pure
  declarative configuration + typed accessors.
* Cost / risk defaults are conservative on purpose. Changing them is a
  research decision and must be reflected in the report.

All timestamps are handled as timezone-aware UTC internally
(``pandas.DatetimeTZDtype("UTC")``). Local session timezones are only used
for bar *construction*, never for storage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional

# --------------------------------------------------------------------------
# Global constants
# --------------------------------------------------------------------------

TIMEFRAME = "4h"          # primary decision timeframe
HTF = "1d"                # higher timeframe filter
LTF = "1h"                # optional lower timeframe refinement
UTC = "UTC"

CANONICAL_COLUMNS: List[str] = [
    "symbol", "timestamp_utc", "open", "high", "low", "close", "volume",
]
OPTIONAL_COLUMNS: List[str] = [
    "funding_rate", "open_interest", "spread", "quote_volume",
    "trades", "taker_buy_volume", "dxy", "usdtry", "benchmark",
]

# Minimum number of 4H bars we are willing to run a walk-forward study on.
MIN_BARS_FOR_STUDY = 1500
# Below this we only allow descriptive statistics, never model selection.
MIN_BARS_FOR_MODEL = 3000


# --------------------------------------------------------------------------
# Cost model
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CostModel:
    """Round-trip trading cost model, expressed in *fraction of notional*.

    ``slippage_bps`` is applied per side on top of half-spread. For research
    we deliberately over-estimate costs: a strategy that only survives at
    zero cost is not a strategy.
    """

    commission_bps: float          # per side, basis points of notional
    spread_bps: float              # FULL quoted spread, basis points
    slippage_bps: float            # per side, basis points of notional
    funding_bps_per_8h: float = 0.0  # perpetual futures carry (BTC only)
    borrow_cost_bps_per_day: float = 0.0

    @property
    def one_way_cost_frac(self) -> float:
        """Cost of a single side (entry OR exit) as a fraction of notional."""
        return (self.commission_bps + self.spread_bps / 2.0 + self.slippage_bps) / 1e4

    @property
    def round_trip_cost_frac(self) -> float:
        return 2.0 * self.one_way_cost_frac

    @property
    def round_trip_bps(self) -> float:
        return self.round_trip_cost_frac * 1e4

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# Risk profiles
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RiskProfile:
    name: str
    risk_per_trade: float            # fraction of equity risked to the stop
    max_daily_loss: float            # fraction of equity; halt for the day
    max_weekly_loss: float           # fraction of equity; halt for the week
    max_open_positions: int
    max_correlation: float           # |corr| above which two assets count as one
    max_leverage: float
    max_portfolio_heat: float        # sum of open risks, fraction of equity
    max_consecutive_losses: int      # after this, cut risk / stop
    loss_streak_risk_multiplier: float
    model_threshold: float           # minimum ML probability for a signal
    min_signal_score: float          # minimum composite confirmation score
    max_gross_exposure: float        # fraction of equity, all assets
    max_exposure_per_asset: float    # fraction of equity, single asset

    def scaled_risk(self, consecutive_losses: int) -> float:
        """Risk per trade after the drawdown governor is applied."""
        if consecutive_losses >= self.max_consecutive_losses:
            return 0.0
        if consecutive_losses >= max(2, self.max_consecutive_losses - 2):
            return self.risk_per_trade * self.loss_streak_risk_multiplier
        return self.risk_per_trade


RISK_PROFILES: Dict[str, RiskProfile] = {
    "conservative": RiskProfile(
        name="conservative", risk_per_trade=0.0025, max_daily_loss=0.01,
        max_weekly_loss=0.025, max_open_positions=2, max_correlation=0.55,
        max_leverage=1.0, max_portfolio_heat=0.0075, max_consecutive_losses=5,
        loss_streak_risk_multiplier=0.5, model_threshold=0.62,
        min_signal_score=0.65, max_gross_exposure=0.60, max_exposure_per_asset=0.25,
    ),
    "balanced": RiskProfile(
        name="balanced", risk_per_trade=0.005, max_daily_loss=0.02,
        # max_open_positions 3→6: Aşama 8 direktifi (2026-09-17) — user_decisions.yaml
        # senkronu; varlık-bazlı tavanlar risk/limits.py RiskLimits'te (BTC 2, GOLD 1,
        # SILVER 1, sepet 3, toplam 6).
        max_weekly_loss=0.05, max_open_positions=6, max_correlation=0.70,
        max_leverage=2.0, max_portfolio_heat=0.015, max_consecutive_losses=4,
        loss_streak_risk_multiplier=0.5, model_threshold=0.58,
        min_signal_score=0.60, max_gross_exposure=1.00, max_exposure_per_asset=0.40,
    ),
    "aggressive": RiskProfile(
        name="aggressive", risk_per_trade=0.01, max_daily_loss=0.035,
        max_weekly_loss=0.08, max_open_positions=4, max_correlation=0.80,
        max_leverage=3.0, max_portfolio_heat=0.03, max_consecutive_losses=3,
        loss_streak_risk_multiplier=0.5, model_threshold=0.55,
        min_signal_score=0.55, max_gross_exposure=1.80, max_exposure_per_asset=0.60,
    ),
}

DEFAULT_PROFILE = "balanced"


# --------------------------------------------------------------------------
# Assets
# --------------------------------------------------------------------------

@dataclass
class AssetSpec:
    """One tradable instrument + everything the pipeline needs to know about it."""

    key: str                      # internal short name, e.g. "BTC"
    symbol: str                   # canonical symbol stored in the data
    asset_class: str              # crypto | metal | equity_index | equity_future
    currency: str
    venue: str                    # binance_spot | yahoo_futures | yahoo_index | user_csv
    source_ticker: str            # ticker understood by the adapter
    raw_timeframe: str            # timeframe we download / receive
    native_session_tz: str        # timezone used to build session-aligned bars
    bar_anchor_local: str         # first bar of the 4H grid, in bar_anchor_mode's tz
    session_start_local: str      # local session open (informational)
    session_end_local: str        # local session close (informational)
    trading_days: List[int]       # 0=Mon ... 6=Sun
    continuous_24h: bool
    cost: CostModel
    session_anchor_local: str = "00:00"  # session OPEN, informational / overnight roll
    session_day_start_local: str = "00:00"
        # A bar starting at/after this local time belongs to THAT calendar day's
        # session; anything earlier rolls to the previous day. This is a manual
        # session-calendar decision and is deliberately SEPARATE from the bar
        # grid anchor: metals need 17:30 (daily halt 17:00-18:00 NY), BIST needs
        # 05:00 (nothing trades before 09:30 Istanbul, so any early-morning bin
        # still belongs to the same day).
    mode: str = "core"            # "core" | "watch_only" | "excluded"
                                  #   core       -> backtest portfoyune girer
                                  #   watch_only -> sinyal uretilir, portfoye ZORLA SOKULMAZ
                                  #   excluded   -> hic calistirilmaz
    volume_required: bool = True  # False ise hacim/onay bacagi bu varlikta devre disi
    caveats: tuple = ()           # her raporda AYNEN basilmasi zorunlu uyari metinleri
    min_source_bars_per_target: int = 1
        # 4H bar üretmek için gereken ASGARİ kaynak (1h) bar sayısı. 1 = ince
        # barlar tutulur. BIST için 4: yalnızca TAM barlar üretilir.
        # NEDEN BIST'te 3 (=%75 kapsama): BIST seansı 6.5 saat ve 10:00 lokal
        # grid 3 bin üretir; 06:00-10:00 bin'i YALNIZCA Yahoo'nun 09:30
        # "açılış anı" printini taşır (n_src=1). Bu ince bar non_tradable
        # olduğu için anchor olamaz ve k=3 fraktalın 6 komşusu HER ZAMAN en az
        # bir ince bara denk gelir -> HİÇBİR swing onaylanamaz (ölçüldü: 28
        # hissede swing=0, Donchian=0, stop=0).
        # 4 DEĞİL 3: ölçüldü ki Yahoo BIST 1h feed'inde 17:30 printi günlerin
        # ~%45'inde YOK; dolayısıyla 14:00-18:00 bin'i çoğu gün 3 kaynak bar
        # içerir. min=4 istenirse 323 seans tek bara düşüyor ve "eksik bar"
        # %26.5'e çıkıp tüm sepet eleniyordu. 3 bar = seansın ≥%75'i, ki bu
        # projenin "ince bar" eşiğiyle (<%75) birebir tutarlıdır.
        # Sonuç: günde 2 bar (10-14 ve 14-18 lokal = 07/11 UTC), ~%5 eksik.
        # BEDELİ: 09:30-10:00 açılış hareketi 4H barlarda temsil edilmez.
    requires_adjustment: bool = False
        # True ise (on-ay vadeli seriler: GC=F, SI=F) roll / veri-kesintisi
        # duzeltmesi UYGULANMADAN bu varlik 'model icin uygun' sayilmaz.
        # QC bunu ERROR olarak isaretler ve usable_for_modelling=False kalir.
    bar_anchor_mode: str = "utc"  # "utc" | "local". "local" keeps session semantics
                                  # stable across DST but the UTC bar times shift twice a
                                  # year; "utc" keeps one single grid all year round.
    min_tick: Optional[float] = None
    contract_multiplier: float = 1.0
    margin_required_frac: float = 1.0   # 1.0 = unlevered / cash
    has_volume: bool = True
    tradable: bool = True
    tradability_note: str = ""
    htf_source_ticker: Optional[str] = None
    ltf_source_ticker: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    @property
    def bars_per_session(self) -> int:
        raise NotImplementedError("computed by resampling.calendar_for()")


# Default, provisional instrument choices.
# >>> THESE ARE ASSUMPTIONS AND MUST BE CONFIRMED BY THE USER (see
# >>> docs/02_DATA_REQUEST.md). They are provisional so that the pipeline
# >>> can be built and tested against free, verifiable data.
_CryptoCost = CostModel(commission_bps=10.0, spread_bps=3.0, slippage_bps=4.0,
                        funding_bps_per_8h=1.0)
_MetalCost = CostModel(commission_bps=3.0, spread_bps=4.0, slippage_bps=5.0)
# KARAR 1: BIST30 icin execution varsayimi = VIOp XU030 futures maliyet modeli.
# Endeks verisi uzerinden calisiyoruz ama maliyeti vadeli islem gibi hesapliyoruz
# (komisyon + spread proxy + slippage). Bu, gercek maliyetin BILINCLI bir
# yaklasiklamasidir; canli islem maliyetiyle birebir ayni degildir.
_ViopCost = CostModel(commission_bps=6.0, spread_bps=15.0, slippage_bps=15.0)
_IndexCost = _ViopCost  # geriye donuk uyumluluk

DEFAULT_ASSETS: Dict[str, AssetSpec] = {
    "BTC": AssetSpec(
        key="BTC", symbol="BTCUSDT", asset_class="crypto", currency="USDT",
        venue="binance_spot", source_ticker="BTCUSDT", raw_timeframe="4h",
        native_session_tz=UTC, bar_anchor_local="00:00", session_anchor_local="00:00",
        session_start_local="00:00", session_end_local="23:59",
        trading_days=[0, 1, 2, 3, 4, 5, 6], continuous_24h=True,
        cost=_CryptoCost, min_tick=0.01, contract_multiplier=1.0,
        margin_required_frac=1.0, has_volume=True, tradable=True,
        caveats=(
            "BTCUSDT SPOT serisi sinyal verisidir. Funding yalnizca maliyet/baglam "
            "katmanidir; PERP SINYALI URETILMEZ.",
        ),
        tradability_note="Spot BTCUSDT. Funding = cost/context only, no perp signals.",
        htf_source_ticker="BTCUSDT", ltf_source_ticker="BTCUSDT",
        extras={"perp_ticker": "BTCUSDT", "funding": True},
    ),
    "GOLD": AssetSpec(
        key="GOLD", symbol="XAUUSD_PROXY_GC", asset_class="metal", currency="USD",
        venue="yahoo_futures", source_ticker="GC=F", raw_timeframe="1h",
        native_session_tz="America/New_York", bar_anchor_local="18:00",
        bar_anchor_mode="local", session_anchor_local="18:00",
        session_day_start_local="17:30",
        session_start_local="18:00", session_end_local="17:00",
        trading_days=[0, 1, 2, 3, 4], continuous_24h=False,
        cost=_MetalCost, min_tick=0.10, contract_multiplier=100.0,
        margin_required_frac=0.10, has_volume=True, tradable=True,
        requires_adjustment=True,   # KARAR 2: on-ay vadeli -> roll/kesinti duzeltmesi SART
        caveats=(
            "GC=F ON-AY vadeli serisidir: roll gap duzeltmesi yapilmadan ham getiri serisi "
            "KULLANILAMAZ. Roll tespiti (gap > esik ATR) zorunludur. requires_adjustment=True "
            "oldugu icin duzeltme calistirilana kadar QC bu varligi 'model icin uygun DEGIL' "
            "olarak isaretler.",
            "Intraday gecmis ~2.4 yil ile sinirlidir (Yahoo 1h limiti 730 gun).",
            "TESPIT (KARAR 3): 2026-01-30 15:00 UTC -> 2026-02-02 18:00 UTC arasinda 75 saatlik "
            "VERI KESINTISI var (normal hafta sonu 80 bar; burada Pazartesi 00:00-15:00 UTC de "
            "kayip). 2026-02-02 gunu yalnizca 5 bar gelmis (normal ~23). Kesintiyi atlayan "
            "-%7.97'lik getiri NE ROLL NE BAD PRINT'tir: SAHTE bir getiridir. BAR SILINMEZ, "
            "'boslugu atlayan getiri' olarak isaretlenir ve getiri/roll hesaplarinda HARIC TUTULUR.",
            "UYARI: 2026-01-26 .. 2026-02-06 penceresinde fiyat 5.626 -> 4.653 arasinda "
            "(yaklasik -%17) savruluyor ve gunluk hacim onceki donemin %38'ine dusuyor. "
            "Feed kalitesi bu pencerede DUSUK; ayni kesinti SILVER'da da birebir ayni "
            "tarihlerde goruluyor (Yahoo kaynakli ortak sorun). Bu doneme dayandirilan "
            "sonuclara guvenilmez, egitim/validasyonda ayrica isaretlenmelidir.",
        ),
        tradability_note=(
            "PROVISIONAL: COMEX front-month gold future (GC=F) used as the "
            "XAUUSD proxy. Front-month only => roll gaps are NOT adjusted. "
            "Intraday (1h) history is ~2 years. Replace with a spot XAUUSD "
            "feed or a roll-adjusted continuous future before trusting results."
        ),
        htf_source_ticker="GC=F", ltf_source_ticker="GC=F",
        extras={"alt_tickers": ["XAUUSD=X", "GLD", "PAXGUSDT", "XAUTUSDT"]},
    ),
    "SILVER": AssetSpec(
        key="SILVER", symbol="XAGUSD_PROXY_SI", asset_class="metal", currency="USD",
        venue="yahoo_futures", source_ticker="SI=F", raw_timeframe="1h",
        native_session_tz="America/New_York", bar_anchor_local="18:00",
        bar_anchor_mode="local", session_anchor_local="18:00",
        session_day_start_local="17:30",
        session_start_local="18:00", session_end_local="17:00",
        trading_days=[0, 1, 2, 3, 4], continuous_24h=False,
        cost=_MetalCost, min_tick=0.005, contract_multiplier=5000.0,
        margin_required_frac=0.10, has_volume=True, tradable=True,
        requires_adjustment=True,   # KARAR 3: on-ay vadeli -> roll/kesinti duzeltmesi SART
        caveats=(
            "SI=F ON-AY vadeli serisidir: roll gap duzeltmesi zorunludur. requires_adjustment=True "
            "oldugu icin duzeltme calistirilana kadar QC bu varligi 'model icin uygun DEGIL' "
            "olarak isaretler.",
            "Intraday gecmis ~2.4 yil ile sinirlidir (Yahoo 1h limiti 730 gun).",
            "TESPIT (KARAR 3): 2026-02-02'deki tek barlik -%22 hareket incelendi. SONUC: bu NE "
            "ROLL NE BAD PRINT'tir. 2026-01-30 15:00 UTC -> 2026-02-02 18:00 UTC arasinda 75 "
            "saatlik VERI KESINTISI var (normal hafta sonu 80 bar; burada Pazartesi 00:00-15:00 "
            "UTC de kayip) ve 2026-02-02 gunu yalnizca 5 bar gelmis (normal ~23). Dolayisiyla "
            "-%22, veri boslugunu atlayan SAHTE bir getiridir. BAR SILINMEZ; 'boslugu atlayan "
            "getiri' olarak isaretlenir ve getiri/roll/label hesaplarinda HARIC TUTULUR.",
            "UYARI: 2026-01-26 .. 2026-02-06 penceresinde fiyat 121.79 -> 66.88 arasinda "
            "(yaklasik -%45) savruluyor ve gunluk hacim onceki donemin %42'sine dusuyor. "
            "Ayni kesinti GOLD'da da birebir ayni tarihlerde var (Yahoo kaynakli ortak sorun). "
            "Bu pencerede feed kalitesi COK DUSUK; model egitimi/validasyonunda ayrica "
            "isaretlenmeli, sonuclar bu doneme dayandirilmamali.",
        ),
        tradability_note="PROVISIONAL: COMEX front-month silver future (SI=F). "
                         "Same roll-gap caveat as GOLD.",
        htf_source_ticker="SI=F", ltf_source_ticker="SI=F",
        extras={"alt_tickers": ["XAGUSD=X", "SLV"]},
    ),
    "BIST30": AssetSpec(
        key="BIST30", symbol="XU030_INDEX", asset_class="equity_index", currency="TRY",
        venue="yahoo_index", source_ticker="XU030.IS", raw_timeframe="1h",
        # KARAR 1: XU030.IS sinyal motoru olarak kalir ama DOGRUDAN TRADE EDILEMEZ.
        mode="watch_only", volume_required=False,
        caveats=(
            "BIST30 dogrudan trade edilemez: XU030.IS endeksin kendisidir. "
            "Execution VIOp XU030 vadeli maliyet modeliyle VARSAYIMSAL olarak modellenir.",
            "Hacim verisi YOKTUR (her bar 0). Hacim/onay bacagi bu varlikta KULLANILMAZ; "
            "cift onay burada trend + momentum ile sinirlidir.",
            "Gecmis sadece ~2.9 yil. 4H bar sayisi ~2.157 gorunur ama bunun ~721 adedi "
            "yalnizca 09:30 ACILIS ANI printini iceren INCE barlardir; TAM 4H bar sayisi "
            "~1.436'ddir. BTC'nin 19.888 bariyla karsilastirildiginda istatistiksel guc "
            "COK DUSUKTUR; sonuclar yalnizca yon gosterir, kesinlik iddia edilemez.",
            "Alternatif VIOp XU030 futures gecmisi bulunamadigi surece BIST30 backtest "
            "portfoyune ZORLA SOKULMAZ, izleme modunda kalir.",
            "4H grid faz farki: BIST30 barlari 07/11 UTC'de, BTC barlari 00/04/08 UTC'de "
            "acilir. Bu yuzden varliklar arasi korelasyon YALNIZCA GUNLUK bazda hesaplanir; "
            "4H seviyesinde ortak bar yoktur (n=0).",

        ),
        # KARAR/H4 (3. iterasyon): grid 10:00 Istanbul lokal.
        #  Yahoo XU030.IS 1h barlari 09:30,10:30,...,17:30 lokal saatlerde gelir.
        #  10:00 anchor => 10-14 ve 14-18 lokal olmak uzere SEANS BASINA 2 TAM 4H
        #  BAR (her biri 4 kaynak bar). 06:00-10:00 bin'i yalnizca 09:30 "acilis
        #  ani" printini icerdigi icin (n_src=1) elenir.
        #  BEDELLERI (ikisi de raporlarda caveat):
        #   (1) 09:30-10:00 acilis hareketi 4H barlarda YOKTUR.
        #   (2) Grid 4h UTC gridine (00/04/08...) 3 saat faz farkiyla oturur
        #       (07/11 UTC), bu yuzden BTC ile 4H ortus bar = 0; varliklar arasi
        #       korelasyon YALNIZCA GUNLUK bazda hesaplanir.
        #  Turkiye DST uygulamadigi (kalici UTC+3) icin bu saatler yil boyu sabittir.
        native_session_tz="Europe/Istanbul", bar_anchor_local="10:00",
        session_anchor_local="09:30", session_day_start_local="05:00",
        bar_anchor_mode="local", min_source_bars_per_target=3,
        session_start_local="09:30", session_end_local="18:00",
        trading_days=[0, 1, 2, 3, 4], continuous_24h=False,
        cost=_ViopCost, min_tick=0.01, contract_multiplier=1.0,
        margin_required_frac=0.15, has_volume=False, tradable=False,
        tradability_note=(
            "NOT DIRECTLY TRADABLE. XU030.IS is the index itself: volume == 0 "
            "on every bar, intraday history only ~2 years, and the session "
            "(09:30-18:00 Europe/Istanbul) does not divide evenly into 4H UTC "
            "bars. Options: (a) VIOP XU030 near-month future, (b) an ETF "
            "(e.g. FBIST/ZPX30 style), (c) an equal/cap-weighted basket of "
            "liquid constituents, (d) index daily bars for the HTF filter only."
        ),
        htf_source_ticker="XU030.IS", ltf_source_ticker=None,
        extras={
            "liquid_constituents": [
                "AKBNK.IS", "GARAN.IS", "ISCTR.IS", "YKBNK.IS", "THYAO.IS",
                "ASELS.IS", "EREGL.IS", "SISE.IS", "TUPRS.IS", "BIMAS.IS",
                "KCHOL.IS", "SAHOL.IS", "TCELL.IS", "FROTO.IS", "SASA.IS",
            ],
        },
    ),
}

# --------------------------------------------------------------------------
# BIST30 hisse sepeti (AŞAMA 1.5)
# --------------------------------------------------------------------------
# KARAR: "BIST30" = konstitüant HİSSELERİ. XU030 endeksi trade varlığı değil,
# long'lar için bağlam filtresidir. Hisse maliyet modeli configs/
# user_decisions.yaml ve configs/bist30_universe.yaml içinde kayıtlıdır.
# CostModel sözleşmesi: commission_bps ve slippage_bps TEK TARAF, spread_bps
# ise TAM kotasyon spread'idir (tek tarafa yarısı yazılır). Kullanıcının
# onayladığı 120 bp GİDİŞ-DÖNÜŞ hedefini birebir vermek için:
#   tek taraf = 10 (komisyon) + 60/2 (yarım spread) + 20 (slippage) = 60 bp
#   gidiş-dönüş = 2 x 60 = 120 bp
# (user_decisions.yaml içindeki "spread_bps: 30" ifadesi TEK TARAF yarım-spread
#  maliyetidir; buradaki 60 ise TAM spread'dir. Aynı ekonomik varsayım, iki
#  farklı birim sözleşmesi — karışıklığı önlemek için ikisi de belgelendi.)
_BistStockCost = CostModel(commission_bps=10.0, spread_bps=60.0, slippage_bps=20.0)
BIST_STOCK_ROUND_TRIP_BPS = _BistStockCost.round_trip_bps      # == 120.0 bp
assert abs(BIST_STOCK_ROUND_TRIP_BPS - 120.0) < 1e-9, BIST_STOCK_ROUND_TRIP_BPS

BIST_STOCK_CAVEATS = (
    "SURVIVORSHIP BIAS: yalnızca BUGÜN BIST30'da olan hisseler indirilebilir; "
    "geçmişte endekste olup sonradan çıkanlar YOKTUR. Sonuçlar sistematik olarak "
    "YUKARI yönlü çarpıktır ve BTC/GOLD/SILVER ile aynı güven düzeyinde "
    "DEĞERLENDİRİLEMEZ.",
    "Point-in-time üyelik verisi yoktur: 'o günkü endeks' yeniden KURULAMAZ.",
    "Yahoo 1h limiti 730 gün -> hisse başına intraday geçmiş en fazla ~2.9 yıl; "
    "BIST seansı 6.5 saat olduğu için günde yalnızca ~2 TAM 4H bar üretilir.",
    "BIST'te günlük fiyat marjı sınırlıdır ve devre kesici uygulanır; marja "
    "yapışan barlar sinyalde kullanılabilir ama gerçekçi execution VARSAYILAMAZ.",
    "Maliyet modeli (10+30+20 bp = 120 bp gidiş-dönüş) YAKLAŞIKLAMADIR; "
    "kullanıcının gerçek aracılık komisyonuyla değiştirilmelidir.",
    "Kurumsal aksiyonlar (temettü/bölünme) OTOMATİK DÜZELTİLMEZ; yalnızca "
    "İŞARETLENİR (adjust.py felsefesi). close_raw ve adjclose ayrı tutulur.",
)


def make_bist_stock_spec(code: str, name: str = "", sector: str = "",
                         min_tick: float = 0.01) -> AssetSpec:
    """Build an AssetSpec for one BIST30 constituent.

    Grid: 10:00 Europe/Istanbul, local anchor mode. Turkey does not observe DST
    (permanent UTC+3 since 2016) so the UTC bar times are stable all year:
    07:00 and 11:00 UTC -> exactly 2 full 4H bars per session, plus one thin
    03:00 UTC bar that only carries Yahoo's 09:30 opening snapshot.
    """
    return AssetSpec(
        key=f"BIST_{code}", symbol=f"{code}.IS", asset_class="equity", currency="TRY",
        venue="yahoo_stock", source_ticker=f"{code}.IS", raw_timeframe="1h",
        native_session_tz="Europe/Istanbul", bar_anchor_local="10:00",
        session_anchor_local="09:30", session_day_start_local="05:00",
        bar_anchor_mode="local", min_source_bars_per_target=3,
        session_start_local="09:30", session_end_local="18:00",
        trading_days=[0, 1, 2, 3, 4], continuous_24h=False,
        cost=_BistStockCost, min_tick=min_tick, contract_multiplier=1.0,
        margin_required_frac=1.0, has_volume=True, tradable=True,
        mode="core", volume_required=True, requires_adjustment=False,
        caveats=BIST_STOCK_CAVEATS,
        tradability_note=f"BIST30 konstitüant hissesi: {name or code} ({sector or 'n/a'})",
        htf_source_ticker=f"{code}.IS", ltf_source_ticker=None,
        extras={"universe_version": "2026-09-16.v1", "code": code, "name": name,
                "sector": sector, "context_index": "XU030.IS"},
    )


def load_bist_universe(path: Optional[str] = None) -> Dict[str, Any]:
    """Load configs/bist30_universe.yaml (frozen, timestamped membership)."""
    import yaml
    if path is None:
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(here, "configs", "bist30_universe.yaml")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def bist_stock_specs(universe: Optional[Dict[str, Any]] = None) -> Dict[str, AssetSpec]:
    universe = universe or load_bist_universe()
    out: Dict[str, AssetSpec] = {}
    for m in universe.get("members", []):
        spec = make_bist_stock_spec(m["code"], m.get("name") or "", m.get("sector") or "")
        out[spec.key] = spec
    return out


# XU030 index: NOT tradable, context filter for long signals only.
BIST30_CONTEXT_SPEC_KEY = "BIST30"

# Optional macro / cross-asset context series (never traded, features only).
CONTEXT_SERIES: Dict[str, Dict[str, str]] = {
    "DXY": {"venue": "yahoo_index", "ticker": "DX-Y.NYB", "timeframe": "1d"},
    "US10Y": {"venue": "yahoo_index", "ticker": "^TNX", "timeframe": "1d"},
    "USDTRY": {"venue": "yahoo_fx", "ticker": "USDTRY=X", "timeframe": "1d"},
    "SPX": {"venue": "yahoo_index", "ticker": "^GSPC", "timeframe": "1d"},
    "VIX": {"venue": "yahoo_index", "ticker": "^VIX", "timeframe": "1d"},
}


# --------------------------------------------------------------------------
# Study design (splits / validation)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SplitConfig:
    """Fixed, pre-registered split of the 4H study window.

    ``test_frac`` is the FINAL hold-out. It is touched exactly once, after
    every model/parameter decision is frozen. ``purge_bars`` removes bars
    around each split boundary (label horizon leakage) and ``embargo_bars``
    adds a further dead zone after every validation fold.
    """

    train_frac: float = 0.60
    val_frac: float = 0.20
    test_frac: float = 0.20
    purge_bars: int = 24          # >= max label horizon in 4H bars
    embargo_bars: int = 12
    n_wf_folds: int = 6           # walk-forward folds over train+val
    wf_train_bars: int = 2500
    wf_step_bars: int = 500
    label_horizons_bars: tuple = (3, 6, 12, 18, 30)   # 12h, 24h, 48h, 72h, 5d
    max_label_horizon_bars: int = 30
    mc_simulations: int = 1000
    bootstrap_resamples: int = 1000


DEFAULT_SPLIT = SplitConfig()


# --------------------------------------------------------------------------
# Regime engine
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RegimeConfig:
    """Rejim motoru — SADELİK KURALI gereği yalnızca İKİ ölçüm.

    İPTAL EDİLENLER (kullanıcı kararı, bağlayıcı): ADX, Hurst exponent, HMM,
    Choppiness Index, Bollinger Band width, Ichimoku, Supertrend, Keltner.
    Bunlar config'te tutulmaz; çünkü kullanılmayan parametre ayarlanabilir
    parametredir ve ayarlanabilir parametre overfitting yüzeyidir.

    Ölçüm 1 — TREND (tek görsel öğe: EMA200):
        trend_up   : close > EMA200  VE  EMA200 yükseliyor
        trend_down : close < EMA200  VE  EMA200 düşüyor
        range      : diğer tüm durumlar (yön VE eğim uyuşmuyor)
      Eğim, ölçekten bağımsız olsun diye ATR'ye normalize edilir:
        slope_norm = (EMA200[t] - EMA200[t-slope_window]) / (ATR% x close)

    Ölçüm 2 — VOLATİLİTE (ATR yüzdelik dilimi):
        vol_high   : ATR yüzdeliği >= high_pct
        vol_low    : ATR yüzdeliği <= low_pct
        vol_normal : aradaki
      Yüzdelik, GERİYE DÖNÜK pencere içinde hesaplanır (look-ahead yok).

    Rejim etiketi = f(trend, vol) → 3 x 2 = 6 durum.
    """

    ema_trend_period: int = 200          # TEK trend filtresi
    slope_window: int = 20               # EMA200 eğim penceresi (bar)
    slope_min_atr_units: float = 0.05    # eğim en az bu kadar ATR birimi olmalı
    atr_period: int = 14
    atr_percentile_window: int = 500     # ~83 gün (4H), geriye dönük
    vol_high_pct: float = 0.75
    vol_low_pct: float = 0.25
    # sinyal kapıları
    long_allowed_in: tuple = ("trend_up",)
    short_allowed_in: tuple = ("trend_down",)
    max_atr_percentile: float = 0.95     # aşırı volatilitede yeni sinyal YOK
    min_bars_for_regime: int = 500       # ısınma: bu kadar bar yoksa rejim NaN
    fail_closed: bool = True             # rejim bilinmiyorsa sinyal YOK





DEFAULT_REGIME = RegimeConfig()


@dataclass(frozen=True)
class LevelsConfig:
    """AŞAMA 3 — yapısal seviyeler ve yapısal stop.

    SADELİK KURALI: yeni indikatör YOK. Yalnızca üç kavram var:
    k-bar fraktal swing, Donchian(N) ve ATR buffer'lı yapısal stop.
    Yasaklı liste (Ichimoku/Supertrend/Keltner/order block/volume profile/
    anchored VWAP/fractal-dışı seviye sistemleri) GEÇERLİLİĞİNİ KORUR.

    Look-ahead sözleşmesi (hepsi test ile kilitli):
    * Bir swing, ekstremumdan **k bar sonra** onaylanır. Bar t'de verilen karar
      yalnızca ``p + k < t`` olan swing'leri görebilir (yani t anında KAPANMIŞ
      barlarla onaylanmış olanları).
    * Donchian(N) **son N KAPANMIŞ barı** kullanır; mevcut bar pencereye GİRMEZ.
    * ``return_valid == False`` veya ``non_tradable == True`` barlar ne swing
      ne Donchian anchor'ı olabilir (FLAG-ONLY felsefesi). Yeterli geçerli bar
      yoksa seviye NaN'dır ve stop GEÇERSİZDİR (fail-closed).
    """

    swing_k: int = 3                    # k-bar fraktal (k bar önce/sonra)
    swing_lookback: int = 120           # 'son onaylı swing' bu pencerede aranır
    donchian_period: int = 20           # son 20 KAPANMIŞ bar
    stop_buffer_atr: float = 1.0        # VARSAYILAN; aday küme Aşama 9'da
    stop_buffer_candidates: tuple = (0.5, 1.0, 1.5)   # Aşama 9 — ŞİMDİ SEÇİM YOK
    min_valid_frac_in_window: float = 0.90   # pencerede geçerli bar oranı alt sınırı
    allow_short: bool = True            # core varlıklar için; hisselerde politika False
    break_even_after_r: float = 0.0     # 0 = kapalı (Aşama 7'de ele alınacak)

    def __post_init__(self) -> None:
        if self.swing_k < 1:
            raise ValueError("swing_k >= 1 olmali")
        if self.donchian_period < 2:
            raise ValueError("donchian_period >= 2 olmali")
        if self.stop_buffer_atr not in self.stop_buffer_candidates:
            raise ValueError(
                f"stop_buffer_atr ({self.stop_buffer_atr}) aday kumesinde degil; "
                f"buffer SECIMI yalnizca Asama 9'da yapilir, simdi {self.stop_buffer_candidates} "
                f"icinden VARSAYILAN kullanilir")


DEFAULT_LEVELS = LevelsConfig()


@dataclass(frozen=True)
class MomentumConfig:
    """AŞAMA 4 — TEK momentum kuralı: ATR-normalize ROC.

    SADELİK KURALI: RSI, MACD, Stochastic, StochRSI, MFI, OBV, Williams %R,
    CCI ve benzeri HİÇBİRİ yok. Yalnızca aşağıdaki tek ölçüm:

        mom(t) = (close[t] / close[t-n] - 1) / (ATR14[t] / close[t-n])

    Yani "son n barda fiyat, ATR cinsinden kaç birim yer değiştirdi".
    Payda ``ATR/close.shift(n)`` olduğu için birimsizdir ve varlıklar arası
    karşılaştırılabilir.

    Karar anı sözleşmesi (kabul kriteri 3):
    Bar ``t``'de karar anı ``t``'nin AÇILIŞIDIR. ``close[t-1]`` o ana kadar
    KAPANMIŞ son bardır, ``close[t-n]`` de öyle. Yani formüldeki her terim
    karar anından önce bilinir -> look-ahead YOKTUR (silme testiyle kilitli).

    Guard (kabul kriteri 4) — ``momentum_valid=False`` ve dolayısıyla
    ``momentum_ok=False`` olur:
      * ATR NaN veya <= 0
      * close[t-n] NaN veya <= 0
      * ``non_tradable == True``
      * ``return_valid == False``
      * ilk n barda (ısınma)
    Fail-closed: momentum BİLİNMİYORSA onay YOKTUR.
    """

    roc_bars: int = 10                      # n (varsayılan)
    threshold_atr: float = 1.0              # m (varsayılan)
    roc_candidates: tuple = (5, 10, 20)     # Aşama 9 — ŞİMDİ SEÇİM YOK
    threshold_candidates: tuple = (0.5, 1.0, 1.5)
    atr_period: int = 14
    allow_short: bool = True                # core varlıklar; hisselerde politika False
    calibration_band: tuple = (0.10, 0.60)  # geçiş oranı bandı; DIŞINDA ise bayrak
    tune_out_of_band: bool = False          # ASLA otomatik tune ETME, sadece bayrak

    def __post_init__(self) -> None:
        if self.roc_bars not in self.roc_candidates:
            raise ValueError(
                f"roc_bars ({self.roc_bars}) aday kümesinde değil: {self.roc_candidates}. "
                f"Parametre seçimi yalnızca Aşama {PARAM_TUNING_STAGE}'da, yalnızca "
                f"{PARAM_TUNING_UNIVERSE} üzerinde yapılır.")
        if self.threshold_atr not in self.threshold_candidates:
            raise ValueError(
                f"threshold_atr ({self.threshold_atr}) aday kümesinde değil: "
                f"{self.threshold_candidates}. Seçim Aşama {PARAM_TUNING_STAGE}'da.")
        if self.tune_out_of_band:
            raise ValueError(
                "tune_out_of_band=True YASAK: bant dışı geçiş oranı TUNE EDİLMEZ, "
                "yalnızca BAYRAKLANIR ve rapora not düşülür (kabul kriteri 6).")


DEFAULT_MOMENTUM = MomentumConfig()


@dataclass(frozen=True)
class ExitConfig:
    """AŞAMA 6 — gerçek çıkış motoru.

    Üç çıkış yolu, öncelik sırasıyla (aynı barda çakışırsa PESİMİST olan kazanır):
      1. **Dondurulmuş yapısal stop** — girişte planlanır, ASLA gevşetilmez
         (Aşama 3 `FrozenStop` sözleşmesi).
      2. **Basit TP = take_profit_r × R** — R = |giriş − stop|.
      3. **Time-stop = time_stop_bars** — giriş barından itibaren sayılır.

    Aday kümeleri `{time_stop: 60, 90, 120}` ve `{TP: 2R, 3R, 4R}` **YALNIZCA
    Aşama 9'da**, yalnızca core varlıklar üzerinde test edilir. Küme dışı değer
    `ValueError` verir; `tune_now=True` de `ValueError` verir.

    Doldurma varsayımları (MUHAFAZAKÂR, kabul kriteri 2):
      * giriş  : ``open[t+1]``
      * stop   : bar ``open < stop`` ise **open**'dan (gap aleyhimize çalışır),
                 değilse **stop** fiyatından
      * TP     : bar ``open > tp`` ise **open**'dan (gap lehimizeyse alınır),
                 değilse **tp** fiyatından
      * aynı barda stop VE TP dokunmuşsa → **STOP** öncelikli (pesimist)
      * time-stop → o barın **kapanışından**
      * slippage + komisyon + yarım spread **iki tarafa da** işlenir
    """

    time_stop_bars: int = 90
    take_profit_r: float = 3.0
    time_stop_candidates: tuple = (60, 90, 120)
    take_profit_candidates: tuple = (2.0, 3.0, 4.0)
    tune_now: bool = False
    same_bar_priority: str = "stop"        # "stop" = pesimist
    require_valid_stop: bool = True        # H35 kilidi: stopsuz pozisyon AÇILMAZ
    apply_costs_both_sides: bool = True
    min_trades_for_significance: int = 100
    bootstrap_resamples: int = 1000
    random_seed: int = 42
    # ---- AŞAMA 7: çıkış mimarisi KARŞILAŞTIRMASI (2026-09-17 kullanıcı şartnamesi) ----
    # SEÇİM YOKTUR: P0 varsayılan kalır; profil/anchor seçimi YALNIZ Aşama 9'da,
    # YALNIZ OOS (ön-kayıtlı split'ler) ile yapılır. Aşama 7 grid'i in-sample'dır.
    #   P0 baseline      : TS90 + TP3R (Aşama 6 davranışı, birebir korunur)
    #   P1 partial+runner: 1R'de %50 kapat + stop breakeven + runner chandelier ATR×3 (TS YOK)
    #   P2 trailing      : girişten chandelier ATR×3 (dondurulmuş stop'un üstüne çıkar,
    #                      gevşemez), sabit TP YOK, TS90 emniyet
    #   P3 breakeven     : 1R sonrası stop→breakeven, TP3R + TS90 (partial YOK)
    profile: str = "P0"
    exit_profile_candidates: tuple = ("P0", "P1", "P2", "P3")
    partial_frac: float = 0.5              # şartname sabiti — KİLİTLİ
    breakeven_trigger_r: float = 1.0       # şartname sabiti — KİLİTLİ
    chandelier_atr_mult: float = 3.0       # şartname sabiti — KİLİTLİ

    def __post_init__(self) -> None:
        if self.time_stop_bars not in self.time_stop_candidates:
            raise ValueError(
                f"time_stop_bars ({self.time_stop_bars}) aday kümesinde değil: "
                f"{self.time_stop_candidates}. Seçim yalnızca Aşama "
                f"{PARAM_TUNING_STAGE}'da, yalnızca {PARAM_TUNING_UNIVERSE} üzerinde.")
        if self.take_profit_r not in self.take_profit_candidates:
            raise ValueError(
                f"take_profit_r ({self.take_profit_r}) aday kümesinde değil: "
                f"{self.take_profit_candidates}. Seçim Aşama {PARAM_TUNING_STAGE}'da.")
        if self.tune_now:
            raise ValueError("tune_now=True YASAK: Aşama 6'da parametre TUNE EDİLMEZ.")
        if self.same_bar_priority != "stop":
            raise ValueError(
                f"same_bar_priority '{self.same_bar_priority}' desteklenmiyor; "
                f"kabul kriteri 2 gereği PESİMİST olmalı ('stop').")
        # ---- Aşama 7 kilitleri ----
        if self.profile not in self.exit_profile_candidates:
            raise ValueError(
                f"profile '{self.profile}' aday kümesinde değil: "
                f"{self.exit_profile_candidates}. Profil SEÇİMİ yalnızca Aşama "
                f"{PARAM_TUNING_STAGE}'da, yalnızca OOS yapılır.")
        if self.partial_frac != 0.5:
            raise ValueError("partial_frac Aşama 7 şartname sabitidir (0.5); değiştirilemez/tune edilemez.")
        if self.breakeven_trigger_r != 1.0:
            raise ValueError("breakeven_trigger_r Aşama 7 şartname sabitidir (1.0); değiştirilemez/tune edilemez.")
        if self.chandelier_atr_mult != 3.0:
            raise ValueError("chandelier_atr_mult Aşama 7 şartname sabitidir (3.0); değiştirilemez/tune edilemez.")


DEFAULT_EXIT = ExitConfig()

DEFAULT_MOMENTUM = MomentumConfig()



# KARAR (2026-09-16, PROGRESS'e işlendi): BIST30 hisselerinde warmup nedeniyle
# TRAIN etiketli bar sayısı azdır. Bu yüzden HİÇBİR aşamada hisse başına
# in-sample parametre seçimi YAPILMAZ. Parametre seçimi Aşama 9'da, küçük bir
# aday kümesiyle ve yalnızca CORE varlıklar üzerinde yapılır; hisseler yalnızca
# OOS raporlanır. Aşağıdaki bayrak bu kuralı kod düzeyinde taşır.
PER_ASSET_IN_SAMPLE_TUNING_ALLOWED = False
PARAM_TUNING_UNIVERSE = ("BTC", "GOLD", "SILVER")
PARAM_TUNING_STAGE = 9

# BIST30 hisseleri LONG-ONLY (KARAR 4) -> short stop üretilmez.
STOCK_ALLOW_SHORT = False


# --------------------------------------------------------------------------
# Full experiment config
# --------------------------------------------------------------------------

@dataclass
class ExperimentConfig:
    profile: str = DEFAULT_PROFILE
    assets: List[str] = field(default_factory=lambda: ["BTC", "GOLD", "SILVER", "BIST30"])
    split: SplitConfig = DEFAULT_SPLIT
    regime: RegimeConfig = DEFAULT_REGIME
    levels: LevelsConfig = DEFAULT_LEVELS
    momentum: MomentumConfig = DEFAULT_MOMENTUM
    exit: ExitConfig = DEFAULT_EXIT
    starting_equity: float = 100_000.0
    equity_currency: str = "USD"
    fx_fallback: Dict[str, float] = field(default_factory=lambda: {"TRY": 0.03, "USDT": 1.0})
    random_seed: int = 42
    min_bars_for_study: int = MIN_BARS_FOR_STUDY
    min_bars_for_model: int = MIN_BARS_FOR_MODEL

    @property
    def risk(self) -> RiskProfile:
        return RISK_PROFILES[self.profile]

    def asset(self, key: str) -> AssetSpec:
        return DEFAULT_ASSETS[key]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "assets": self.assets,
            "starting_equity": self.starting_equity,
            "equity_currency": self.equity_currency,
            "fx_fallback": self.fx_fallback,
            "random_seed": self.random_seed,
            "risk": asdict(self.risk),
            "split": asdict(self.split),
            "regime": asdict(self.regime),
            "assets_detail": {k: asdict(v) for k, v in DEFAULT_ASSETS.items()},
        }


def load_config(path: Optional[str] = None) -> ExperimentConfig:
    """Load a YAML config if present, otherwise return defaults.

    Unknown keys raise: silent typos in a risk config are unacceptable.
    """
    cfg = ExperimentConfig()
    if path is None:
        return cfg
    import yaml  # local import so the module works without pyyaml
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    known = {f for f in cfg.__dataclass_fields__}  # type: ignore[attr-defined]
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"Unknown config keys: {sorted(unknown)}. Known: {sorted(known)}")
    for key, value in raw.items():
        if key in ("split", "regime"):
            continue
        setattr(cfg, key, value)
    if cfg.profile not in RISK_PROFILES:
        raise ValueError(f"Unknown risk profile '{cfg.profile}'")
    unknown_assets = [a for a in cfg.assets if a not in DEFAULT_ASSETS]
    if unknown_assets:
        raise ValueError(f"Unknown assets: {unknown_assets}")
    return cfg


__all__ = [
    "TIMEFRAME", "HTF", "LTF", "UTC", "CANONICAL_COLUMNS", "OPTIONAL_COLUMNS",
    "BIST_STOCK_ROUND_TRIP_BPS", "BIST_STOCK_CAVEATS", "make_bist_stock_spec",
    "LevelsConfig", "DEFAULT_LEVELS", "MomentumConfig", "DEFAULT_MOMENTUM",
    "ExitConfig", "DEFAULT_EXIT",
    "PER_ASSET_IN_SAMPLE_TUNING_ALLOWED",
    "PARAM_TUNING_UNIVERSE", "PARAM_TUNING_STAGE", "STOCK_ALLOW_SHORT",
    "load_bist_universe", "bist_stock_specs", "BIST30_CONTEXT_SPEC_KEY",
    "CostModel", "RiskProfile", "RISK_PROFILES", "DEFAULT_PROFILE",
    "AssetSpec", "DEFAULT_ASSETS", "CONTEXT_SERIES", "SplitConfig",
    "DEFAULT_SPLIT", "RegimeConfig", "DEFAULT_REGIME", "ExperimentConfig",
    "load_config", "MIN_BARS_FOR_STUDY", "MIN_BARS_FOR_MODEL",
]
