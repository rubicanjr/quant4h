"""AŞAMA 6 — Baseline backtest engine: gerçek çıkış motoru + maliyet + metrikler.

Tasarım ilkeleri
----------------
* **Tek geçişli, nedensel döngü.** Bar `t`'de verilen kararlar yalnızca `t-1`
  ve öncesine bakar. Giriş bar `t`'nin AÇILIŞINDA olur ve bu giriş, bar `t-1`'in
  KAPANIŞINDA üretilmiş sinyale dayanır. Yani sinyal ve icra arasında her zaman
  bir bar vardır (kabul kriteri 3, Aşama 5).
* **Stop ASLA gevşetilmez.** `entry_stop`, giriş anındaki DONDURULMUŞ yapısal
  stop'tur ve pozisyon boyunca sabittir (Aşama 3 `FrozenStop` sözleşmesi).
* **Geçerli stopu olmayan pozisyon AÇILMAZ** (kabul kriteri 3 / H35 kilidi).
* **Maliyet iki tarafa da** işlenir: `one_way_cost_frac × notional` hem girişte
  hem çıkışta.
* **Pesimist doldurma.** Aynı barda hem stop hem TP dokunmuşsa STOP kazanır.
  Gap'ler aleyhimize çalışır: stop gap'inde open'dan (daha kötü), TP gap'inde
  open'dan (daha iyi ama gerçekçi) çıkılır.

Çıkış önceliği (tek bar içinde)
-------------------------------
1. stop ihlali  → `stop`
2. TP ihlali    → `take_profit`
3. time-stop    → `time_stop` (giriş barından itibaren `time_stop_bars` bar)

Pozisyon boyutu (eşit-risk, KARAR 6)
-----------------------------------
    units = (risk_per_trade × equity) / |entry − stop|
Böylece stop'a dokunulursa kayıp ≈ `risk_per_trade × equity` olur. Sermaye
ağırlıklandırması YOKTUR. Kaldıraç `max_leverage` ile sınırlanır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import (DEFAULT_EXIT, DEFAULT_PROFILE, RISK_PROFILES, CostModel,  # noqa: F401
                      ExitConfig)

EXIT_REASONS = ("stop", "take_profit", "time_stop", "end_of_data")


@dataclass
class Trade:
    direction: str
    signal_bar: int
    signal_timestamp_utc: str
    entry_bar: int
    entry_timestamp_utc: str
    entry_price: float
    stop_price: float
    tp_price: float
    exit_bar: int
    exit_timestamp_utc: str
    exit_price: float
    exit_reason: str
    bars_held: int
    units: float
    notional_entry: float
    notional_exit: float
    cost_entry: float
    cost_exit: float
    cost_total: float
    gross_pnl: float
    net_pnl: float
    r_multiple: float
    equity_before: float
    equity_after: float
    return_frac: float            # net_pnl / equity_before
    atr_at_entry: float
    stop_distance_atr: float

    def to_dict(self) -> Dict[str, Any]:
        return {k: (float(v) if isinstance(v, (np.floating, float)) else v)
                for k, v in self.__dict__.items()}


@dataclass
class BacktestResult:
    asset: str
    trades: List[Trade] = field(default_factory=list)
    equity: Optional[pd.DataFrame] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    buy_hold: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def _as_bool(s: Optional[pd.Series], n: int, default: bool) -> np.ndarray:
    """Boolean kolonu numpy'ye çevir. Kolon YOKSA `default` kullanılır.

    HATA KAYDI (H40): ilk sürümde ikinci argüman olarak `out.index`
    geçiriliyordu; `s` None olduğunda `len(idx)` doğru uzunluğu veriyordu ama
    `s` VARSA kolon hiç okunmuyor ve `default` kullanılıyordu. `stop_valid_long`
    için default=False olduğundan HİÇBİR pozisyon açılmıyordu. İmza artık
    açıkça `n: int` alıyor ve çağıran taraf kolonun kendisini geçirmek
    zorunda.
    """
    if s is None:
        return np.full(int(n), default, dtype=bool)
    arr = np.asarray(s)
    if arr.dtype == bool:
        return arr.copy()
    # object dtype (Python bool / karışık) -> doğrudan bool'a çevir.
    # DİKKAT: pd.to_numeric Python bool'larını NaN yapar; fillna(default) ile
    # birleşince TÜM kolon sessizce yanlış değere döner (bulunan hata H41:
    # stop_valid_long object dtype olduğu için her pozisyon "geçersiz stop"
    # diye reddedildi ve HİÇ trade üretilmedi).
    if arr.dtype == object:
        try:
            return arr.astype(bool)
        except (TypeError, ValueError):
            pass
    ser = pd.to_numeric(pd.Series(arr), errors="coerce")
    return ser.fillna(1 if default else 0).astype(bool).to_numpy()


def run_backtest(df: pd.DataFrame, cost: CostModel, *,
                 exit_cfg: ExitConfig = DEFAULT_EXIT,
                 risk_per_trade: float = 0.005,
                 starting_equity: float = 100_000.0,
                 max_leverage: float = 2.0,
                 allow_short: bool = True,
                 signal_col_long: str = "long_signal",
                 signal_col_short: str = "short_signal",
                 asset: str = "",
                 bootstrap: bool = True) -> BacktestResult:
    """Single causal pass over the frame. Returns trades + equity + metrics."""
    if exit_cfg.tune_now:
        raise ValueError("exit_cfg.tune_now=True YASAK")
    out = df.reset_index(drop=True)
    n = len(out)
    if n == 0:
        raise ValueError("run_backtest: boş frame")

    ts = pd.to_datetime(out["timestamp_utc"], utc=True)
    open_ = pd.to_numeric(out["open"], errors="coerce").to_numpy(dtype="float64")
    high = pd.to_numeric(out["high"], errors="coerce").to_numpy(dtype="float64")
    low = pd.to_numeric(out["low"], errors="coerce").to_numpy(dtype="float64")
    close = pd.to_numeric(out["close"], errors="coerce").to_numpy(dtype="float64")
    stop_l = (pd.to_numeric(out["stop_long"], errors="coerce").to_numpy(dtype="float64")
              if "stop_long" in out.columns else np.full(n, np.nan))
    stop_s = (pd.to_numeric(out["stop_short"], errors="coerce").to_numpy(dtype="float64")
              if "stop_short" in out.columns else np.full(n, np.nan))
    valid_l = _as_bool(out["stop_valid_long"] if "stop_valid_long" in out.columns else None,
                       n, False)
    valid_s = _as_bool(out["stop_valid_short"] if "stop_valid_short" in out.columns else None,
                       n, False)
    atr = (pd.to_numeric(out["atr"], errors="coerce").to_numpy(dtype="float64")
           if "atr" in out.columns else np.full(n, np.nan))
    sig_l = _as_bool(out[signal_col_long] if signal_col_long in out.columns else None,
                     n, False)
    sig_s = (_as_bool(out[signal_col_short] if signal_col_short in out.columns else None,
                      n, False) if allow_short else np.zeros(n, dtype=bool))
    tradable = ~_as_bool(out["non_tradable"] if "non_tradable" in out.columns else None,
                         n, False)
    ret_ok = _as_bool(out["return_valid"] if "return_valid" in out.columns else None,
                      n, True)

    one_way = cost.one_way_cost_frac
    ts_arr = ts.to_numpy()
    equity = starting_equity
    trades: List[Trade] = []
    eq_curve = np.full(n, np.nan)
    pos_open = np.zeros(n, dtype=np.int8)
    in_pos = False
    entry_i = -1
    direction = ""
    entry_px = np.nan
    stop_px = np.nan
    tp_px = np.nan
    units = 0.0
    eq_before = np.nan
    atr_entry = np.nan
    rejected_no_stop = 0
    rejected_not_tradable = 0

    def _cost(notional: float) -> float:
        return abs(notional) * one_way if exit_cfg.apply_costs_both_sides else 0.0

    for t in range(n):
        # ---------- 0) maruziyet bayrağı: bar t SIRASINDA pozisyon var mıydı? ----------
        # Çıkış barı da DAHİLDİR (pozisyon o barın içinde kapanır). Bu bayrak
        # exit'ten ÖNCE yazılmazsa, çıkış barında position_open=0 ama equity
        # gerçekleşen değere atlamış görünür ve "pozisyon yokken equity düzdür"
        # denetimi yanlış alarm verir (bulunan hata H43).
        pos_open[t] = 1 if in_pos else 0

        # ---------- 1) açık pozisyonun çıkışı (bar t'nin OHLC'si) ----------
        if in_pos:
            exit_px = np.nan
            reason = ""
            if direction == "long":
                hit_stop = np.isfinite(stop_px) and low[t] <= stop_px
                hit_tp = np.isfinite(tp_px) and high[t] >= tp_px
            else:
                hit_stop = np.isfinite(stop_px) and high[t] >= stop_px
                hit_tp = np.isfinite(tp_px) and low[t] <= tp_px
            timed_out = (t - entry_i) >= exit_cfg.time_stop_bars
            if hit_stop and hit_tp:
                # KABUL KRİTERİ 2: aynı barda çakışma -> STOP öncelikli (pesimist)
                reason, exit_px = "stop", (open_[t] if (direction == "long" and open_[t] < stop_px)
                                           or (direction == "short" and open_[t] > stop_px)
                                           else stop_px)
            elif hit_stop:
                gap = (open_[t] < stop_px) if direction == "long" else (open_[t] > stop_px)
                exit_px = open_[t] if gap else stop_px
                reason = "stop"
            elif hit_tp:
                gap = (open_[t] > tp_px) if direction == "long" else (open_[t] < tp_px)
                exit_px = open_[t] if gap else tp_px
                reason = "take_profit"
            elif timed_out:
                exit_px = close[t]
                reason = "time_stop"
            if reason:
                trades.append(_close_trade(direction, entry_i, entry_px, stop_px, tp_px,
                                           t, exit_px, reason, units, eq_before, atr_entry,
                                           one_way, _cost, ts_arr, equity))
                equity = trades[-1].equity_after
                in_pos = False

        # ---------- 2) bar t-1'in sinyaline göre bar t AÇILIŞINDA giriş ----------
        prev = t - 1
        if (not in_pos) and prev >= 0 and (sig_l[prev] or sig_s[prev]):
            want_long = bool(sig_l[prev])
            d = "long" if want_long else "short"
            sp = stop_l[prev] if want_long else stop_s[prev]
            sv = valid_l[prev] if want_long else valid_s[prev]
            entry_px = open_[t]
            if not np.isfinite(entry_px) or entry_px <= 0:
                rejected_not_tradable += 1
            elif not tradable[t] or not ret_ok[t]:
                # giriş barı kendisi işlem-dışıysa (kesinti devamı, ince bar,
                # kurumsal aksiyon) pozisyon AÇILMAZ
                rejected_not_tradable += 1
            elif exit_cfg.require_valid_stop and (not sv or not np.isfinite(sp)):
                rejected_no_stop += 1            # KABUL KRİTERİ 3 / H35 kilidi
            elif (want_long and sp >= entry_px) or ((not want_long) and sp <= entry_px):
                rejected_no_stop += 1            # geometri bozuk: stop girişin yanlış tarafında
            else:
                direction = d
                stop_px = float(sp)
                risk_per_unit = abs(entry_px - stop_px)
                tp_px = (entry_px + exit_cfg.take_profit_r * risk_per_unit) if want_long \
                    else (entry_px - exit_cfg.take_profit_r * risk_per_unit)
                risk_amount = risk_per_trade * equity
                units = risk_amount / risk_per_unit if risk_per_unit > 0 else 0.0
                max_units = (equity * max_leverage) / entry_px if entry_px > 0 else 0.0
                units = min(units, max_units)
                eq_before = equity
                atr_entry = float(atr[prev]) if np.isfinite(atr[prev]) else np.nan
                entry_i = t
                in_pos = True
                pos_open[t] = 1

        # ---------- 3) mark-to-market equity ----------
        if in_pos:
            if direction == "long":
                unreal = (close[t] - entry_px) * units
            else:
                unreal = (entry_px - close[t]) * units
            eq_curve[t] = equity + unreal
        else:
            eq_curve[t] = equity

    # ---------- veri sonunda açık pozisyon: zorunlu kapatma (şeffaf) ----------
    warnings: List[str] = []
    if in_pos:
        t = n - 1
        trades.append(_close_trade(direction, entry_i, entry_px, stop_px, tp_px,
                                   t, close[t], "end_of_data", units, eq_before, atr_entry,
                                   one_way, _cost, ts_arr, equity))
        equity = trades[-1].equity_after
        eq_curve[t] = equity
        warnings.append("Backtest sonunda pozisyon AÇIKTI; son barın kapanışından "
                        "'end_of_data' sebebiyle kapatıldı (şeffaflık için ayrı reason).")
        pos_open[t] = 0

    eq_df = pd.DataFrame({"timestamp_utc": ts, "equity": eq_curve,
                          "position_open": pos_open})
    res = BacktestResult(asset=asset or str(out["symbol"].iloc[0]) if "symbol" in out.columns else asset,
                         trades=trades, equity=eq_df,
                         config={"time_stop_bars": exit_cfg.time_stop_bars,
                                 "take_profit_r": exit_cfg.take_profit_r,
                                 "same_bar_priority": exit_cfg.same_bar_priority,
                                 "risk_per_trade": risk_per_trade,
                                 "max_leverage": max_leverage,
                                 "allow_short": allow_short,
                                 "one_way_cost_frac": one_way,
                                 "round_trip_bps": cost.round_trip_bps,
                                 "starting_equity": starting_equity,
                                 "rejected_no_valid_stop": rejected_no_stop,
                                 "rejected_not_tradable": rejected_not_tradable})
    res.metrics = compute_metrics(trades, eq_df, starting_equity, exit_cfg, bootstrap)
    res.buy_hold = buy_hold_reference(out, cost, starting_equity, allow_short=False)
    res.warnings = warnings + res.metrics.get("warnings", [])
    return res


def _close_trade(direction: str, entry_i: int, entry_px: float, stop_px: float,
                 tp_px: float, t: int, exit_px: float, reason: str, units: float,
                 eq_before: float, atr_entry: float, one_way: float,
                 cost_fn, ts_arr, equity: float) -> Trade:
    """Build a Trade record. Costs are applied to BOTH sides."""
    if direction == "long":
        gross = (exit_px - entry_px) * units
    else:
        gross = (entry_px - exit_px) * units
    n_entry = abs(entry_px * units)
    n_exit = abs(exit_px * units)
    c_entry = n_entry * one_way
    c_exit = n_exit * one_way
    net = gross - c_entry - c_exit
    risk_per_unit = abs(entry_px - stop_px)
    r_mult = ((exit_px - entry_px) / risk_per_unit) if direction == "long" and risk_per_unit > 0 \
        else (((entry_px - exit_px) / risk_per_unit) if risk_per_unit > 0 else np.nan)
    eq_after = equity + net
    return Trade(
        direction=direction, signal_bar=entry_i - 1,
        signal_timestamp_utc=str(pd.Timestamp(ts_arr[entry_i - 1])) if entry_i - 1 >= 0 else "",
        entry_bar=entry_i, entry_timestamp_utc=str(pd.Timestamp(ts_arr[entry_i])),
        entry_price=float(entry_px), stop_price=float(stop_px),
        tp_price=float(tp_px) if np.isfinite(tp_px) else np.nan,
        exit_bar=t, exit_timestamp_utc=str(pd.Timestamp(ts_arr[t])),
        exit_price=float(exit_px), exit_reason=reason, bars_held=int(t - entry_i),
        units=float(units), notional_entry=float(n_entry), notional_exit=float(n_exit),
        cost_entry=float(c_entry), cost_exit=float(c_exit),
        cost_total=float(c_entry + c_exit), gross_pnl=float(gross), net_pnl=float(net),
        r_multiple=float(r_mult) if np.isfinite(r_mult) else np.nan,
        equity_before=float(eq_before), equity_after=float(eq_after),
        return_frac=float(net / eq_before) if eq_before else np.nan,
        atr_at_entry=float(atr_entry) if np.isfinite(atr_entry) else np.nan,
        stop_distance_atr=float(risk_per_unit / atr_entry)
        if (atr_entry and np.isfinite(atr_entry) and atr_entry > 0) else np.nan,
    )


# --------------------------------------------------------------------------
# metrikler
# --------------------------------------------------------------------------

def compute_metrics(trades: Sequence[Trade], eq: pd.DataFrame, starting_equity: float,
                    cfg: ExitConfig = DEFAULT_EXIT, bootstrap: bool = True) -> Dict[str, Any]:
    warns: List[str] = []
    n_tr = len(trades)
    res: Dict[str, Any] = {"n_trades": n_tr}
    if n_tr == 0:
        res.update({"win_rate": None, "n_wins": 0, "n_losses": 0, "n_breakeven": 0,
                    "profit_factor_gross": None, "profit_factor_net": None,
                    "expectancy_r": None, "expectancy_r_median": None,
                    "avg_win_r": None, "avg_loss_r": None,
                    "avg_holding_bars": None, "median_holding_bars": None,
                    "max_holding_bars": None,
                    "max_drawdown_frac": 0.0, "final_equity": starting_equity,
                    "net_return_frac": 0.0, "total_cost": 0.0, "total_gross": 0.0,
                    "total_net": 0.0, "cost_as_pct_of_gross": None,
                    "exposure_frac": 0.0, "exit_reason_mix": {}, "direction_mix": {},
                    "avg_stop_distance_atr": None,
                    "cost_row": {"total_cost": 0.0,
                                 "net_return_with_cost_frac": 0.0,
                                 "gross_return_without_cost_frac": 0.0,
                                 "verdict": "trade yok"},
                    "statistically_weak": True})
        res["warnings"] = ["Hiç trade yok: metrikler tanımsız."]
        return res

    nets = np.array([t.net_pnl for t in trades], dtype="float64")
    grosses = np.array([t.gross_pnl for t in trades], dtype="float64")
    costs = np.array([t.cost_total for t in trades], dtype="float64")
    rs = np.array([t.r_multiple for t in trades], dtype="float64")
    wins = nets > 0
    losses = nets < 0
    gp = float(grosses[wins].sum()) if wins.any() else 0.0
    gl = float(-grosses[losses].sum()) if losses.any() else 0.0
    np_ = float(nets[wins].sum()) if wins.any() else 0.0
    nl = float(-nets[losses].sum()) if losses.any() else 0.0

    final_equity = float(eq["equity"].dropna().iloc[-1]) if len(eq) else starting_equity
    peak = eq["equity"].cummax()
    dd = (eq["equity"] - peak) / peak.replace(0, np.nan)
    res.update({
        "win_rate": round(float(wins.mean()), 4),
        "n_wins": int(wins.sum()), "n_losses": int(losses.sum()),
        "n_breakeven": int((nets == 0).sum()),
        "profit_factor_gross": round(gp / gl, 4) if gl > 0 else (None if gp == 0 else float("inf")),
        "profit_factor_net": round(np_ / nl, 4) if nl > 0 else (None if np_ == 0 else float("inf")),
        "expectancy_r": round(float(np.nanmean(rs)), 4),
        "expectancy_r_median": round(float(np.nanmedian(rs)), 4),
        "avg_win_r": round(float(np.nanmean(rs[rs > 0])), 4) if (rs > 0).any() else None,
        "avg_loss_r": round(float(np.nanmean(rs[rs < 0])), 4) if (rs < 0).any() else None,
        "avg_holding_bars": round(float(np.mean([t.bars_held for t in trades])), 2),
        "median_holding_bars": float(np.median([t.bars_held for t in trades])),
        "max_holding_bars": int(max(t.bars_held for t in trades)),
        "total_gross": float(grosses.sum()),
        "total_cost": float(costs.sum()),
        "total_net": float(nets.sum()),
        "cost_as_pct_of_gross": round(float(costs.sum() / abs(grosses.sum())) * 100, 2)
        if grosses.sum() != 0 else None,
        "net_return_frac": round(final_equity / starting_equity - 1.0, 6),
        "final_equity": final_equity,
        "max_drawdown_frac": round(float(dd.min()), 6) if dd.notna().any() else 0.0,
        "exposure_frac": round(float(eq["position_open"].mean()), 4) if "position_open" in eq else None,
        "exit_reason_mix": {k: int(v) for k, v in
                            pd.Series([t.exit_reason for t in trades]).value_counts().items()},
        "direction_mix": {k: int(v) for k, v in
                          pd.Series([t.direction for t in trades]).value_counts().items()},
        "avg_stop_distance_atr": round(float(np.nanmean([t.stop_distance_atr for t in trades])), 3),
    })
    # maliyet satırı (kabul kriteri 7): maliyetsiz sonuç NE OLURDU
    res["cost_row"] = {
        "total_cost": res["total_cost"],
        "net_return_with_cost_frac": res["net_return_frac"],
        "gross_return_without_cost_frac": round(
            (starting_equity + float(grosses.sum())) / starting_equity - 1.0, 6),
        "verdict": ("maliyet sonucu TERSİNE ÇEVİRİYOR"
                    if (starting_equity + float(grosses.sum())) > starting_equity
                    and final_equity <= starting_equity else
                    "maliyet sonrası da pozitif" if final_equity > starting_equity else
                    "maliyet öncesi de negatif"),
    }
    weak = n_tr < cfg.min_trades_for_significance
    res["statistically_weak"] = bool(weak)
    # Bootstrap CI HER zaman hesaplanır (n>=5): "zayıf" bayrağı yalnızca
    # eşik altı örneklem için ZORUNLU uyarıdır, ama CI olmadan büyük örneklemli
    # bir varlığı küçük örneklemliyle KARŞILAŞTIRMAK da mümkün olmazdı.
    if bootstrap and n_tr >= 5:
        eq_before = np.array([t.equity_before for t in trades], dtype="float64")
        # HATA KAYDI (H42): `max(1e-9, np.array(...))` Python max'i bir diziyle
        # karşılaştırıyor -> "truth value is ambiguous". np.maximum kullanılmalı.
        safe = np.maximum(eq_before, 1e-9)
        res["bootstrap"] = bootstrap_ci(rs, nets / safe, cfg)
    if weak:
        warns.append(
            f"İSTATİSTİKSEL ZAYIF: {n_tr} trade < {cfg.min_trades_for_significance} eşik. "
            f"Tüm metrikler bootstrap CI ile birlikte OKUNMALI; tek başına nokta "
            f"tahminine dayanarak karar VERİLMEZ.")
    if res["max_drawdown_frac"] is not None and res["max_drawdown_frac"] < -0.25:
        warns.append(f"Max DD %{res['max_drawdown_frac'] * 100:.1f} — %25'i aşıyor; "
                     f"risk profili/position sizing gözden geçirilmeli.")
    res["warnings"] = warns
    return res


def bootstrap_ci(r_multiples: np.ndarray, returns: np.ndarray,
                 cfg: ExitConfig = DEFAULT_EXIT) -> Dict[str, Any]:
    """Bootstrap CI for expectancy(R) and win rate. Resampling trades, not bars."""
    r = r_multiples[np.isfinite(r_multiples)]
    ret = returns[np.isfinite(returns)]
    if len(r) < 5:
        return {"note": "bootstrap için yetersiz trade"}
    rng = np.random.default_rng(cfg.random_seed)
    n = len(r)
    B = int(cfg.bootstrap_resamples)
    idx = rng.integers(0, n, size=(B, n))
    exp = r[idx].mean(axis=1)
    wr = (r[idx] > 0).mean(axis=1)
    ret_b = ret[idx].mean(axis=1) if len(ret) == n else None
    out = {
        "resamples": B, "n_trades": int(n),
        "expectancy_r_ci95": [round(float(np.quantile(exp, 0.025)), 4),
                              round(float(np.quantile(exp, 0.975)), 4)],
        "expectancy_r_p05": round(float(np.quantile(exp, 0.05)), 4),
        "win_rate_ci95": [round(float(np.quantile(wr, 0.025)), 4),
                          round(float(np.quantile(wr, 0.975)), 4)],
        "prob_expectancy_positive": round(float((exp > 0).mean()), 4),
    }
    if ret_b is not None:
        out["mean_return_per_trade_ci95"] = [round(float(np.quantile(ret_b, 0.025)), 6),
                                             round(float(np.quantile(ret_b, 0.975)), 6)]
    return out


def buy_hold_reference(df: pd.DataFrame, cost: CostModel, starting_equity: float,
                       allow_short: bool = False) -> Dict[str, Any]:
    """Aynı dönemde, aynı maliyetle buy&hold (tek giriş + tek çıkış)."""
    close = pd.to_numeric(df["close"], errors="coerce")
    close = close.dropna()
    if len(close) < 2:
        return {}
    p0, p1 = float(close.iloc[0]), float(close.iloc[-1])
    gross_frac = p1 / p0 - 1.0
    one_way = cost.one_way_cost_frac
    net_frac = gross_frac - 2 * one_way
    equity = starting_equity * (1 + net_frac)
    peak = close.cummax()
    dd = float(((close - peak) / peak).min())
    return {"gross_return_frac": round(gross_frac, 6),
            "cost_frac": round(2 * one_way, 6),
            "net_return_frac": round(net_frac, 6),
            "final_equity": round(float(equity), 2),
            "max_drawdown_frac": round(dd, 6),
            "first": str(pd.to_datetime(df["timestamp_utc"], utc=True).iloc[0]),
            "last": str(pd.to_datetime(df["timestamp_utc"], utc=True).iloc[-1])}


def equity_from_trades(trades: Sequence[Trade], starting_equity: float) -> np.ndarray:
    """Bağımsız yeniden hesap: equity_final = start + Σ net_pnl.

    Motorun ürettiği equity eğrisiyle KARŞILAŞTIRMAK için kullanılır (kabul
    kriteri 8). İki yol aynı sonucu vermiyorsa motorda hata vardır.
    """
    eq = starting_equity
    curve = []
    for t in trades:
        eq += t.net_pnl
        curve.append(eq)
    return np.array(curve, dtype="float64")


__all__ = ["run_backtest", "compute_metrics", "bootstrap_ci", "buy_hold_reference",
           "equity_from_trades", "Trade", "BacktestResult", "EXIT_REASONS"]
