"""Tests for the explicit, logged cleaning layer.

Pinned guarantees:
  * deduplication keeps the FIRST occurrence and never reorders prices
  * only NaN / non-positive rows are ever dropped - envelope violations are
    REPAIRED, not deleted
  * repair never moves open/close and never deletes a bar
  * winsorise only FLAGS; values are byte-identical afterwards
  * returns that jump a data outage (return_valid == False) are NOT counted as
    fat tails
  * the still-forming last bar is dropped (look-ahead guard)
  * every step is present in the CleaningLog with correct row counts

Run: python3 -W ignore tests/test_cleaning.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from quant4h.config import UTC  # noqa: E402
from quant4h.data import schema  # noqa: E402
from quant4h.data.cleaning import (CleaningLog, clean_pipeline, dedupe_and_sort,  # noqa: E402
                                   drop_forming_last_bar, drop_invalid_ohlc,
                                   flag_invalid_ohlc, repair_ohlc_envelope,
                                   winsorise_returns)

NOW = pd.Timestamp("2024-06-01 00:00:00", tz=UTC)


def _frame(n: int = 60, start: str = "2024-05-01 00:00:00", seed: int = 1) -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="4h", tz=UTC)
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.fmax(open_, close) * (1 + rng.uniform(0, 0.002, n))
    low = np.fmin(open_, close) * (1 - rng.uniform(0, 0.002, n))
    return schema.coerce(pd.DataFrame({
        "symbol": "TEST", "timestamp_utc": idx, "open": open_, "high": high,
        "low": low, "close": close, "volume": rng.uniform(10, 100, n)}))


# --------------------------------------------------------------------------

def test_dedupe_keeps_first_by_arrival_order() -> None:
    """'first' = ARRIVAL order, not sorted order. The duplicate is placed BEFORE
    the original on purpose: a naive sorted drop_duplicates(keep='first') would
    silently keep the WRONG row."""
    df = _frame(30)
    ts10 = df["timestamp_utc"].iloc[10]
    dup = df.iloc[[10]].copy()
    dup["close"] = 999.0                       # the duplicate carries a WRONG close
    # dup, orijinal satirdan SONRA gelmeli: o zaman 'first' = orijinal olmali.
    messy = pd.concat([df.iloc[15:], df.iloc[:15], dup], ignore_index=True)
    hits = [i for i, t in enumerate(messy["timestamp_utc"]) if t == ts10]
    assert len(hits) == 2, hits
    # ilk gelen ORIJINAL (close != 999), ikinci gelen DUP (close == 999)
    assert float(messy["close"].iloc[hits[0]]) != 999.0
    assert float(messy["close"].iloc[hits[1]]) == 999.0
    log = CleaningLog()
    out = dedupe_and_sort(messy, log)
    assert len(out) == 30, len(out)
    assert out["timestamp_utc"].is_monotonic_increasing
    assert not out["timestamp_utc"].duplicated().any()
    kept = out[out["timestamp_utc"] == ts10]
    assert float(kept["close"].iloc[0]) != 999.0, "keep='first' (arrival) must win"
    assert log.steps[0]["rows_delta"] == -1
    assert log.steps[0]["duplicated_rows"] == 2
    # keep='last' must do the opposite - the policy is explicit, not accidental
    out_last = dedupe_and_sort(messy, CleaningLog(), keep="last")
    assert float(out_last[out_last["timestamp_utc"] == ts10]["close"].iloc[0]) == 999.0
    # Politika gelis sirasina BAGLIDIR (satir siralamasina degil): ayni iki satir
    # ters sira ile verilince 'last' bu kez ORIJINALI tutmali.
    messy2 = pd.concat([dup, df], ignore_index=True)
    out2 = dedupe_and_sort(messy2, CleaningLog(), keep="last")
    assert float(out2[out2["timestamp_utc"] == ts10]["close"].iloc[0]) != 999.0
    out3 = dedupe_and_sort(messy2, CleaningLog(), keep="first")
    assert float(out3[out3["timestamp_utc"] == ts10]["close"].iloc[0]) == 999.0
    try:
        dedupe_and_sort(messy, CleaningLog(), keep="middle")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid keep must raise")


def test_flag_invalid_ohlc_drops_nothing() -> None:
    df = _frame(20)
    df.loc[df.index[3], "high"] = df.loc[df.index[3], "low"] - 1     # envelope break
    df.loc[df.index[5], "close"] = np.nan                            # NaN
    df.loc[df.index[7], "open"] = -5.0                               # non-positive
    df.loc[df.index[9], "high"] = df.loc[df.index[9], "low"]         # zero range
    df.loc[df.index[9], "open"] = df.loc[df.index[9], "close"]
    log = CleaningLog()
    out = flag_invalid_ohlc(df, log)
    assert len(out) == len(df), "flagging must never drop a row"
    assert out["is_envelope_broken"].sum() >= 1
    assert out["is_nan_ohlc"].sum() == 1
    assert out["is_nonpositive"].sum() == 1
    assert out["is_zero_range"].sum() == 1
    assert log.steps[0]["rows_delta"] == 0


def test_drop_invalid_ohlc_only_drops_unusable_rows() -> None:
    df = _frame(20)
    df.loc[df.index[3], "high"] = df.loc[df.index[3], "low"] - 1     # repairable
    df.loc[df.index[5], "close"] = np.nan                            # unusable
    df.loc[df.index[7], "open"] = -5.0                               # unusable
    log = CleaningLog()
    flagged = flag_invalid_ohlc(df, log)
    out = drop_invalid_ohlc(flagged, log)
    assert len(out) == 18, len(out)
    assert not out["is_nan_ohlc"].any() and not out["is_nonpositive"].any()
    # the envelope-broken bar SURVIVED (it will be repaired, not deleted)
    assert out["is_envelope_broken"].sum() >= 1


def test_repair_envelope_never_moves_open_close_or_deletes() -> None:
    df = _frame(20)
    i = df.index[4]
    df.loc[i, "high"] = df.loc[i, "low"] - 2.0        # badly broken
    before_open, before_close = float(df.loc[i, "open"]), float(df.loc[i, "close"])
    log = CleaningLog()
    out = repair_ohlc_envelope(df, log)
    assert len(out) == len(df)
    assert float(out.loc[i, "open"]) == before_open
    assert float(out.loc[i, "close"]) == before_close
    assert float(out.loc[i, "high"]) >= max(before_open, before_close)
    assert float(out.loc[i, "low"]) <= min(before_open, before_close)
    assert (out["high"] >= out["low"]).all()
    assert (out["high"] >= out[["open", "close"]].max(axis=1)).all()
    assert (out["low"] <= out[["open", "close"]].min(axis=1)).all()
    assert log.steps[0]["rows_delta"] == 0
    assert log.steps[0]["bars_repaired"] >= 1


def test_winsorise_only_flags_and_never_rewrites() -> None:
    df = _frame(200)
    df.loc[df.index[100], "close"] = df.loc[df.index[100], "close"] * 2.5   # fat tail
    raw_close = df["close"].to_numpy().copy()
    log = CleaningLog()
    out = winsorise_returns(df, log, z_thresh=8.0)
    assert np.allclose(out["close"].to_numpy(), raw_close, equal_nan=True)
    assert int(out["return_outlier_flag"].sum()) >= 1
    assert log.steps[0]["rows_delta"] == 0
    assert "VALUES UNCHANGED" in log.steps[0]["detail"]


def test_winsorise_ignores_outage_crossing_returns() -> None:
    """A return that jumps a data outage is NOT a fat tail. If return_valid is
    supplied, such bars must not be flagged as outliers."""
    df = _frame(200)
    i = df.index[120]
    df.loc[i, "close"] = df.loc[i, "close"] * 0.78            # fake -22% jump
    df.loc[i + 1:, "close"] = df.loc[i + 1:, "close"] * 0.78
    df["return_valid"] = True
    df.loc[i, "return_valid"] = False                          # it crosses an outage
    log = CleaningLog()
    out = winsorise_returns(df, log, z_thresh=8.0, valid=df["return_valid"])
    assert bool(out.loc[i, "return_outlier_flag"]) is False
    assert pd.isna(out.loc[i, "return_mad_z"])


def test_winsorise_degenerate_mad_is_safe() -> None:
    df = _frame(30)
    df["close"] = 100.0                                        # zero variance
    log = CleaningLog()
    out = winsorise_returns(df, log)
    assert len(out) == len(df)
    assert (out["return_outlier_flag"] == False).all()         # noqa: E712
    assert "skipped" in log.steps[0]["detail"]


def test_drop_forming_last_bar() -> None:
    df = _frame(30, start="2024-05-01 00:00:00")
    last_open = df["timestamp_utc"].iloc[-1]
    now_mid = last_open + pd.Timedelta(hours=2)                 # bar still forming
    log = CleaningLog()
    out = drop_forming_last_bar(df, log, "4h", now=now_mid)
    assert len(out) == 29
    assert (out["timestamp_utc"] + pd.Timedelta(hours=4) <= now_mid).all()
    log2 = CleaningLog()
    out2 = drop_forming_last_bar(df, log2, "4h", now=NOW)
    assert len(out2) == 30


def test_clean_pipeline_is_complete_logged_and_order_preserving() -> None:
    df = _frame(120)
    df = pd.concat([df, df.iloc[[20]]], ignore_index=True)      # duplicate
    df.loc[df.index[50], "high"] = df.loc[df.index[50], "low"] - 1   # envelope break
    df.loc[df.index[70], "close"] = np.nan                      # unusable
    out, log = clean_pipeline(df, "4h", now=NOW)
    steps = [s["step"] for s in log.to_dict()["steps"]]
    assert steps == ["dedupe_and_sort", "flag_invalid_ohlc", "drop_invalid_ohlc",
                     "repair_ohlc_envelope", "winsorise_returns",
                     "drop_forming_last_bar"], steps
    assert len(out) == 119                                      # 121 - 1 dup - 1 NaN
    assert out["timestamp_utc"].is_monotonic_increasing
    assert (out["high"] >= out[["open", "close"]].max(axis=1)).all()
    assert not out["close"].isna().any()
    # every step reports its own row counts consistently
    for i in range(1, len(log.steps)):
        assert log.steps[i]["rows_before"] == log.steps[i - 1]["rows_after"]
    assert log.dropped == 2


def test_clean_pipeline_never_touches_raw_prices() -> None:
    df = _frame(80)
    before = df["close"].to_numpy().copy()
    out, _ = clean_pipeline(df, "4h", now=NOW)
    merged = out.merge(df[["timestamp_utc", "close"]], on="timestamp_utc",
                       suffixes=("", "_orig"))
    assert np.allclose(merged["close"].to_numpy(), merged["close_orig"].to_numpy())
    assert set(out["timestamp_utc"]).issubset(set(df["timestamp_utc"]))
    assert len(before) == len(df)


def test_clean_pipeline_accepts_adjusted_frame() -> None:
    """The adjust pipeline output (with return_valid / non_tradable) must flow
    through cleaning without losing its flags."""
    df = _frame(80)
    df["return_valid"] = True
    df.loc[df.index[40], "return_valid"] = False
    df["non_tradable"] = False
    df.loc[df.index[40], "non_tradable"] = True
    out, log = clean_pipeline(df, "4h", now=NOW)
    assert "return_valid" in out.columns and "non_tradable" in out.columns
    assert bool(out.loc[out.index[40], "return_valid"]) is False
    assert bool(out.loc[out.index[40], "non_tradable"]) is True
    assert int(out["return_outlier_flag"].sum()) == 0


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
