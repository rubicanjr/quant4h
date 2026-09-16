"""AŞAMA 3 — Structural levels and the structural stop.

SADELİK KURALI: bu modülde YENİ İNDİKATÖR YOKTUR. Üç kavram var:

1. **k-bar fraktal swing** (varsayılan k=3)
2. **Donchian(N)** (varsayılan N=20, son N KAPANMIŞ bar)
3. **ATR buffer'lı yapısal stop** (varsayılan buffer 1.0)

Grafikte maksimum 3 öğe kuralı korunur: mum + EMA200 (Aşama 2) + yapısal
stop/hedef çizgileri (bu modül). Kullanıcının yasakladığı indikatör yığını
burada YOKTUR; yasaklı liste `configs/user_decisions.yaml → simplicity_rules`
içinde tutulur ve `tests/test_levels.py` bu modülü ona karşı tarar.

Look-ahead sözleşmesi (hepsi `tests/test_levels.py` ile kilitli)
--------------------------------------------------------------
Bir bar ``t`` için karar anı ``t``'nin AÇILIŞIDIR; yani yalnızca ``t-1`` ve
öncesi barlar KAPANMIŞTIR ve kullanılabilir.

* **Swing onayı:** p konumlu bir swing high, ``high[p]`` hem önceki k hem
  sonraki k barın zirvesi ise vardır. Bu ancak ``p+k`` barı KAPANDIĞINDA
  bilinir. ``t`` anında görülebilen swing'ler ``p + k < t`` koşulunu sağlayan
 lardır. Onaysız swing seviyeye GİRMEZ (test: ``test_unconfirmed_swing_is_invisible``).
* **Donchian:** ``rolling(N).max().shift(1)`` — mevcut bar pencereye girmez.
* **Anchor kısıtı:** ``return_valid == False`` veya ``non_tradable == True``
  barlar ne swing ne Donchian anchor'ı olabilir. Bir bar bayraklıysa swing
  adayı hiç üretilmez; Donchian penceresindeyse pencereden ÇIKARILIR ve
  pencerede yeterli geçerli bar kalmazsa seviye NaN olur (fail-closed).
* Pencerede geçerli bar oranı ``min_valid_frac_in_window`` altına düşerse
  Donchian NaN'dır. "Eksik veriyi görmezden gel" değil, "seviye BİLİNMİYOR".

Stop dondurma (kabul kriteri 5)
-------------------------------
``plan_stop()`` saf bir fonksiyondur: aynı girdi → aynı çıktı, yan etki yok.
``FrozenStop`` ise değiştirilemez (frozen dataclass) ve ``widen()``,
``move_against()``, ``relax()`` çağrıları **StopImmutabilityError** fırlatır.
Backtest motoru bir stop'u gevşetemez veya kaydıramaz; yalnızca pozisyon
lehine ilerleyen bir trailing kuralı (Aşama 7) ``tighten()`` çağırabilir ve o
da orijinal stopu koruyarak yeni bir nesne DÖNDÜRÜR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import DEFAULT_LEVELS, LevelsConfig

LEVEL_COLUMNS = (
    "anchor_ok",                 # bu bar swing/Donchian anchor'ı OLABİLİR mi
    "swing_high_candidate",      # k-bar fraktal zirve (onay bekliyor)
    "swing_low_candidate",
    "swing_high_confirmed",      # p+k < t ile ONAYLANMIŞ zirve
    "swing_low_confirmed",
    "last_swing_high",           # karar anında bilinen SON onaylı zirve
    "last_swing_low",
    "last_swing_high_pos",       # kaç bar önce onaylandı (bayatlık ölçüsü)
    "last_swing_low_pos",
    "highest_swing_high",        # swing_lookback içindeki EN YÜKSEK onaylı zirve
    "lowest_swing_low",
    "donchian_high",             # son N KAPANMIŞ barın zirvesi
    "donchian_low",
    "donchian_valid_frac",       # penceredeki geçerli bar oranı
    "stop_long", "stop_short",
    "stop_long_dist", "stop_short_dist",
    "stop_long_atr_mult", "stop_short_atr_mult",
    "stop_long_pct_price", "stop_short_pct_price",
    "stop_valid_long", "stop_valid_short",
    "stop_anchor_long", "stop_anchor_short",
)


class StopImmutabilityError(RuntimeError):
    """A frozen stop may never be widened, moved against the position or relaxed."""


# --------------------------------------------------------------------------
# anchor eligibility
# --------------------------------------------------------------------------

def anchor_eligible(df: pd.DataFrame) -> pd.Series:
    """True where the bar may act as a swing / Donchian anchor.

    FLAG-ONLY felsefesinin devamı: bozuk veri SİLİNMEZ ama seviye üretimine
    de KATILMAZ. Bir bar şu durumlarda anchor olamaz:
      * ``return_valid == False`` (veri boşluğunu veya ex-date'i atlayan getiri)
      * ``non_tradable == True``  (kesinti / ince açılış barı / oluşuyor / kurumsal aksiyon)
      * OHLC'si NaN veya pozitif değil
    """
    n = len(df)
    ok = pd.Series(True, index=df.index)
    if "return_valid" in df.columns:
        ok &= pd.to_numeric(df["return_valid"], errors="coerce").fillna(False).astype(bool)
    if "non_tradable" in df.columns:
        nt = pd.to_numeric(df["non_tradable"], errors="coerce").fillna(True).astype(bool)
        ok &= ~nt
    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            v = pd.to_numeric(df[col], errors="coerce")
            ok &= v.notna() & (v > 0)
    if "halt_or_limit_flag" in df.columns:
        # Marja yapışmış bar GERÇEK bir seviye değildir (fiyat keşfi durmuştur).
        # Silinmez ama anchor olarak da kullanılmaz.
        ok &= ~pd.to_numeric(df["halt_or_limit_flag"], errors="coerce").fillna(False).astype(bool)
    return ok.reindex(df.index).fillna(False).astype(bool) if n else ok


# --------------------------------------------------------------------------
# 1. k-bar fractal swings
# --------------------------------------------------------------------------

def _fractal(series: pd.Series, k: int, kind: str, eligible: pd.Series) -> pd.Series:
    """k-bar fraktal. ``kind='high'`` için yerel maksimum, ``'low'`` için minimum.

    Adaylık yalnızca ``eligible`` barlar için değerlendirilir; karşılaştırma da
    yalnızca ``eligible`` komşularla yapılır. Bir komşu bayraklıysa fraktal
    **onaylanmaz** (eksik veriyle 'zirve' ilan etmek yanıltıcı olur).
    """
    s = pd.to_numeric(series, errors="coerce")
    ok = eligible.to_numpy(dtype=bool)
    v = s.to_numpy(dtype="float64")
    n = len(v)
    out = np.zeros(n, dtype=bool)
    for p in range(k, n - k):
        if not ok[p] or not np.isfinite(v[p]):
            continue
        left = np.arange(p - k, p)
        right = np.arange(p + 1, p + k + 1)
        idx = np.concatenate([left, right])
        if not ok[idx].all():
            continue                      # bayraklı komşu -> fraktal onaylanmaz
        neigh = v[idx]
        if not np.isfinite(neigh).all():
            continue
        if kind == "high":
            out[p] = bool(v[p] > neigh.max())
        else:
            out[p] = bool(v[p] < neigh.min())
    return pd.Series(out, index=s.index)


def _confirm(cand: pd.Series, k: int) -> pd.Series:
    """Onay gecikmesi: p konumlu aday ancak ``p + k`` barı KAPANDIktan sonra
    bilinir. Bar t'nin karar anında görülebilen en son onay ``t-1``'de kapanan
    bardır, yani ``p + k <= t - 1``  ->  ``confirmed = cand.shift(k + 1)``.
    """
    return cand.shift(k + 1).fillna(False).astype(bool)


def add_swings(df: pd.DataFrame, cfg: LevelsConfig = DEFAULT_LEVELS,
               eligible: Optional[pd.Series] = None) -> pd.DataFrame:
    out = df.copy()
    k = cfg.swing_k
    elig = eligible if eligible is not None else anchor_eligible(out)
    out["anchor_ok"] = elig.to_numpy()

    hi_c = _fractal(out["high"], k, "high", elig)
    lo_c = _fractal(out["low"], k, "low", elig)
    out["swing_high_candidate"] = hi_c.to_numpy()
    out["swing_low_candidate"] = lo_c.to_numpy()
    hi = _confirm(hi_c, k)
    lo = _confirm(lo_c, k)
    out["swing_high_confirmed"] = hi.to_numpy()
    out["swing_low_confirmed"] = lo.to_numpy()

    # Karar anında bilinen SON onaylı swing (ffill) + kaç bar önce onaylandı
    pos = pd.Series(np.arange(len(out), dtype="float64"), index=out.index)
    hi_pos = pos.where(hi)
    lo_pos = pos.where(lo)
    hi_val = pd.to_numeric(out["high"], errors="coerce").shift(k + 1).where(hi)
    lo_val = pd.to_numeric(out["low"], errors="coerce").shift(k + 1).where(lo)

    out["last_swing_high"] = hi_val.ffill().to_numpy()
    out["last_swing_low"] = lo_val.ffill().to_numpy()
    out["last_swing_high_pos"] = (pos - hi_pos.ffill()).to_numpy()
    out["last_swing_low_pos"] = (pos - lo_pos.ffill()).to_numpy()

    lb = max(int(cfg.swing_lookback), k + 2)
    out["highest_swing_high"] = hi_val.rolling(lb, min_periods=1).max().to_numpy()
    out["lowest_swing_low"] = lo_val.rolling(lb, min_periods=1).min().to_numpy()
    return out


# --------------------------------------------------------------------------
# 2. Donchian on CLOSED, eligible bars only
# --------------------------------------------------------------------------

def add_donchian(df: pd.DataFrame, cfg: LevelsConfig = DEFAULT_LEVELS,
                 eligible: Optional[pd.Series] = None) -> pd.DataFrame:
    out = df.copy()
    if "anchor_ok" not in out.columns:
        out["anchor_ok"] = anchor_eligible(out).to_numpy()
    elig = eligible if eligible is not None else out["anchor_ok"].astype(bool)
    n = int(cfg.donchian_period)
    e = elig.to_numpy(dtype=float)
    high = pd.to_numeric(out["high"], errors="coerce").where(elig).to_numpy(dtype="float64")
    low = pd.to_numeric(out["low"], errors="coerce").where(elig).to_numpy(dtype="float64")

    def _roll_masked(vals: np.ndarray, how: str) -> np.ndarray:
        s = pd.Series(vals)
        # min_periods=1 ZORUNLU: maskelenmiş (bayraklı) barlar NaN olduğu için
        # min_periods=n kullanılırsa pencerede TEK bir bayraklı bar varsa rolling
        # sonsuza dek NaN döndürür ve Donchian tamamen ölür. Bunun yerine
        # pencere HER ZAMAN hesaplanır ve güvenilirlik `donchian_valid_frac`
        # kapısıyla (min_valid_frac_in_window) sağlanır: yeterli geçerli bar
        # yoksa seviye NaN olur (fail-closed).
        r = s.rolling(n, min_periods=1)
        res = r.max() if how == "max" else r.min()
        # shift(1): mevcut bar pencereye GİRMEZ (yalnızca KAPANMIŞ barlar)
        return res.shift(1).to_numpy(dtype="float64")

    dh = _roll_masked(high, "max")
    dl = _roll_masked(low, "min")
    cnt = pd.Series(e).rolling(n, min_periods=1).sum().shift(1).to_numpy(dtype="float64")
    frac = np.where(np.isfinite(cnt), cnt / float(n), np.nan)

    enough = np.isfinite(frac) & (frac >= cfg.min_valid_frac_in_window)
    out["donchian_high"] = np.where(enough, dh, np.nan)
    out["donchian_low"] = np.where(enough, dl, np.nan)
    out["donchian_valid_frac"] = frac
    return out


# --------------------------------------------------------------------------
# 3. structural stop
# --------------------------------------------------------------------------

def add_structural_stop(df: pd.DataFrame, cfg: LevelsConfig = DEFAULT_LEVELS,
                        allow_short: Optional[bool] = None,
                        buffer_atr: Optional[float] = None) -> pd.DataFrame:
    """Attach the structural stop. The stop is defined BEFORE entry, from the
    most recent CONFIRMED swing plus an ATR buffer. It is never derived from
    the entry bar's own high/low (that would be look-ahead).
    """
    out = df.copy()
    if "last_swing_low" not in out.columns:
        out = add_swings(out, cfg)
    if "atr" not in out.columns:
        from .regime import wilder_atr
        out["atr"] = wilder_atr(pd.to_numeric(out["high"], errors="coerce"),
                                pd.to_numeric(out["low"], errors="coerce"),
                                pd.to_numeric(out["close"], errors="coerce"),
                                cfg_atr_period()).to_numpy()
    short_ok = cfg.allow_short if allow_short is None else bool(allow_short)
    buf = cfg.stop_buffer_atr if buffer_atr is None else float(buffer_atr)
    if buf not in cfg.stop_buffer_candidates:
        raise ValueError(f"buffer {buf} aday kümesinde değil; seçim Aşama 9'da")

    close = pd.to_numeric(out["close"], errors="coerce")
    atr = pd.to_numeric(out.get("atr"), errors="coerce")
    sl = pd.to_numeric(out["last_swing_low"], errors="coerce")
    sh = pd.to_numeric(out["last_swing_high"], errors="coerce")
    valid = sl.notna() & atr.notna() & (atr > 0) & close.notna() & (close > 0)

    stop_long = sl - buf * atr
    out["stop_long"] = stop_long.where(valid).to_numpy()
    out["stop_long_dist"] = (close - stop_long).where(valid).to_numpy()
    out["stop_long_atr_mult"] = ((close - stop_long) / atr).where(valid).to_numpy()
    out["stop_long_pct_price"] = ((close - stop_long) / close * 100.0).where(valid).to_numpy()
    out["stop_valid_long"] = valid.fillna(False).to_numpy()
    # stop fiyatın ÜSTÜNDE kalıyorsa yapısal olarak geçersizdir (long için)
    bad_long = valid & (stop_long >= close)
    out.loc[bad_long, "stop_valid_long"] = False
    out["stop_anchor_long"] = np.where(valid, "swing_low", "")

    if short_ok:
        vs = sh.notna() & atr.notna() & (atr > 0) & close.notna() & (close > 0)
        stop_short = sh + buf * atr
        out["stop_short"] = stop_short.where(vs).to_numpy()
        out["stop_short_dist"] = (stop_short - close).where(vs).to_numpy()
        out["stop_short_atr_mult"] = ((stop_short - close) / atr).where(vs).to_numpy()
        out["stop_short_pct_price"] = ((stop_short - close) / close * 100.0).where(vs).to_numpy()
        bad_short = vs & (stop_short <= close)
        out["stop_valid_short"] = vs.fillna(False).astype(bool)
        out.loc[bad_short, "stop_valid_short"] = False
        out["stop_anchor_short"] = np.where(vs, "swing_high", "")
    else:
        # KARAR 4: BIST30 hisseleri LONG-ONLY -> short stop HİÇ üretilmez
        for c in ("stop_short", "stop_short_dist", "stop_short_atr_mult",
                  "stop_short_pct_price"):
            out[c] = np.nan
        out["stop_valid_short"] = False
        out["stop_anchor_short"] = ""
    return out


def cfg_atr_period() -> int:
    from ..config import DEFAULT_REGIME
    return int(DEFAULT_REGIME.atr_period)


def add_levels(df: pd.DataFrame, cfg: LevelsConfig = DEFAULT_LEVELS,
               allow_short: Optional[bool] = None,
               buffer_atr: Optional[float] = None) -> pd.DataFrame:
    """Full Aşama 3 pass: swings -> Donchian -> structural stop."""
    out = add_swings(df, cfg)
    out = add_donchian(out, cfg)
    out = add_structural_stop(out, cfg, allow_short=allow_short, buffer_atr=buffer_atr)
    return out


# --------------------------------------------------------------------------
# frozen stop object (kabul kriteri 5)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FrozenStop:
    """A stop planned BEFORE entry. Immutable by construction.

    Backtest motoru bu nesneyi gevşetemaz/kaydıramaz. Yalnızca pozisyon
    LEHİNE ilerleyen bir kural (Aşama 7 trailing) ``tighten()`` ile YENİ bir
    nesne döndürebilir; orijinal ``initial_stop`` her zaman korunur ve
    ``tighten`` asla ``initial_stop``'un ötesine geçemez.
    """

    direction: str            # "long" | "short"
    initial_stop: float       # GİRİŞTEN ÖNCE dondurulan stop — ASLA değişmez
    entry_price: float
    planned_at_utc: str
    anchor: str
    atr_at_plan: float
    buffer_atr: float
    reason: str = "structural_swing_atr_buffer"
    current_stop: Optional[float] = None   # sıkılaştırılmış stop (yoksa initial)

    def __post_init__(self) -> None:
        if self.direction not in ("long", "short"):
            raise ValueError(f"direction must be long/short, got {self.direction!r}")
        if not np.isfinite(self.initial_stop) or self.initial_stop <= 0:
            raise ValueError("initial_stop must be a positive finite price")
        if self.direction == "long" and self.initial_stop >= self.entry_price:
            raise ValueError("long stop must be BELOW the entry price")
        if self.direction == "short" and self.initial_stop <= self.entry_price:
            raise ValueError("short stop must be ABOVE the entry price")
        cs = self.initial_stop if self.current_stop is None else float(self.current_stop)
        object.__setattr__(self, "current_stop", cs)
        if self.direction == "long" and cs < self.initial_stop:
            raise StopImmutabilityError("current_stop initial_stop'un ALTINA inemez")
        if self.direction == "short" and cs > self.initial_stop:
            raise StopImmutabilityError("current_stop initial_stop'un ÜSTÜNE çıkamaz")

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry_price - self.initial_stop)

    @property
    def stop_atr_multiple(self) -> float:
        return self.risk_per_unit / self.atr_at_plan if self.atr_at_plan else float("nan")

    def widen(self, new_stop: float) -> "FrozenStop":
        raise StopImmutabilityError(
            f"stop GEVŞETİLEMEZ ({self.direction} {self.initial_stop} -> {new_stop}). "
            f"Kabul kriteri 5: stop girişten önce dondurulur.")

    def move_against(self, new_stop: float) -> "FrozenStop":
        raise StopImmutabilityError(
            "stop pozisyon aleyhine KAYDIRILAMAZ (kabul kriteri 5)")

    def relax(self, *a: Any, **k: Any) -> "FrozenStop":
        raise StopImmutabilityError("stop gevşetilemez (kabul kriteri 5)")

    def tighten(self, new_stop: float, reason: str = "trailing") -> "FrozenStop":
        """Only toward the position. Returns a NEW object; never mutates."""
        if not np.isfinite(new_stop):
            raise ValueError("new_stop must be finite")
        if self.direction == "long":
            if new_stop <= self.initial_stop:
                raise StopImmutabilityError(
                    f"long stop yalnızca YUKARI sıkılaştırılabilir "
                    f"(initial {self.initial_stop}, istenen {new_stop})")
            if new_stop >= self.entry_price * 1e9:
                raise ValueError("new_stop unreasonable")
        else:
            if new_stop >= self.initial_stop:
                raise StopImmutabilityError(
                    f"short stop yalnızca AŞAĞI sıkılaştırılabilir "
                    f"(initial {self.initial_stop}, istenen {new_stop})")
        return FrozenStop(direction=self.direction, initial_stop=self.initial_stop,
                          entry_price=self.entry_price, planned_at_utc=self.planned_at_utc,
                          anchor=self.anchor, atr_at_plan=self.atr_at_plan,
                          buffer_atr=self.buffer_atr, reason=reason,
                          current_stop=float(new_stop))

    @property
    def active_stop(self) -> float:
        """The stop currently in force (initial unless tightened)."""
        return float(self.initial_stop if self.current_stop is None else self.current_stop)


def plan_stop(row: pd.Series, direction: str, cfg: LevelsConfig = DEFAULT_LEVELS,
              allow_short: bool = True) -> Optional[FrozenStop]:
    """Pure function: plan the frozen stop for a signal bar.

    ``row`` is one bar of an ``add_levels()`` frame. Returns ``None`` when the
    stop cannot be determined (fail-closed: no stop -> NO TRADE).
    """
    if direction == "long":
        valid = bool(row.get("stop_valid_long", False))
        stop = row.get("stop_long", np.nan)
        anchor = row.get("stop_anchor_long", "")
    elif direction == "short":
        if not allow_short:
            return None                 # LONG-ONLY politika: short planı YOK
        valid = bool(row.get("stop_valid_short", False))
        stop = row.get("stop_short", np.nan)
        anchor = row.get("stop_anchor_short", "")
    else:
        raise ValueError(f"direction must be long/short, got {direction!r}")
    if not valid or not np.isfinite(stop):
        return None
    entry = float(row["close"])
    atr = float(row.get("atr", np.nan))
    if not np.isfinite(atr) or atr <= 0:
        return None
    if direction == "long" and stop >= entry:
        return None
    if direction == "short" and stop <= entry:
        return None
    return FrozenStop(direction=direction, initial_stop=float(stop), entry_price=entry,
                      planned_at_utc=str(row.get("timestamp_utc", "")), anchor=str(anchor),
                      atr_at_plan=atr, buffer_atr=float(cfg.stop_buffer_atr))


# --------------------------------------------------------------------------
# event counts for the report
# --------------------------------------------------------------------------

def count_events(df: pd.DataFrame, cfg: LevelsConfig = DEFAULT_LEVELS) -> Dict[str, Any]:
    """Breakout / level-touch / swing statistics used by levels_report.md."""
    n = len(df)
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    dh = pd.to_numeric(df.get("donchian_high"), errors="coerce")
    dl = pd.to_numeric(df.get("donchian_low"), errors="coerce")
    prev_close = close.shift(1)

    def _cnt(mask: pd.Series) -> int:
        return int(mask.fillna(False).sum())

    bo_up = _cnt((high > dh) & (prev_close <= dh.shift(1)) & dh.notna())
    bo_dn = _cnt((low < dl) & (prev_close >= dl.shift(1)) & dl.notna())
    touch_hi = _cnt((high >= dh) & dh.notna())
    touch_lo = _cnt((low <= dl) & dl.notna())
    sh = df.get("last_swing_high")
    sl = df.get("last_swing_low")
    touch_sh = _cnt((high >= pd.to_numeric(sh, errors="coerce")) & pd.to_numeric(sh, errors="coerce").notna())
    touch_sl = _cnt((low <= pd.to_numeric(sl, errors="coerce")) & pd.to_numeric(sl, errors="coerce").notna())
    brk_sh = _cnt((close > pd.to_numeric(sh, errors="coerce")) & pd.to_numeric(sh, errors="coerce").notna())
    brk_sl = _cnt((close < pd.to_numeric(sl, errors="coerce")) & pd.to_numeric(sl, errors="coerce").notna())

    dist = {}
    for side in ("long", "short"):
        col = f"stop_{side}_atr_mult"
        if col in df.columns:
            x = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(x):
                dist[side] = {"n": int(len(x)), "median_atr_mult": round(float(x.median()), 3),
                              "p25_atr_mult": round(float(x.quantile(0.25)), 3),
                              "p75_atr_mult": round(float(x.quantile(0.75)), 3),
                              "median_pct_price": round(float(pd.to_numeric(
                                  df[f"stop_{side}_pct_price"], errors="coerce").dropna().median()), 3)}
    return {
        "bars": n,
        "anchor_ok_bars": int(df["anchor_ok"].sum()) if "anchor_ok" in df.columns else None,
        "anchor_ok_frac": round(float(df["anchor_ok"].mean()), 4) if "anchor_ok" in df.columns else None,
        "swing_high_confirmed": _cnt(df["swing_high_confirmed"].astype(bool)) if "swing_high_confirmed" in df.columns else 0,
        "swing_low_confirmed": _cnt(df["swing_low_confirmed"].astype(bool)) if "swing_low_confirmed" in df.columns else 0,
        "swing_high_candidates": _cnt(df["swing_high_candidate"].astype(bool)) if "swing_high_candidate" in df.columns else 0,
        "swing_low_candidates": _cnt(df["swing_low_candidate"].astype(bool)) if "swing_low_candidate" in df.columns else 0,
        "bars_with_last_swing_high": int(pd.to_numeric(df.get("last_swing_high"), errors="coerce").notna().sum()),
        "bars_with_last_swing_low": int(pd.to_numeric(df.get("last_swing_low"), errors="coerce").notna().sum()),
        "donchian_available_frac": round(float(dh.notna().mean()), 4) if n else 0.0,
        "donchian_thin_window_bars": _cnt(pd.to_numeric(df.get("donchian_valid_frac"), errors="coerce")
                                          < cfg.min_valid_frac_in_window),
        "breakout_up": bo_up, "breakout_down": bo_dn,
        "touch_donchian_high": touch_hi, "touch_donchian_low": touch_lo,
        "touch_last_swing_high": touch_sh, "touch_last_swing_low": touch_sl,
        "close_beyond_swing_high": brk_sh, "close_below_swing_low": brk_sl,
        "stop_valid_long": _cnt(df["stop_valid_long"].astype(bool)) if "stop_valid_long" in df.columns else 0,
        "stop_valid_short": _cnt(df["stop_valid_short"].astype(bool)) if "stop_valid_short" in df.columns else 0,
        "stop_distance": dist,
        "median_swing_age_bars_high": float(pd.to_numeric(df.get("last_swing_high_pos"),
                                                          errors="coerce").median()) if n else None,
        "median_swing_age_bars_low": float(pd.to_numeric(df.get("last_swing_low_pos"),
                                                         errors="coerce").median()) if n else None,
    }


__all__ = ["add_swings", "add_donchian", "add_structural_stop", "add_levels",
           "anchor_eligible", "count_events", "plan_stop", "FrozenStop",
           "StopImmutabilityError", "LEVEL_COLUMNS"]
