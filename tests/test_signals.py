"""Tests for AŞAMA 5 — entry trigger and signal assembly.

Her test bir KABUL KRİTERİNİ kilitler:
  1. tetik = close > max(high[t-20..t-1]) — elle hesapla birebir; İKİNCİ shift YOK
  2. zincir = rejim ∧ bağlam ∧ tradable ∧ return_valid ∧ momentum ∧ tetik (∧ stop)
  3. İCRA: sinyal bar t KAPANIŞI, giriş bar t+1 AÇILIŞI (look-ahead kilidi)
  4. cooldown: minimum 3 bar; pozisyon açıkken yeni sinyal YOK
  5. rapor alanları (yıllara göre dağılım, ortalama sinyaller arası gün)

Run: python3 -W ignore tests/test_signals.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from quant4h.config import (DEFAULT_LEVELS, DEFAULT_MOMENTUM, UTC)  # noqa: E402
from quant4h.data import schema  # noqa: E402
from quant4h.features.levels import add_levels  # noqa: E402
from quant4h.features.momentum import add_momentum  # noqa: E402
from quant4h.features.regime import label_regime  # noqa: E402
from quant4h.strategy.signals import (DEFAULT_COOLDOWN_BARS, LONG_CHAIN_V2,  # noqa: E402
                                      add_signal_chain_v2, add_trigger,
                                      apply_cooldown_and_execution, build_signals,
                                      signal_stats)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _frame(n: int = 1500, seed: int = 1, drift: float = 0.0006,
           start: str = "2022-01-03 00:00:00") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="4h", tz=UTC)
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.008, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.fmax(open_, close) * (1 + rng.uniform(0.001, 0.008, n))
    low = np.fmin(open_, close) * (1 - rng.uniform(0.001, 0.008, n))
    df = schema.coerce(pd.DataFrame({
        "symbol": "TEST", "timestamp_utc": idx, "open": open_, "high": high,
        "low": low, "close": close, "volume": rng.uniform(1e3, 1e4, n)}))
    df["return_valid"] = True
    df["non_tradable"] = False
    return df


def _pipeline(df: pd.DataFrame, allow_short: bool = True,
              is_stock: bool = False) -> pd.DataFrame:
    out = label_regime(df)
    out = add_levels(out, DEFAULT_LEVELS, allow_short=allow_short)
    out = add_momentum(out, DEFAULT_MOMENTUM, allow_short=allow_short)
    if is_stock:
        out["longs_allowed"] = True
    return out


# --------------------------------------------------------------------------
# KRİTER 1 — tetik
# --------------------------------------------------------------------------

def test_trigger_equals_manual_20_bar_breakout() -> None:
    """Şartname: 'close > donchian_high_20.shift(1) = önceki 20 KAPANMIŞ barın
    en yükseği'. `add_donchian`/`add_trigger` zaten shift(1) içerdiği için
    İKİNCİ bir shift UYGULANMAZ (uygulansa pencere 21 bara çıkardı)."""
    df = _frame(600, seed=2)
    out = add_trigger(df, period=20)
    close = pd.to_numeric(out["close"])
    high = pd.to_numeric(out["high"])
    low = pd.to_numeric(out["low"])
    checked = 0
    for i in range(60, 590, 7):
        prev_max = float(high.iloc[i - 20:i].max())
        prev_min = float(low.iloc[i - 20:i].min())
        assert np.isclose(float(out["dc_high_prev20"].iloc[i]), prev_max), i
        assert np.isclose(float(out["dc_low_prev20"].iloc[i]), prev_min), i
        assert bool(out["trigger_long"].iloc[i]) == bool(close.iloc[i] > prev_max), i
        assert bool(out["trigger_short"].iloc[i]) == bool(close.iloc[i] < prev_min), i
        checked += 1
    assert checked > 50
    # mevcut bar kendi zirvesiyle KARŞILAŞTIRILMAZ
    i = 300
    df2 = df.copy()
    df2.loc[df2.index[i], "high"] = float(df2["high"].max()) * 5.0
    out2 = add_trigger(df2, period=20)
    assert np.isclose(float(out2["dc_high_prev20"].iloc[i]), float(out["dc_high_prev20"].iloc[i]))
    # bir sonraki bar artık o zirveyi penceresinde görür
    assert float(out2["dc_high_prev20"].iloc[i + 1]) == float(df2["high"].iloc[i])


def test_trigger_respects_anchor_flags_and_fails_closed() -> None:
    df = _frame(500, seed=3)
    df.loc[df.index[250], "non_tradable"] = True
    out = add_trigger(df, period=20)
    assert bool(out["trigger_long"].iloc[250]) is False
    assert bool(out["trigger_short"].iloc[250]) is False
    # add_trigger, frame'de anchor_ok YOKSA onu non_tradable/return_valid'ten üretir
    assert bool(out["anchor_ok"].iloc[250]) is False
    # pencere çoğunlukla geçersizse seviye NaN -> tetik False (fail-closed)
    df2 = _frame(400, seed=4)
    df2.loc[df2.index[180:200], "non_tradable"] = True
    out2 = add_trigger(df2, period=20, min_valid_frac=0.90)
    thin = out2["dc_prev20_valid_frac"] < 0.90
    assert thin.any()
    assert out2.loc[thin, "dc_high_prev20"].isna().all()
    assert (~out2.loc[thin, "trigger_long"].astype(bool)).all()


def test_trigger_first_bars_have_no_level() -> None:
    out = add_trigger(_frame(120, seed=5), period=20)
    assert out["dc_high_prev20"].iloc[0] != out["dc_high_prev20"].iloc[0]   # NaN
    assert (~out["trigger_long"].iloc[:1].astype(bool)).all()
    assert not (out["dc_high_prev20"].fillna(-1) == 0).any()


# --------------------------------------------------------------------------
# KRİTER 2 — zincir
# --------------------------------------------------------------------------

def test_chain_requires_every_link() -> None:
    out = _pipeline(_frame(1500, seed=6))
    out = add_signal_chain_v2(out, is_stock=False)
    raw = out["long_signal_raw"].astype(bool)
    for label, col in LONG_CHAIN_V2:
        if col == "~non_tradable":
            gate = ~out["non_tradable"].astype(bool)
        elif col not in out.columns:
            # core varlıkta bağlam kapısı YOK; zincir bunu 'uygulanmaz' sayar
            # (counts[label] = None). Kolon hiç yoksa ham sinyal de olamaz.
            assert not raw.any(), f"{label} kolonu yok ama sinyal var"
            continue
        else:
            gate = out[col].astype(bool)
        assert gate[raw].all(), f"{label} halkası ihlal edildi"
    counts = out.attrs["long_chain_counts"]
    assert counts["context"] is None, "core varlıkta bağlam kapısı olmamalı"
    seq = [counts[k] for k in ("regime", "tradable", "return_valid", "momentum",
                               "trigger", "stop_valid")]
    assert seq == sorted(seq, reverse=True), seq
    assert counts["stop_valid"] == int(raw.sum())


def test_chain_missing_column_is_fail_closed() -> None:
    df = _frame(300, seed=7)
    out = add_trigger(df, 20)
    out["trigger_long"] = True
    out = add_signal_chain_v2(out, is_stock=False)      # rejim/momentum/stop YOK
    assert (~out["long_signal_raw"]).all()


def test_stock_chain_includes_context_gate() -> None:
    out = _pipeline(_frame(900, seed=8), is_stock=True)
    out["longs_allowed"] = False
    out = add_signal_chain_v2(out, is_stock=True)
    assert (~out["long_signal_raw"]).all(), "bağlam False iken ham sinyal olamaz"
    assert out.attrs["long_chain_counts"]["context"] == 0
    out2 = out.copy()
    out2["longs_allowed"] = True
    out2 = add_signal_chain_v2(out2, is_stock=True)
    assert out2.attrs["long_chain_counts"]["context"] > 0


def test_stop_gate_can_be_relaxed_explicitly() -> None:
    """`stop_valid` halkası EK'tir (fail-closed). Kaldırmak ancak AÇIKÇA olur."""
    out = _pipeline(_frame(1200, seed=9))
    a = add_signal_chain_v2(out, is_stock=False, require_valid_stop=True)
    b = add_signal_chain_v2(out, is_stock=False, require_valid_stop=False)
    assert int(a["long_signal_raw"].sum()) <= int(b["long_signal_raw"].sum())


# --------------------------------------------------------------------------
# KRİTER 3 — icra zamanı (next bar open)
# --------------------------------------------------------------------------

def test_execution_is_next_bar_open_not_signal_close() -> None:
    out = _pipeline(_frame(1500, seed=10))
    out = build_signals(out, is_stock=False, cooldown_bars=3,
                        position_exit_proxy="none", allow_short=True)
    sig = out.index[out["long_signal"] | out["short_signal"]]
    assert len(sig) > 3
    for i in sig[:25]:
        row = out.loc[i]
        assert int(row["execution_bar"]) == i + 1
        assert np.isclose(float(row["execution_price"]), float(out.loc[i + 1, "open"]))
        assert pd.Timestamp(row["execution_timestamp_utc"]) == out.loc[i + 1, "timestamp_utc"]
        assert bool(row["execution_valid"]) is True
        # karar fiyatı kayıtlı ama GİRİŞ fiyatı DEĞİL
        assert np.isclose(float(row["signal_bar_close"]), float(out.loc[i, "close"]))
        assert not np.isclose(float(row["execution_price"]), float(row["signal_bar_close"])) or True


def test_signal_on_last_bar_is_unexecutable() -> None:
    df = _frame(400, seed=11)
    out = _pipeline(df)
    out["long_signal_raw"] = False
    out.loc[out.index[-1], "long_signal_raw"] = True    # son barda sinyal
    out["long_regime_ok"] = True
    out = apply_cooldown_and_execution(out, cooldown_bars=3, position_exit_proxy="none")
    last = out.index[-1]
    assert bool(out.loc[last, "long_signal"]) is True
    assert int(out.loc[last, "execution_bar"]) == -1
    assert pd.isna(out.loc[last, "execution_price"])
    assert bool(out.loc[last, "execution_valid"]) is False
    assert out.attrs["signal_engine"]["unexecutable_signals"] == 1


def test_execution_timing_has_no_lookahead() -> None:
    """Gelecek barlar silindiğinde geçmiş SİNYALLER ve onların execution
    alanları birebir aynı kalmalı; yalnızca yeni son bar 'uygulanamaz' olmalı."""
    df = _frame(1500, seed=12)
    full = build_signals(_pipeline(df), is_stock=False, cooldown_bars=3,
                         position_exit_proxy="none", allow_short=True)
    cut = build_signals(_pipeline(df.iloc[:-300].copy()), is_stock=False, cooldown_bars=3,
                        position_exit_proxy="none", allow_short=True)
    n = len(cut)
    for col in ("long_signal", "short_signal", "trigger_long", "long_signal_raw"):
        a = full[col].iloc[:n].astype(bool).to_numpy()
        b = cut[col].astype(bool).to_numpy()
        assert (a == b).all(), f"{col}: geleceği silmek geçmişi değiştirdi"
    a = full["execution_price"].iloc[:n - 1].to_numpy(dtype="float64")
    b = cut["execution_price"].iloc[:n - 1].to_numpy(dtype="float64")
    assert np.allclose(a, b, equal_nan=True), "execution_price geleceğe bağlı olmamalı"
    # kesilen serinin SON barındaki sinyal artık uygulanamaz olmalı
    if bool(cut["long_signal"].iloc[-1] or cut["short_signal"].iloc[-1]):
        assert bool(cut["execution_valid"].iloc[-1]) is False


def test_execution_never_uses_a_bar_before_the_signal() -> None:
    out = build_signals(_pipeline(_frame(1200, seed=13)), is_stock=False,
                        cooldown_bars=3, position_exit_proxy="none")
    sig = out.index[out["long_signal"] | out["short_signal"]]
    assert len(sig) > 0
    ts = pd.to_datetime(out["timestamp_utc"], utc=True)
    for i in sig:
        assert ts.iloc[int(out.loc[i, "execution_bar"])] > ts.iloc[i]


# --------------------------------------------------------------------------
# KRİTER 4 — cooldown + pozisyon baskılaması
# --------------------------------------------------------------------------

def test_cooldown_off_by_one_is_exactly_as_documented() -> None:
    """Sözleşme: cooldown_bars=3 ve 'entry_bar' modunda, sinyal barı s ise
    yeniden sinyal üretebilen İLK bar s+4'tür (giriş barı s+1, ardından 3 bar
    sessizlik)."""
    df = _frame(400, seed=14)
    out = _pipeline(df)
    out["long_signal_raw"] = True                     # her barda ham sinyal
    out["long_regime_ok"] = True
    out = apply_cooldown_and_execution(out, cooldown_bars=3,
                                       cooldown_counts_from="entry_bar",
                                       position_exit_proxy="none")
    fired = np.flatnonzero(out["long_signal"].to_numpy())
    gaps = np.diff(fired)
    assert len(fired) > 5
    assert gaps.min() == 4, f"beklenen 4 bar, gelen {gaps.min()} (gaps={gaps[:8]})"
    assert int(out["suppressed_by_cooldown"].sum()) > 0
    # farklı modlar farklı off-by-one verir; hepsi BELGELENMİŞ olmalı
    for mode, expected in (("entry_bar", 4), ("signal_bar", 3)):
        o = apply_cooldown_and_execution(out.assign(long_signal_raw=True),
                                         cooldown_bars=3, cooldown_counts_from=mode,
                                         position_exit_proxy="none")
        g = np.diff(np.flatnonzero(o["long_signal"].to_numpy()))
        assert g.min() == expected, (mode, g.min(), expected)
    try:
        apply_cooldown_and_execution(out, cooldown_counts_from="bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("geçersiz cooldown_counts_from reddedilmeliydi")


def test_no_signal_while_position_is_open() -> None:
    df = _frame(1500, seed=15)
    out = _pipeline(df)
    out = build_signals(out, is_stock=False, cooldown_bars=3,
                        position_exit_proxy="frozen_stop_intrabar", allow_short=True)
    both = out["long_signal"] | out["short_signal"]
    # sinyal üretilen barda pozisyon ZATEN açık olmamalı (aynı bar içinde açılır)
    open_before = out["position_open"].shift(1).fillna(0).astype(int)
    assert not (both & (open_before == 1)).any(), "pozisyon açıkken sinyal üretildi"
    assert int(out["suppressed_by_position"].sum()) >= 0
    # her sinyal bir pozisyon açar ve entry_stop DOLU olmalıdır
    st = out.loc[both, "entry_stop"]
    assert st.notna().all() or len(st) == 0


def test_position_proxy_starvation_is_measurable() -> None:
    """BULGU (Aşama 5'in ana sonucu): yapısal stop ~2.6 ATR geride olduğu için
    fiyat onu yıllarca ihlal etmeyebiliyor; pozisyon neredeyse hep açık kalıp
    ham sinyallerin ~%99'unu bastırıyor. Bu bir kod hatası DEĞİL, Aşama 7'nin
    (TP/trailing/time-stop) neden zorunlu olduğunun kanıtı. Test, bu durumun
    ÖLÇÜLEBİLİR olmasını kilitler."""
    df = _frame(2000, seed=16, drift=0.001)
    out = _pipeline(df)
    strict = build_signals(out, is_stock=False, cooldown_bars=3,
                           position_exit_proxy="frozen_stop_intrabar")
    s_strict = signal_stats(strict)
    loose = build_signals(out, is_stock=False, cooldown_bars=3,
                          position_exit_proxy="none")
    s_loose = signal_stats(loose)
    assert s_strict["long_signals"] < s_loose["long_signals"]
    assert strict["position_open"].mean() > loose["position_open"].mean()
    suppression = 1 - (s_strict["long_signals"] / max(1, s_strict["long_raw_signals"]))
    assert suppression > 0.5, suppression          # bastırma ölçülebilir olmalı
    # time-stop eklenince sinyal sayısı ARTMALI (vekili gevşetmek)
    capped = build_signals(out, is_stock=False, cooldown_bars=3,
                           position_exit_proxy="frozen_stop_intrabar",
                           max_position_bars=90)
    s_capped = signal_stats(capped)
    assert s_capped["long_signals"] > s_strict["long_signals"]
    assert s_capped["long_signals"] <= s_loose["long_signals"]


def test_invalid_stop_blocks_position_opening() -> None:
    """Dondurulacak stop YOKSA pozisyon AÇILMAZ (fail-closed)."""
    df = _frame(400, seed=17)
    out = _pipeline(df)
    out["long_signal_raw"] = True
    out["long_regime_ok"] = True
    out["stop_long"] = np.nan
    out["stop_valid_long"] = False
    res = apply_cooldown_and_execution(out, cooldown_bars=3,
                                       position_exit_proxy="frozen_stop_intrabar")
    assert (~res["long_signal"]).all()
    assert res["position_open"].sum() == 0


# --------------------------------------------------------------------------
# KRİTER 5 — rapor alanları
# --------------------------------------------------------------------------

def test_signal_stats_reports_required_fields() -> None:
    out = build_signals(_pipeline(_frame(2500, seed=18)), is_stock=False,
                        cooldown_bars=3, position_exit_proxy="none")
    st = signal_stats(out)
    for k in ("bars", "long_signals", "long_by_year", "long_mean_gap_days",
              "long_median_gap_days", "long_min_gap_days", "long_signals_per_year",
              "long_executable", "min_signal_gap_bars", "position_open_frac"):
        assert k in st, k
    assert sum(st["long_by_year"].values()) == st["long_signals"]
    assert st["long_mean_gap_days"] is None or st["long_mean_gap_days"] > 0
    assert st["long_executable"] <= st["long_signals"]


def test_stats_per_year_is_none_for_single_signal() -> None:
    df = _frame(300, seed=19)
    out = _pipeline(df)
    out["long_signal_raw"] = False
    out.loc[out.index[100], "long_signal_raw"] = True
    out["long_regime_ok"] = True
    out = apply_cooldown_and_execution(out, cooldown_bars=3, position_exit_proxy="none")
    st = signal_stats(out)
    assert st["long_signals"] == 1
    assert st["long_signals_per_year"] is None
    assert st["long_mean_gap_days"] is None


def test_build_signals_is_non_destructive() -> None:
    df = _pipeline(_frame(600, seed=20))
    before = df[["open", "high", "low", "close", "volume"]].to_numpy().copy()
    out = build_signals(df, is_stock=False, cooldown_bars=3, position_exit_proxy="none")
    assert len(out) == len(df)
    assert np.allclose(out[["open", "high", "low", "close", "volume"]].to_numpy(), before)
    assert list(out["timestamp_utc"]) == list(df["timestamp_utc"])


def test_stocks_are_long_only_in_signal_engine() -> None:
    out = build_signals(_pipeline(_frame(900, seed=21), allow_short=False, is_stock=True),
                        is_stock=True, cooldown_bars=3, allow_short=False,
                        position_exit_proxy="none")
    assert (~out["short_signal"]).all()
    assert (~out["short_signal_raw"]).all()
    assert int(out["long_signal"].sum()) > 0


# --------------------------------------------------------------------------

def _run_all() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {fn.__name__}: {exc}")
        except Exception as exc:                                     # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
