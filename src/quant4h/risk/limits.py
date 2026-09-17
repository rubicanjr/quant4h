"""AŞAMA 8 — Risk limitleri (tavanlar). Bağlayıcı kaynak: kullanıcı direktifi 2026-09-17.

Tavanlar (balanced varsayılanları):
  * Maks eşzamanlı pozisyon: TOPLAM 6 · BTC 2 · GOLD 1 · SILVER 1 · BIST30 sepet 3.
    (Not: Stage 0 `RiskProfile.max_open_positions=3` değeri Aşama 8 şartnamesiyle
    SUPERSEDE edilmiştir — kullanıcı direktifi 2026-09-17 toplam 6'yı bağlayıcı
    kılar; bu not PROGRESS'e de işlenmiştir.)
  * Kıymetli maden TEK kova (ONAYLI KARAR 2026-09-16): GOLD+SILVER birleşik ısı
    <= 1 × risk_per_trade. Isı = giriş anındaki PLANLANAN risk oranı
    (|giriş−stop| × units / equity_at_entry); kaldıraç kıskacı riski yalnız KÜÇÜLTÜR.
  * BIST30: sepet TEK ısı birimi <= 3 × risk_per_trade · hisse başı <= 1 ×
    risk_per_trade · banka sektörü eşzamanlı <= 2 (banka listesi DONMUŞ
    üniversalden okunur: configs/bist30_universe.yaml, sector == "banka").
  * Günlük/haftalık kayıp limitleri: RiskProfile değerleri BAĞLAYICI
    (balanced: %2 gün / %5 hafta). Baz: gerçekleşen (realized) P&L vs dönem başı
    equity; aşımında YENİ GİRİŞLER kapalı (fail-closed), ÇIKIŞLARA DOKUNULMAZ.
  * Ardışık kayıp freni: aynı varlıkta 4 ardışık kayıp -> o varlıkta 20 bar
    yeni giriş YOK (varlığın KENDİ bar ızgarasında; long+short ortak sayılır).

Tavanlar YALNIZ GİRİŞTE uygulanır; hiçbir tavan pozisyon KAPATMAZ.
`unlimited=True` yalnız regresyon testleri içindir (Aşama 6/7 motor eşitliği).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_UNIVERSE_YAML = os.path.join(_ROOT, "configs", "bist30_universe.yaml")

_BANK_CACHE: Optional[Tuple[str, ...]] = None


def bank_codes(universe_yaml: str = _UNIVERSE_YAML) -> Tuple[str, ...]:
    """Donmuş üniversalden banka sektörü kodları (deterministik, cache'li)."""
    global _BANK_CACHE
    if _BANK_CACHE is None:
        import yaml
        with open(universe_yaml, "r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        members = doc.get("members") or []
        _BANK_CACHE = tuple(sorted(m["code"] for m in members
                                   if str(m.get("sector", "")).lower() == "banka"))
    return _BANK_CACHE


@dataclass(frozen=True)
class RiskLimits:
    # ---- eşzamanlı pozisyon tavanları ----
    max_concurrent_total: int = 6
    max_btc: int = 2
    max_gold: int = 1
    max_silver: int = 1
    max_basket_concurrent: int = 3       # BIST30 sepeti TOPLAM eşzamanlı
    max_per_stock: int = 1                 # hisse başına (motor zaten tek pozisyon)
    max_bank_concurrent: int = 2           # banka sektörü eşzamanlı
    # ---- ısı (planned risk fraction) tavanları ----
    metals_heat_max_rpt_mult: float = 1.0  # GOLD+SILVER birleşik <= 1×risk_per_trade
    basket_heat_max_rpt_mult: float = 3.0  # sepet birleşik <= 3×risk_per_trade
    per_stock_heat_max_rpt_mult: float = 1.0
    # ---- kayıp limitleri (profilden enjekte edilir; balanced varsayılanları) ----
    max_daily_loss: float = 0.02
    max_weekly_loss: float = 0.05
    # ---- ardışık kayıp freni ----
    loss_streak_count: int = 4
    loss_streak_block_bars: int = 20
    # ---- regresyon modu ----
    unlimited: bool = False              # True -> TÜM tavanlar kapalı (yalnız test)

    def __post_init__(self) -> None:
        for name in ("max_concurrent_total", "max_btc", "max_gold", "max_silver",
                     "max_basket_concurrent", "max_per_stock", "max_bank_concurrent",
                     "loss_streak_count", "loss_streak_block_bars"):
            if int(getattr(self, name)) < 1:
                raise ValueError(f"{name} >= 1 olmalı (fail-closed); got {getattr(self, name)}")
        for name in ("metals_heat_max_rpt_mult", "basket_heat_max_rpt_mult",
                     "per_stock_heat_max_rpt_mult"):
            if float(getattr(self, name)) <= 0:
                raise ValueError(f"{name} > 0 olmalı; got {getattr(self, name)}")
        if not (0 < self.max_daily_loss < 1) or not (0 < self.max_weekly_loss < 1):
            raise ValueError("max_daily_loss/max_weekly_loss (0,1) aralığında oran olmalı")
        if self.max_weekly_loss < self.max_daily_loss:
            raise ValueError("haftalık limit günlük limitten küçük olamaz")

    def per_asset_cap(self, key: str) -> int:
        return {"BTC": self.max_btc, "GOLD": self.max_gold,
                "SILVER": self.max_silver}.get(key, self.max_per_stock)

    @classmethod
    def from_profile(cls, profile, **overrides) -> "RiskLimits":
        """RiskProfile'dan günlük/haftalık limitleri enjekte eder (bağlayıcı)."""
        kw = {"max_daily_loss": float(profile.max_daily_loss),
              "max_weekly_loss": float(profile.max_weekly_loss)}
        kw.update(overrides)
        return cls(**kw)

    @classmethod
    def no_limits(cls) -> "RiskLimits":
        return cls(unlimited=True)


BUCKET_METALS = "precious_metals"
BUCKET_BASKET = "bist30_basket"
BUCKET_CORE = "core"

# reddedilen sinyal sayaç anahtarları (rapor: tavan tipi başına)
REJECTION_KEYS = ("no_valid_stop", "stop_geometry", "not_tradable", "invalid_price",
                  "loss_streak_brake", "daily_loss_limit", "weekly_loss_limit",
                  "total_concurrent", "per_asset_concurrent", "basket_concurrent",
                  "bank_sector", "metals_bucket_heat", "basket_heat", "per_stock_heat")


def bucket_of(key: str) -> str:
    if key in ("GOLD", "SILVER"):
        return BUCKET_METALS
    if key == "BTC":
        return BUCKET_CORE
    return BUCKET_BASKET


__all__ = ["RiskLimits", "bank_codes", "bucket_of", "REJECTION_KEYS",
           "BUCKET_METALS", "BUCKET_BASKET", "BUCKET_CORE"]
