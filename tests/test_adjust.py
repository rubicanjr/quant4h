"""Tests for the roll / data-outage adjustment module (KARAR 2 & KARAR 3).

The user's hard rules, each one pinned by a test:
  * no bar is DELETED, no bar is FABRICATED
  * the outage window is marked non-tradable (not repaired)
  * a return that jumps the outage is corrected (invalidated), never trusted
  * the SILVER 2026-02-02 -22% bar stays in the data, permanently flagged
  * raw prices are never modified (close_raw is pristine)

Run: python3 -W ignore tests/test_adjust.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from quant4h.config import DEFAULT_ASSETS, UTC, AssetSpec  # noqa: E402
from quant4h.data import schema  # noqa: E402
from quant4h.data.adjust import ADDED_COLUMNS, adjust_asset  # noqa: E402

NOW = pd.Timestamp("2026-09-30 00:00:00", tz=UTC)


def _synthetic(spec_key: str = "GOLD", n_hours: int = 24 * 40,
               outage_at: int | None = None, outage_hours: int = 75,
               roll_at: int | None = None, seed: int = 3) -> pd.DataFrame:
    """Synthetic 1h NY feed -> 4H frame, with an optional outage and/or roll."""
    from quant4h.data.resample import resample_ohlcv
    spec = DEFAULT_ASSETS[spec_key]
    idx = pd.date_range("2024-05-01 00:00:00", periods=n_hours, freq="h",
                        tz="America/New_York")
    rng = np.random.default_rng(seed)
    close = 2000.0 * np.exp(np.cumsum(rng.normal(0, 0.0008, n_hours)))
    if roll_at is not None:                    # a genuine, persistent level shift
        close[roll_at:] *= 0.985
    open_ = np.r_[close[0], close[:-1]]
    high = np.fmax(open_, close) * (1 + rng.uniform(0, 0.0004, n_hours))
    low = np.fmin(open_, close) * (1 - rng.uniform(0, 0.0004, n_hours))
    src = pd.DataFrame({"symbol": spec.source_ticker, "timestamp_utc": idx.tz_convert(UTC),
                        "open": open_, "high": high, "low": low, "close": close,
                        "volume": rng.uniform(500, 5000, n_hours)})
    if outage_at is not None:                  # cut a hole in the calendar
        src = src.drop(src.index[outage_at:outage_at + outage_hours])
    return resample_ohlcv(src, "4h", spec, min_bars_fill=1, now=NOW)


# --------------------------------------------------------------------------
# Rule 1 & 2: never delete, never fabricate
# --------------------------------------------------------------------------

def test_row_count_is_never_changed() -> None:
    spec = DEFAULT_ASSETS["GOLD"]
    for kwargs in ({}, {"outage_at": 200}, {"roll_at": 300}, {"outage_at": 200, "roll_at": 500}):
        frame = _synthetic(**kwargs)
        adj, rep, log = adjust_asset(frame, spec, "4h", src_timeframe="1h", now=NOW)
        assert len(adj) == len(frame), kwargs
        assert rep.rows_in == rep.rows_out == len(frame)
        assert rep.bars_deleted == 0 and rep.bars_added == 0
        # timestamps must be IDENTICAL - nothing inserted, nothing removed
        assert list(adj["timestamp_utc"]) == list(frame["timestamp_utc"])


def test_no_price_is_fabricated() -> None:
    """close_raw must be byte-identical to the input close, NaN pattern included."""
    spec = DEFAULT_ASSETS["GOLD"]
    frame = _synthetic(outage_at=200)
    adj, _, _ = adjust_asset(frame, spec, "4h", src_timeframe="1h", now=NOW)
    assert np.allclose(adj["close_raw"].to_numpy(), frame["close"].to_numpy(), equal_nan=True)
    assert np.allclose(adj["open"].to_numpy(), frame["open"].to_numpy(), equal_nan=True)
    assert np.allclose(adj["high"].to_numpy(), frame["high"].to_numpy(), equal_nan=True)
    assert np.allclose(adj["low"].to_numpy(), frame["low"].to_numpy(), equal_nan=True)
    # with no roll correction applied, close_adjusted must equal close_raw
    assert np.allclose(adj["close_adjusted"].to_numpy(), adj["close_raw"].to_numpy())
    assert (adj["adjustment_factor"] == 1.0).all()


def test_all_documented_columns_are_added() -> None:
    spec = DEFAULT_ASSETS["GOLD"]
    adj, _, _ = adjust_asset(_synthetic(), spec, "4h", src_timeframe="1h", now=NOW)
    missing = [c for c in ADDED_COLUMNS if c not in adj.columns]
    assert not missing, missing
    # hisse-ozel kolonlar adjust_asset'ten BEKLENMEZ (ayri yardimcilar uretir)
    from quant4h.data.adjust import STOCK_COLUMNS, flag_corporate_actions, flag_price_limit_bars
    assert not (set(STOCK_COLUMNS) <= set(adj.columns))
    adj2 = flag_price_limit_bars(flag_corporate_actions(adj))
    missing2 = [c for c in STOCK_COLUMNS if c not in adj2.columns]
    assert not missing2, missing2


# --------------------------------------------------------------------------
# Rule 3: the outage is marked non-tradable, not repaired
# --------------------------------------------------------------------------

def test_outage_window_is_marked_non_tradable() -> None:
    spec = DEFAULT_ASSETS["GOLD"]
    frame = _synthetic(outage_at=300, outage_hours=75)
    adj, rep, _ = adjust_asset(frame, spec, "4h", src_timeframe="1h", now=NOW)
    assert len(rep.outage_windows) >= 1, "the injected 75h hole must be detected"
    w = rep.outage_windows[0]
    assert w["missing_hours"] >= 72, w
    # every bar inside the window is non-tradable, and the window is NOT filled
    inside = adj[(adj["timestamp_utc"] >= pd.Timestamp(w["missing_from_utc"])) &
                 (adj["timestamp_utc"] <= pd.Timestamp(w["missing_to_utc"]))]
    assert len(inside) == 0, "no bar may be fabricated inside the outage window"
    assert adj.loc[adj["outage_window"], "non_tradable"].all()
    # the resumption bar is flagged too: its level may have jumped
    resumed = adj[adj["outage_resumption"]]
    assert len(resumed) >= 1
    assert resumed["non_tradable"].all()
    assert "outage_resumption" in resumed["non_tradable_reason"].iloc[0]


def test_normal_session_gaps_are_not_outages() -> None:
    """A weekend must not be reported as a data outage."""
    spec = DEFAULT_ASSETS["GOLD"]
    adj, rep, _ = adjust_asset(_synthetic(n_hours=24 * 20), spec, "4h",
                               src_timeframe="1h", now=NOW)
    assert rep.n_gap_anomaly <= 1, [w["missing_hours"] for w in rep.outage_windows]


# --------------------------------------------------------------------------
# Rule 4: the gap-jumping return is corrected (invalidated), never trusted
# --------------------------------------------------------------------------

def test_return_across_outage_is_invalidated() -> None:
    """The outage must hide a REAL level difference, otherwise the test proves
    nothing (first version failed exactly here: the random walk happened to line
    up across the hole, so max_raw == max_valid)."""
    spec = DEFAULT_ASSETS["GOLD"]
    frame = _synthetic(outage_at=300, outage_hours=75)
    # enjekte: kesintiden SONRAKI tum fiyatlar %15 asagi -> -16.5% sahte getiri
    cut = pd.Timestamp("2024-05-16 18:00:00", tz=UTC)
    assert (frame["timestamp_utc"] >= cut).any(), "kesinti sonrasi bar bulunamadi"
    for col in ("open", "high", "low", "close"):
        m = frame["timestamp_utc"] >= cut
        frame.loc[m, col] = frame.loc[m, col] * 0.85
    adj, rep, _ = adjust_asset(frame, spec, "4h", src_timeframe="1h", now=NOW)
    resumed = adj[adj["outage_resumption"]]
    assert len(resumed) >= 1
    assert (~resumed["return_valid"]).all()
    assert resumed["close_to_close_return"].isna().all()
    # the RAW jump is much larger than anything the valid series contains
    assert rep.max_raw_abs_return > 0.10, rep.max_raw_abs_return
    assert rep.max_valid_abs_return < 0.02, rep.max_valid_abs_return
    assert rep.max_raw_abs_return > rep.max_valid_abs_return
    # ...and the raw jump is still visible in close_raw (nothing was erased)
    prev_close = float(adj["close_raw"].iloc[adj.index.get_loc(resumed.index[0]) - 1])
    assert abs(np.log(float(resumed["close_raw"].iloc[0]) / prev_close)) > 0.10


def test_returns_on_contiguous_bars_stay_valid() -> None:
    spec = DEFAULT_ASSETS["GOLD"]
    adj, _, _ = adjust_asset(_synthetic(n_hours=24 * 20), spec, "4h",
                             src_timeframe="1h", now=NOW)
    tradable = adj[(~adj["non_tradable"]) & adj["close_to_close_return"].notna()]
    assert len(tradable) > 50
    expected = np.log(tradable["close_raw"] /
                      adj["close_raw"].shift(1).loc[tradable.index])
    assert np.allclose(tradable["close_to_close_return"].to_numpy(), expected.to_numpy())


# --------------------------------------------------------------------------
# Rule 5: rolls are never fabricated; spot/index can never have a roll
# --------------------------------------------------------------------------

def test_spot_and_index_never_get_a_roll() -> None:
    """BTC (spot) and XU030 (index) cannot roll. A big genuine move must NOT be
    reclassified as a roll - that was bug: 118 fake rolls on BTC."""
    for key in ("BTC", "BIST30"):
        spec = DEFAULT_ASSETS[key]
        assert spec.requires_adjustment is False
        frame = schema.load_parquet(f"data/interim/{key.lower()}_4h.parquet") \
            if os.path.exists(f"data/interim/{key.lower()}_4h.parquet") else None
        if frame is None:
            continue
        adj, rep, _ = adjust_asset(frame, spec, "4h", src_timeframe=spec.raw_timeframe, now=NOW)
        assert rep.n_roll_event == 0, key
        assert (adj["roll_candidate"] == False).all(), key          # noqa: E712
        assert np.allclose(adj["close_adjusted"].to_numpy(), adj["close_raw"].to_numpy())


def test_persistent_level_shift_is_flagged_but_not_silently_corrected() -> None:
    """DURUST SINIR: bir roll ile gercek bir ekstrem hareket fiyattan AYIRT
    EDILEMEZ. Bu yuzden varsayilan politika FLAG ONLY'ddir; fiyatlar yalnizca
    kullanici ACIKCA isterse (apply_roll_correction=True) duzeltilir."""
    spec = DEFAULT_ASSETS["GOLD"]
    frame = _synthetic(n_hours=24 * 60, roll_at=600)
    adj, rep, _ = adjust_asset(frame, spec, "4h", src_timeframe="1h", now=NOW)
    assert rep.n_roll_candidate >= 1
    assert rep.n_roll_event == 0, "varsayilan: HICBIR fiyat duzeltilmez"
    assert np.allclose(adj["close_adjusted"].to_numpy(), adj["close_raw"].to_numpy())
    assert adj.attrs["roll_correction_applied"] is False
    assert bool(adj["persistent_move"].any())
    # explicit opt-in DOES back-adjust, and keeps the newest prices raw
    adj2, _, _ = adjust_asset(frame, spec, "4h", src_timeframe="1h",
                              apply_roll_correction=True, now=NOW)
    assert adj2.attrs["roll_correction_applied"] is True
    assert int(adj2["roll_event"].sum()) >= 1
    assert not np.allclose(adj2["close_adjusted"].to_numpy(), adj2["close_raw"].to_numpy())
    assert np.allclose(adj2["close_adjusted"].iloc[-1], adj2["close_raw"].iloc[-1])
    r_raw = np.log(adj2["close_raw"] / adj2["close_raw"].shift(1)).abs()
    r_adj = np.log(adj2["close_adjusted"] / adj2["close_adjusted"].shift(1)).abs()
    assert float(r_adj.max()) < float(r_raw.max())


def test_bad_print_heuristic_uses_volume_not_persistence() -> None:
    """Kalıcılık testi bad print'i AYIRT EDEMEZ (print sonrasi seviye kaymis
    gorunur). Ayirt edici sezgi HACIMDIR: izole print dusuk hacimli olur."""
    spec = DEFAULT_ASSETS["GOLD"]
    i = 200

    def _spiked(low_volume: bool) -> pd.DataFrame:
        f = _synthetic(n_hours=24 * 40)
        f.loc[i, "close"] = f.loc[i, "close"] * 1.20
        f.loc[i, "high"] = f.loc[i, "close"]
        f.loc[i + 1, "open"] = f.loc[i, "close"]
        f.loc[i + 1, "high"] = f.loc[i + 1, "open"]
        if low_volume:
            # 4H bar hacmi = 4 kaynak barin TOPLAMI; bu yuzden tek kaynak bara
            # degil, 4H barin kendi hacmine mudahale edilir.
            f.loc[i, "volume"] = 1.0
        return f

    adj, rep, _ = adjust_asset(_spiked(True), spec, "4h", src_timeframe="1h", now=NOW)
    assert rep.n_roll_event == 0                    # fiyat duzeltilmedi
    assert int(adj["big_move_candidate"].sum()) >= 1
    assert int(adj["bad_print_candidate"].sum()) >= 1, \
        "dusuk hacimli buyuk hareket bad print adayi olmali"

    adj2, _, _ = adjust_asset(_spiked(False), spec, "4h", src_timeframe="1h", now=NOW)
    assert int(adj2["big_move_candidate"].sum()) >= 1
    assert int(adj2["bad_print_candidate"].sum()) == 0, \
        "normal hacimli buyuk hareket bad print sayilmamali"


# --------------------------------------------------------------------------
# Rule 6: every mutation is logged
# --------------------------------------------------------------------------

def test_back_adjustment_removes_exactly_the_roll_jump() -> None:
    """Net matematik sozlesmesi: roll p'de ise factor[p-1] = ratio_p,
    factor[p:] = 1.0 ve p-1 -> p arasindaki yapay sicrama adjusted seride YOKTUR."""
    spec = DEFAULT_ASSETS["GOLD"]
    frame = _synthetic(n_hours=24 * 60, roll_at=600)
    adj, _, _ = adjust_asset(frame, spec, "4h", src_timeframe="1h",
                             apply_roll_correction=True, now=NOW)
    pos = int(np.flatnonzero(adj["roll_event"].to_numpy())[0])
    ratio = float(adj["close_raw"].iloc[pos] / adj["close_raw"].iloc[pos - 1])
    factor = adj["adjustment_factor"].to_numpy()
    assert np.isclose(factor[pos - 1], ratio), (factor[pos - 1], ratio)
    assert np.allclose(factor[pos:], 1.0)
    assert np.allclose(factor[:pos], ratio)
    assert np.allclose(adj["close_adjusted"].iloc[-1], adj["close_raw"].iloc[-1])
    r_raw = np.log(adj["close_raw"] / adj["close_raw"].shift(1)).abs()
    r_adj = np.log(adj["close_adjusted"] / adj["close_adjusted"].shift(1)).abs()
    assert float(r_adj.max()) < float(r_raw.max()), (float(r_adj.max()), float(r_raw.max()))


def test_every_step_is_logged() -> None:
    spec = DEFAULT_ASSETS["GOLD"]
    _, _, log = adjust_asset(_synthetic(outage_at=300), spec, "4h",
                             src_timeframe="1h", now=NOW)
    steps = [s["step"] for s in log.to_dict()["steps"]]
    for expected in ("gap_classification", "outage_marking", "non_tradable_marking",
                     "return_invalidation", "big_move_classification", "back_adjustment"):
        assert expected in steps, (expected, steps)
    # no step may report a row-count change
    assert all(s["rows_before"] == s["rows_after"] for s in log.to_dict()["steps"])


# --------------------------------------------------------------------------
# The real, documented event: SILVER 2026-02-02 -22%
# --------------------------------------------------------------------------

def test_real_silver_2026_02_02_event_is_flagged_and_preserved() -> None:
    """KARAR 3 verdict, pinned against the REAL cached dataset:
    the -22% bar is neither a roll nor a bad print - it jumps a 75h data outage.
    It must stay in the file, flagged, with its return invalidated."""
    path = "data/interim/silver_4h.parquet"
    if not os.path.exists(path):
        print("SKIP  (silver_4h.parquet yok - once run_data_qc.py calistirin)")
        return
    spec = DEFAULT_ASSETS["SILVER"]
    frame = schema.load_parquet(path)
    adj, rep, _ = adjust_asset(frame, spec, "4h", src_timeframe="1h", now=NOW)

    assert rep.rows_in == rep.rows_out == len(frame)
    bar = adj[adj["timestamp_utc"] == pd.Timestamp("2026-02-02 15:00:00", tz=UTC)]
    assert len(bar) == 1, "the -22% bar must NOT be deleted"
    row = bar.iloc[0]
    assert float(row["close_raw"]) < 80.0                       # the raw price is intact
    assert bool(row["gap_anomaly"]) is True                     # it jumps a calendar hole
    assert bool(row["return_valid"]) is False                   # its return is invalidated
    assert pd.isna(row["close_to_close_return"])                # no fake -22% in the series
    assert bool(row["non_tradable"]) is True
    assert "outage_resumption" in str(row["non_tradable_reason"])
    assert bool(row["roll_candidate"]) is False                 # NOT a roll
    assert bool(row["roll_event"]) is False
    # the outage itself is documented with its exact bounds
    win = [w for w in rep.outage_windows if w["resumed_bar_utc"].startswith("2026-02-02")]
    assert win, rep.outage_windows
    assert win[0]["missing_from_utc"].startswith("2026-01-30")
    assert win[0]["missing_hours"] >= 70
    assert abs(win[0]["return_across_gap_pct"]) > 15.0


def test_real_gold_outage_matches_silver_outage() -> None:
    """Both metals show the SAME outage window -> a Yahoo feed problem, not a
    market event. Recorded as diagnosis 3 in PROGRESS.md."""
    if not (os.path.exists("data/interim/gold_4h.parquet")
            and os.path.exists("data/interim/silver_4h.parquet")):
        print("SKIP  (interim parquet yok)")
        return
    wins = {}
    for key in ("GOLD", "SILVER"):
        spec = DEFAULT_ASSETS[key]
        frame = schema.load_parquet(f"data/interim/{key.lower()}_4h.parquet")
        _, rep, _ = adjust_asset(frame, spec, "4h", src_timeframe="1h", now=NOW)
        wins[key] = {(w["missing_from_utc"][:13], w["resumed_bar_utc"][:13])
                     for w in rep.outage_windows}
    shared = wins["GOLD"] & wins["SILVER"]
    assert ("2026-01-30 15", "2026-02-02 15") in {(a, b) for a, b in shared} or \
           any(a.startswith("2026-01-30") and b.startswith("2026-02-02") for a, b in shared), shared
    assert len(shared) >= 5, f"most outage windows should be common: {len(shared)}"


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
