"""AŞAMA 8 — Portföy simülatörü (event-driven · t+1 icra · çift taraf maliyet).

Sözleşme
--------
* Sinyal akışı: CAPPED (Aşama 5/6/7 ile aynı `long_signal`/`short_signal`
  kolonları, A0 anchor). Çıkış profili Aşama 9'a kadar **P0×A0 KİLİTLİ**
  (`ExitConfig.profile != "P0"` -> ValueError).
* İcra: sinyal bar `i−1` KAPANIŞI -> giriş bar `i` AÇILIŞI (`open[i]`). Stop,
  SİNYAL barındaki dondurulmuş yapısal stop'tur (H35: geçerli stop yoksa giriş YOK).
* Fill kuralları Aşama 6 motoruyla birebir: aynı barda stop+TP çakışması -> STOP
  (pesimist); stop gap'i open'dan (aleyhimize); TP gap'i open'dan (lehimize);
  time-stop kapanıştan; maliyet (komisyon + yarım spread + slippage) İKİ tarafa.
* D6 kilidi: bar içinde kapanan pozisyonun ardından AYNI barın açılışında yeni
  giriş YOK.
* **Tavanlar YALNIZ GİRİŞTE uygulanır; çıkışlara DOKUNMAZ.** Hiçbir tavan
  pozisyon kapatmaz (fail-closed: limit aşımında yeni giriş reddedilir).
* Equity ORTAKTUR (tek portföy nakit hesabı, REALIZED baz); boyutlama her girişte
  güncel realized equity üzerinden: units = (risk_per_trade × equity) /
  |giriş − stop|, `max_leverage` kıskacıyla. Isı = giriş anındaki planlanan risk
  oranı (|giriş−stop| × units / equity_at_entry); kıskaç ısıyı yalnız KÜÇÜLTÜR.
* Günlük/haftalık limitler REALIZED P&L bazlıdır (UTC günü / ISO haftası; dönem
  başı realized equity'ye oran). Aşım -> dönem sonuna kadar yeni giriş YOK.
* Ardışık kayıp freni: varlık bazında (long+short ORTAK sayaç) `loss_streak_count`
  ardışık kayıp -> o varlığın KENDİ ızgarasında `loss_streak_block_bars` bar
  giriş yok. Kazanç sayacı sıfırlar.
* Global zaman çizelgesi: tüm akışların timestamp BİRLEŞİMİ (grid fazları farklı —
  PROGRESS kayıt 8). Mark-to-market her global noktada akışların SON KAPANIŞI ile.

Regresyon garantisi: `RiskLimits.no_limits()` + TEK akış -> Aşama 6
`run_backtest` çıktısıyla birebir (`tests/test_risk.py` kilitler).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..backtest.engine import Trade, _close_trade          # bilinçli private import:
# fill/muhasebe matematiğinin TEK kaynağı engine'de kalır (Aşama 6 birebirliği).
from ..config import ExitConfig
from .limits import REJECTION_KEYS, RiskLimits, bank_codes, bucket_of


@dataclass
class StreamSpec:
    key: str                 # "BTC" / "GOLD" / "AEFES" …
    direction: str           # "long" | "short"
    frame: pd.DataFrame      # capped sinyal frame'i (A0 anchor kolonlarıyla)
    cost: Any                # CostModel
    max_leverage: float = 2.0
    is_stock: bool = False

    def __post_init__(self) -> None:
        if self.direction not in ("long", "short"):
            raise ValueError(f"direction geçersiz: {self.direction!r}")
        if self.is_stock and self.direction != "long":
            raise ValueError("BIST30 hisseleri LONG-ONLY (KARAR 4)")


@dataclass(eq=False)
class _OpenPos:
    key: str
    direction: str
    stream: Any              # _Stream referansı (mtm için)
    entry_i: int             # akış ızgarasında giriş bar indeksi
    entry_px: float
    stop_px: float
    tp_px: float
    units: float
    eq_before: float
    atr_entry: float
    risk_frac: float         # planlanan risk (equity oranı) — ISI birimi
    bucket: str
    is_stock: bool


@dataclass
class SimResult:
    trades: List[Trade] = field(default_factory=list)
    equity: Optional[pd.DataFrame] = None   # timestamp_utc, equity, n_open, metals_heat, basket_heat
    rejections: Dict[str, int] = field(default_factory=dict)
    peaks: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


class _Stream:
    """Tek yön akışı: frame kolonlarını numpy'ye çözer; P0 fill kuralları motorla aynı."""

    def __init__(self, spec: StreamSpec):
        df = spec.frame.reset_index(drop=True)
        self.spec = spec
        n = len(df)
        self.n = n
        self.ts = pd.to_datetime(df["timestamp_utc"], utc=True)
        self.ts_arr = self.ts.to_numpy()
        self.ts_int = self.ts.to_numpy(dtype="datetime64[ns]").view("int64")
        self.open = pd.to_numeric(df["open"], errors="coerce").to_numpy("float64")
        self.high = pd.to_numeric(df["high"], errors="coerce").to_numpy("float64")
        self.low = pd.to_numeric(df["low"], errors="coerce").to_numpy("float64")
        self.close = pd.to_numeric(df["close"], errors="coerce").to_numpy("float64")
        sig_col = "long_signal" if spec.direction == "long" else "short_signal"
        stop_col = "stop_long" if spec.direction == "long" else "stop_short"
        valid_col = "stop_valid_long" if spec.direction == "long" else "stop_valid_short"
        self.sig = self._bool(df.get(sig_col), n, False)
        self.stop = (pd.to_numeric(df[stop_col], errors="coerce").to_numpy("float64")
                     if stop_col in df.columns else np.full(n, np.nan))
        self.valid = self._bool(df.get(valid_col), n, False)
        self.tradable = ~self._bool(df.get("non_tradable"), n, False)
        self.ret_ok = self._bool(df.get("return_valid"), n, True)
        self.atr = (pd.to_numeric(df["atr"], errors="coerce").to_numpy("float64")
                    if "atr" in df.columns else np.full(n, np.nan))
        self.i = 0                       # sıradaki bar indeksi
        self.pos: Optional[_OpenPos] = None
        self.exited_this_bar = False
        self.last_close = np.nan
        self.one_way = float(spec.cost.one_way_cost_frac)

    @staticmethod
    def _bool(s, n: int, default: bool) -> np.ndarray:
        if s is None:
            return np.full(n, default, dtype=bool)
        arr = np.asarray(s)
        if arr.dtype == bool:
            return arr.copy()
        if arr.dtype == object:                       # H41 dersi: object dtype -> astype(bool)
            try:
                return arr.astype(bool)
            except (TypeError, ValueError):
                pass
        return pd.to_numeric(pd.Series(arr), errors="coerce").fillna(
            1 if default else 0).astype(bool).to_numpy()


def simulate_portfolio(streams: List[StreamSpec], limits: RiskLimits, *,
                       risk_per_trade: float,
                       starting_equity: float = 100_000.0,
                       exit_cfg: ExitConfig = ExitConfig()) -> SimResult:
    """Tüm akışları TEK global zaman çizelgesinde nedensel olarak işler."""
    if exit_cfg.profile != "P0":
        raise ValueError("Aşama 8 simülatörü P0×A0 ile KİLİTLİ (seçim Aşama 9'da); "
                         f"profile={exit_cfg.profile!r} verilemez")
    if not streams:
        raise ValueError("simulate_portfolio: boş akış listesi")
    ss = [_Stream(sp) for sp in streams]
    banks = set(bank_codes())

    events: Dict[int, List[int]] = {}
    for si, s in enumerate(ss):
        for tv in s.ts_int.tolist():
            events.setdefault(int(tv), []).append(si)
    timeline = sorted(events)

    equity = float(starting_equity)                  # REALIZED nakit
    trades: List[Trade] = []
    rej: Dict[str, int] = {k: 0 for k in REJECTION_KEYS}
    open_positions: List[_OpenPos] = []

    streak: Dict[str, int] = {}
    block_until_i: Dict[str, int] = {}               # key -> kendi ızgarasında son blok barı (dahil)

    day_key, week_key = None, None
    day_start_eq = week_start_eq = float(starting_equity)
    day_pnl = week_pnl = 0.0
    daily_blocked = weekly_blocked = False

    curve_ts: List[Any] = []
    curve_eq: List[float] = []
    curve_n: List[int] = []
    curve_mh: List[float] = []
    curve_bh: List[float] = []
    peak_n = peak_bank = 0
    peak_mh = peak_bh = peak_th = 0.0

    def _heat(bucket: str) -> float:
        return sum(p.risk_frac for p in open_positions if p.bucket == bucket)

    def _count(pred) -> int:
        return sum(1 for p in open_positions if pred(p))

    def _register_close(key: str, net: float, exit_i: int) -> None:
        nonlocal equity, day_pnl, week_pnl, daily_blocked, weekly_blocked
        equity += net
        day_pnl += net
        week_pnl += net
        if limits.unlimited:
            return
        if day_pnl <= -limits.max_daily_loss * day_start_eq:
            daily_blocked = True
        if week_pnl <= -limits.max_weekly_loss * week_start_eq:
            weekly_blocked = True
        if net < 0:
            streak[key] = streak.get(key, 0) + 1
            if streak[key] >= limits.loss_streak_count:
                block_until_i[key] = exit_i + limits.loss_streak_block_bars
                streak[key] = 0
        else:
            streak[key] = 0

    def _close(s: _Stream, i: int, exit_px: float, reason: str) -> None:
        p = s.pos
        assert p is not None
        t = _close_trade(s.spec.direction, p.entry_i, p.entry_px, p.stop_px, p.tp_px,
                         i, exit_px, reason, p.units, p.units, p.eq_before,
                         p.atr_entry, s.one_way, s.ts_arr, profile="P0")
        t.group_key = p.key                      # raporlama: varlık grubu etiketi
        trades.append(t)
        _register_close(p.key, t.net_pnl, i)
        open_positions[:] = [q for q in open_positions if q is not p]
        s.pos = None
        s.exited_this_bar = True

    def _exit_step(s: _Stream, i: int) -> None:
        p = s.pos
        if p is None:
            return
        long_ = p.direction == "long"
        hit_stop = np.isfinite(p.stop_px) and (s.low[i] <= p.stop_px if long_
                                               else s.high[i] >= p.stop_px)
        hit_tp = np.isfinite(p.tp_px) and (s.high[i] >= p.tp_px if long_
                                           else s.low[i] <= p.tp_px)
        timed_out = (i - p.entry_i) >= exit_cfg.time_stop_bars
        if hit_stop:                       # KABUL KRİTERİ 2: çakışmada STOP öncelikli
            gap = (s.open[i] < p.stop_px) if long_ else (s.open[i] > p.stop_px)
            _close(s, i, s.open[i] if gap else p.stop_px, "stop")
        elif hit_tp:
            gap = (s.open[i] > p.tp_px) if long_ else (s.open[i] < p.tp_px)
            _close(s, i, s.open[i] if gap else p.tp_px, "take_profit")
        elif timed_out:
            _close(s, i, s.close[i], "time_stop")

    def _try_entry(s: _Stream, i: int) -> None:
        key = s.spec.key
        prev = i - 1
        entry_px = s.open[i]
        if not np.isfinite(entry_px) or entry_px <= 0:
            rej["invalid_price"] += 1
            return
        if not s.tradable[i] or not s.ret_ok[i]:
            rej["not_tradable"] += 1
            return
        stop_px = s.stop[prev]                       # DONDURULMUŞ stop (sinyal barı)
        if not bool(s.valid[prev]) or not np.isfinite(stop_px):
            rej["no_valid_stop"] += 1                # H35 kilidi
            return
        long_ = s.spec.direction == "long"
        if (long_ and stop_px >= entry_px) or ((not long_) and stop_px <= entry_px):
            rej["stop_geometry"] += 1
            return
        if not limits.unlimited:
            if i <= block_until_i.get(key, -(10 ** 9)):
                rej["loss_streak_brake"] += 1
                return
            if daily_blocked:
                rej["daily_loss_limit"] += 1
                return
            if weekly_blocked:
                rej["weekly_loss_limit"] += 1
                return
            if len(open_positions) >= limits.max_concurrent_total:
                rej["total_concurrent"] += 1
                return
            if _count(lambda p: p.key == key) >= limits.per_asset_cap(key):
                rej["per_asset_concurrent"] += 1
                return
            if s.spec.is_stock:
                if _count(lambda p: p.is_stock) >= limits.max_basket_concurrent:
                    rej["basket_concurrent"] += 1
                    return
                if key in banks and \
                        _count(lambda p: p.key in banks) >= limits.max_bank_concurrent:
                    rej["bank_sector"] += 1
                    return
        # ---- boyutlama: eşit-risk (Aşama 6 motor formülüyle aynı) ----
        risk_per_unit = abs(entry_px - stop_px)
        if risk_per_unit <= 0:
            rej["stop_geometry"] += 1
            return
        units = (risk_per_trade * equity) / risk_per_unit
        max_units = (equity * s.spec.max_leverage) / entry_px if entry_px > 0 else 0.0
        units = min(units, max_units)
        if units <= 0 or not np.isfinite(units):
            rej["invalid_price"] += 1
            return
        risk_frac = (risk_per_unit * units) / equity if equity > 0 else 0.0
        bkt = bucket_of(key)
        if not limits.unlimited:
            if bkt == "precious_metals" and \
                    _heat("precious_metals") + risk_frac > \
                    limits.metals_heat_max_rpt_mult * risk_per_trade + 1e-12:
                rej["metals_bucket_heat"] += 1
                return
            if s.spec.is_stock:
                if risk_frac > limits.per_stock_heat_max_rpt_mult * risk_per_trade + 1e-12:
                    rej["per_stock_heat"] += 1
                    return
                if _heat("bist30_basket") + risk_frac > \
                        limits.basket_heat_max_rpt_mult * risk_per_trade + 1e-12:
                    rej["basket_heat"] += 1
                    return
        tp_px = (entry_px + exit_cfg.take_profit_r * risk_per_unit) if long_ \
            else (entry_px - exit_cfg.take_profit_r * risk_per_unit)
        atr_prev = float(s.atr[prev]) if np.isfinite(s.atr[prev]) else np.nan
        pos = _OpenPos(key=key, direction=s.spec.direction, stream=s,
                       entry_i=i, entry_px=float(entry_px), stop_px=float(stop_px),
                       tp_px=float(tp_px), units=float(units), eq_before=float(equity),
                       atr_entry=atr_prev, risk_frac=float(risk_frac), bucket=bkt,
                       is_stock=bool(s.spec.is_stock))
        open_positions.append(pos)
        s.pos = pos

    for tv in timeline:
        t = pd.Timestamp(tv)
        dk = t.date()
        wk = (t.isocalendar()[0], t.isocalendar()[1])
        if dk != day_key:
            day_key, day_start_eq, day_pnl, daily_blocked = dk, equity, 0.0, False
        if wk != week_key:
            week_key, week_start_eq, week_pnl, weekly_blocked = wk, equity, 0.0, False
        for si in events[tv]:
            s = ss[si]
            i = s.i
            s.exited_this_bar = False
            _exit_step(s, i)
            if s.pos is None and not s.exited_this_bar and i >= 1 and s.sig[i - 1]:
                _try_entry(s, i)
            s.last_close = s.close[i]
            s.i = i + 1
        # ---- mark-to-market + tepe kayıtları ----
        unreal = 0.0
        for p in open_positions:
            lc = p.stream.last_close
            if np.isfinite(lc):
                unreal += ((lc - p.entry_px) if p.direction == "long"
                           else (p.entry_px - lc)) * p.units
        n_open = len(open_positions)
        mh, bh = _heat("precious_metals"), _heat("bist30_basket")
        th = sum(p.risk_frac for p in open_positions)
        nbank = _count(lambda p: p.key in banks)
        peak_n = max(peak_n, n_open)
        peak_mh = max(peak_mh, mh)
        peak_bh = max(peak_bh, bh)
        peak_th = max(peak_th, th)
        peak_bank = max(peak_bank, nbank)
        curve_ts.append(t)
        curve_eq.append(equity + unreal)
        curve_n.append(n_open)
        curve_mh.append(mh)
        curve_bh.append(bh)

    # ---- veri sonunda açık pozisyonlar: şeffaf zorunlu kapanış ----
    warns: List[str] = []
    for s in ss:
        if s.pos is not None:
            i = s.n - 1
            _close(s, i, s.close[i], "end_of_data")
            warns.append(f"{s.spec.key}/{s.spec.direction}: sonda açıktı, "
                         f"end_of_data ile kapatıldı (şeffaf)")
    if curve_eq:
        curve_eq[-1] = equity                        # son nokta realized değere sabitlenir

    eq_df = pd.DataFrame({"timestamp_utc": curve_ts, "equity": curve_eq,
                          "n_open": curve_n, "metals_heat": curve_mh,
                          "basket_heat": curve_bh})
    peaks = {"max_concurrent_open": int(peak_n),
             "peak_metals_heat": round(float(peak_mh), 6),
             "peak_basket_heat": round(float(peak_bh), 6),
             "peak_total_heat": round(float(peak_th), 6),
             "max_bank_concurrent": int(peak_bank)}
    return SimResult(trades=trades, equity=eq_df, rejections=rej, peaks=peaks,
                     warnings=warns,
                     config={"risk_per_trade": risk_per_trade,
                             "starting_equity": starting_equity,
                             "exit_profile": "P0", "anchor": "A0",
                             "limits_unlimited": bool(limits.unlimited),
                             "n_streams": len(ss)})


__all__ = ["simulate_portfolio", "StreamSpec", "SimResult"]
