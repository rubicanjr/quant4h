"""Unit tests for the resampler and the QC battery.

Run: python -m pytest tests/ -q   (or)   python tests/test_resample_qc.py
These tests are synthetic and deterministic: no network, no data files.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from quant4h.config import DEFAULT_ASSETS, UTC, AssetSpec, CostModel  # noqa: E402
from quant4h.data import qc, schema  # noqa: E402
from quant4h.data.resample import (calendar_info, resample_ohlcv,  # noqa: E402
                                   session_date, timeframe_minutes)

NOW = pd.Timestamp("2024-06-03 00:00:00", tz=UTC)   # a Monday, safely in the past


def _hourly(start: str, n: int, tz=UTC, price0: float = 100.0, vol: float = 10.0,
            symbol: str = "TEST") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="h", tz=tz)
    rng = np.random.default_rng(7)
    close = price0 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    open_ = np.r_[price0, close[:-1]]
    high = np.fmax(open_, close) * (1 + rng.uniform(0, 0.002, n))
    low = np.fmin(open_, close) * (1 - rng.uniform(0, 0.002, n))
    return pd.DataFrame({
        "symbol": symbol, "timestamp_utc": idx, "open": open_, "high": high,
        "low": low, "close": close, "volume": vol + rng.uniform(0, 5, n),
    })


def test_timeframe_minutes() -> None:
    assert timeframe_minutes("4h") == 240
    assert timeframe_minutes("1h") == 60
    try:
        timeframe_minutes("3h")
    except ValueError:
        pass
    else:
        raise AssertionError("3h must be rejected")


def test_btc_like_4h_aggregation() -> None:
    spec = DEFAULT_ASSETS["BTC"]
    src = _hourly("2024-05-01 00:00:00", 24 * 10)
    out = resample_ohlcv(src, "4h", spec, drop_partial=True, now=NOW)
    assert len(out) == 60, len(out)
    # OHLC identities against the source
    for i in range(len(out)):
        blk = src.iloc[i * 4:(i + 1) * 4]
        row = out.iloc[i]
        assert np.isclose(row["open"], blk["open"].iloc[0])
        assert np.isclose(row["high"], blk["high"].max())
        assert np.isclose(row["low"], blk["low"].min())
        assert np.isclose(row["close"], blk["close"].iloc[-1])
        assert np.isclose(row["volume"], blk["volume"].sum())
        assert row["n_src_bars"] == 4
    # UTC awareness + monotonic + no duplicates
    assert str(out["timestamp_utc"].dtype).endswith("UTC]"), out["timestamp_utc"].dtype
    assert out["timestamp_utc"].is_monotonic_increasing
    assert not out["timestamp_utc"].duplicated().any()
    # every bar on the 00/04/08/12/16/20 UTC grid
    assert set(out["timestamp_utc"].dt.hour.unique()) <= {0, 4, 8, 12, 16, 20}


def test_partial_bar_is_dropped() -> None:
    """The single most important look-ahead guard in the pipeline."""
    spec = DEFAULT_ASSETS["BTC"]
    now = pd.Timestamp("2024-05-11 02:00:00", tz=UTC)       # mid-bin
    src = _hourly("2024-05-01 00:00:00", 24 * 10 + 4)       # last bin still forming
    out = resample_ohlcv(src, "4h", spec, drop_partial=True, now=now)
    assert len(out) == 60, len(out)
    assert out["timestamp_utc"].iloc[-1] + pd.Timedelta(hours=4) <= now
    keep = resample_ohlcv(src, "4h", spec, drop_partial=False, now=now)
    assert len(keep) == 61, len(keep)
    assert keep["timestamp_utc"].iloc[-1] + pd.Timedelta(hours=4) > now


def test_metals_session_grid_is_dst_stable() -> None:
    """Local-anchored grid => identical LOCAL bar hours across a DST flip."""
    spec = DEFAULT_ASSETS["GOLD"]
    assert spec.bar_anchor_mode == "local"
    winter = _hourly("2024-01-08 00:00:00", 24 * 5, tz="America/New_York")
    summer = _hourly("2024-07-08 00:00:00", 24 * 5, tz="America/New_York")
    a = resample_ohlcv(winter, "4h", spec, now=pd.Timestamp("2024-01-15", tz=UTC))
    b = resample_ohlcv(summer, "4h", spec, now=pd.Timestamp("2024-07-15", tz=UTC))
    assert len(a) and len(b), (len(a), len(b))
    la = sorted(int(x) for x in a["timestamp_utc"].dt.tz_convert("America/New_York").dt.hour.unique())
    lb = sorted(int(x) for x in b["timestamp_utc"].dt.tz_convert("America/New_York").dt.hour.unique())
    assert la == lb == [2, 6, 10, 14, 18, 22], (la, lb)
    ua = {int(x) for x in a["timestamp_utc"].dt.hour.unique()}
    ub = {int(x) for x in b["timestamp_utc"].dt.hour.unique()}
    assert ua != ub, (sorted(ua), sorted(ub))
    # every full bin holds exactly 4 hourly bars; only the first/last bin of the
    # synthetic window is clipped by the window edges.
    for frame in (a, b):
        full = (frame["n_src_bars"] == 4).mean()
        assert full >= 0.90, full
    # Overnight session attribution. A bar belongs to the session it OPENS in,
    # so anything strictly before the 18:00 anchor rolls to the previous date:
    #   2024-01-08 19:00 -> session 2024-01-08 (evening leg)
    #   2024-01-09 01:00 -> session 2024-01-08 (overnight leg)
    #   2024-01-09 17:00 -> session 2024-01-08 (last hour before the new open)
    #   2024-01-09 18:30 -> session 2024-01-09 (new session already open)
    sess = session_date(pd.DatetimeIndex(pd.to_datetime(
        ["2024-01-08 19:00", "2024-01-09 01:00", "2024-01-09 17:00",
         "2024-01-09 18:30"])), spec)
    assert [str(d.date()) for d in sess] == [
        "2024-01-08", "2024-01-08", "2024-01-08", "2024-01-09"]


def test_bist_local_anchor() -> None:
    """BIST30 uses an Istanbul-local anchor (Turkey = permanent UTC+3)."""
    spec = DEFAULT_ASSETS["BIST30"]
    assert spec.bar_anchor_mode == "local"
    # 09:30-18:00 local session, hourly bars, 10 trading days
    stamps, rows = [], []
    rng = np.random.default_rng(3)
    px = 10000.0
    for d in pd.bdate_range("2024-05-06", periods=10, tz="Europe/Istanbul"):
        for hh, mm in [(9, 30), (10, 30), (11, 30), (12, 30), (13, 30),
                       (14, 30), (15, 30), (16, 30), (17, 30)]:
            stamps.append(d.replace(hour=hh, minute=mm))
            o = px
            px *= float(np.exp(rng.normal(0, 0.003)))
            rows.append((o, max(o, px) * 1.0002, min(o, px) * 0.9998, px, 0.0))
    src = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    src.insert(0, "timestamp_utc", pd.DatetimeIndex(stamps).tz_convert(UTC))
    src.insert(0, "symbol", "XU030_INDEX")
    out = resample_ohlcv(src, "4h", spec, now=NOW)
    assert len(out) > 0
    local_hours = {int(x) for x in out["timestamp_utc"].dt.tz_convert(
        "Europe/Istanbul").dt.hour.unique()}
    # grid 10:00 Istanbul lokal. spec.min_source_bars_per_target=4 oldugu icin
    # yalnizca TAM barlar uretilir: 10-14 ve 14-18 lokal. 06-10 bin'i sadece
    # 09:30 acilis ani printini tasidigi (n_src=1) ve anchor olamadigi icin
    # uretilmez -> aksi halde k=3 fraktal HICBIR swing'i onaylayamiyordu.
    assert local_hours == {10, 14}, local_hours
    # seans basina bar sayisi TEKDÜZE olmali (H4'un asil belirtisi buydu)
    per = out.groupby("session_date").size()
    assert int(per.median()) == 2, per.value_counts().to_dict()
    assert per.min() >= 1
    # KARAR 1: volume_required=False -> sifir hacim ERROR degil WARN'dur,
    # ama uyari metni mutlaka raporda gorunur (sessizce yutulmaz).
    rep = qc.qc_asset(out, spec, "4h", source_df=src, min_rows=10)
    errs = [f.message for f in rep.findings if f.severity == "ERROR"]
    warns = [f.message for f in rep.findings if f.severity == "WARN"]
    assert not any("volume" in m for m in errs), errs
    assert any("volume is zero on every bar" in m for m in warns), warns
    assert any("volume" in m.lower() for m in warns)


def test_qc_detects_injected_defects() -> None:
    spec = DEFAULT_ASSETS["BTC"]
    clean = _hourly("2024-05-01 00:00:00", 24 * 90)
    good = resample_ohlcv(clean, "4h", spec, now=NOW)
    rep = qc.qc_asset(good, spec, "4h", source_df=clean, min_rows=100)
    assert rep.n_error == 0, [f.message for f in rep.findings if f.severity == "ERROR"]

    bad = good.copy()
    bad.loc[bad.index[5], "high"] = bad.loc[bad.index[5], "low"] - 1      # envelope break
    bad.loc[bad.index[9], "close"] = -3.0                                  # non-positive
    bad = pd.concat([bad, bad.iloc[[20]]], ignore_index=True)              # duplicate ts
    bad = bad.sort_values("timestamp_utc").reset_index(drop=True)
    rep2 = qc.qc_asset(bad, spec, "4h", source_df=clean, min_rows=100)
    checks = {f.check for f in rep2.findings if f.severity == "ERROR"}
    assert {"ohlc", "timestamp"} <= checks, checks
    assert rep2.verdict == "RED" and not rep2.usable_for_modelling


def test_qc_detects_spike_and_gaps() -> None:
    spec = DEFAULT_ASSETS["BTC"]
    src = _hourly("2024-05-01 00:00:00", 24 * 60)
    # 240 saatlik delik = 60 4H bar; tolerans 13 bar oldugu icin ANOMALI sayilir
    src = src.drop(src.index[100:340])
    # NOT: 'now' verilmezse drop_partial tum barlari 'gelecek' sayip dusurur.
    out = resample_ohlcv(src, "4h", spec, now=pd.Timestamp("2024-08-01", tz=UTC))
    assert len(out) > 100, len(out)
    # Spike'i 4H seviyesinde enjekte et: kaynak seviyesinde yapilan bir spike
    # bar'ın ORTASINA denk gelirse bar kapanisina hic yansimaz. OHLC zarfi
    # gecerli kalacak sekilde close/high (ve sonraki barin open/high) carpilir.
    i = 120
    prev_close = float(out.loc[i - 1, "close"])
    out.loc[i, "close"] = prev_close * 3.0                       # +110%
    out.loc[i, "high"] = max(float(out.loc[i, "high"]), float(out.loc[i, "close"]))
    out.loc[i + 1, "open"] = float(out.loc[i, "close"])
    out.loc[i + 1, "high"] = max(float(out.loc[i + 1, "high"]), float(out.loc[i + 1, "open"]))
    rep = qc.qc_asset(out, spec, "4h", source_df=src, min_rows=50)
    msgs = " ".join(f.message for f in rep.findings)
    assert "gap" in msgs.lower() or "missing" in msgs.lower()
    # enjekte edilen x3 spike BITISIK barlarda -> gercek outlier olarak yakalanmali
    assert rep.stats["outlier_contiguous_count"] >= 1, rep.stats
    # boslugu atlayan bar ise "continuity" olarak AYRICA isaretlenmeli
    assert rep.stats["bars_crossing_data_gap"] >= 1
    assert any(f.check == "continuity" for f in rep.findings)


def test_gap_crossing_return_is_not_treated_as_real_return() -> None:
    """KARAR 3'un kritik bulgusu: SILVER 2026-02-02 '-%22' bari aslinda bir
    VERI KESINTISINI atliyordu (2026-01-30 15:00 -> 2026-02-02 18:00, 75 bar).
    Boyle bir getiri ne roll ne bad printtir; sahtedir ve isaretlenmelidir."""
    spec = DEFAULT_ASSETS["GOLD"]
    src = _hourly("2024-05-01 00:00:00", 24 * 40)
    src = src.drop(src.index[200:440])           # 240 saatlik kesinti (60 4H bar)
    # kesintinin iki ucuna buyuk ama SAHTE bir fiyat farki koy
    src.loc[src.index[199], "close"] *= 1.0
    src.loc[src.index[200], ["open", "high", "low", "close"]] *= 0.78
    out = resample_ohlcv(src, "4h", spec, now=pd.Timestamp("2024-07-01", tz=UTC))
    rep = qc.qc_asset(out, spec, "4h", source_df=src, min_rows=20)
    assert rep.stats["bars_crossing_data_gap"] >= 1
    cont = [f for f in rep.findings if f.check == "continuity"]
    assert cont and cont[0].severity in ("ERROR", "WARN"), [(f.severity, f.message) for f in cont]
    # sahte -%22 getiri "outlier" diye raporlanMAMAli (cunku bitisik degil)
    assert rep.stats["outlier_contiguous_count"] == 0, rep.stats


def test_calendar_info() -> None:
    spec = DEFAULT_ASSETS["BTC"]
    src = _hourly("2024-05-01 00:00:00", 24 * 10)
    out = resample_ohlcv(src, "4h", spec, now=NOW)
    ci = calendar_info(out, spec, "4h", src_tf="1h")
    assert ci.bars_total == 60 and ci.bars_per_session_median == 6.0 and ci.thin_bars == 0


def test_schema_roundtrip(tmpdir=None) -> None:
    df = _hourly("2024-05-01 00:00:00", 10)
    c = schema.coerce(df)
    assert list(c.columns)[:7] == ["symbol", "timestamp_utc", "open", "high", "low",
                                   "close", "volume"]
    assert str(c["timestamp_utc"].dtype).endswith("UTC]"), c["timestamp_utc"].dtype




# --------------------------------------------------------------------------
# Regression tests for bugs found while running the real Phase-1 QC
# --------------------------------------------------------------------------

def _bist_source(days: int = 120, symbol: str = "XU030_INDEX") -> pd.DataFrame:
    """Synthetic BIST-like feed: 09:30-17:30 Europe/Istanbul hourly prints,
    weekdays only (so weekends are legitimately absent from the grid)."""
    rng = np.random.default_rng(11)
    stamps, rows = [], []
    px = 10000.0
    for d in pd.bdate_range("2024-01-02", periods=days, tz="Europe/Istanbul"):
        for hh, mm in [(9, 30), (10, 30), (11, 30), (12, 30), (13, 30),
                       (14, 30), (15, 30), (16, 30), (17, 30)]:
            stamps.append(d.replace(hour=hh, minute=mm))
            o = px
            px *= float(np.exp(rng.normal(0, 0.004)))
            rows.append((o, max(o, px) * 1.0003, min(o, px) * 0.9997, px, 0.0))
    src = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    src.insert(0, "timestamp_utc", pd.DatetimeIndex(stamps).tz_convert(UTC))
    src.insert(0, "symbol", symbol)
    return src


def test_local_mode_grid_alignment_is_not_flagged() -> None:
    """Regression: in bar_anchor_mode='local' the UTC hours are 07/11/15, so a
    UTC-based alignment test wrongly flagged 100% of the bars."""
    spec = DEFAULT_ASSETS["BIST30"]
    assert spec.bar_anchor_mode == "local"
    src = _bist_source()
    out = resample_ohlcv(src, "4h", spec, now=pd.Timestamp("2025-06-01", tz=UTC))
    assert len(out) > 100
    # Istanbul kalici UTC+3 (DST yok) + 10:00 lokal grid => barlar 03/07/11 UTC.
    # Bu, 4h UTC gridine (00/04/08) 3 saat faz farkiyla oturur: bilincli tercih,
    # seans butunlugu > faz hizalamasi. Bedeli: BTC ile 4H ortus bar = 0,
    # varliklar arasi korelasyon sadece GUNLUK bazda hesaplanir.
    utc_hours = {int(x) for x in out["timestamp_utc"].dt.hour.unique()}
    assert utc_hours == {7, 11}, utc_hours
    local_hours = {int(x) for x in out["timestamp_utc"].dt.tz_convert(
        "Europe/Istanbul").dt.hour.unique()}
    assert local_hours == {10, 14}, local_hours
    rep = qc.qc_asset(out, spec, "4h", source_df=src, min_rows=10)
    align = [f for f in rep.findings if "aligned to the" in f.message or "NOT aligned" in f.message]
    assert align and align[0].severity == "INFO", [(f.severity, f.message) for f in align]


def test_weekend_gaps_are_not_flagged_as_missing_bars() -> None:
    """Regression: a fixed '>4 bars' gap rule flagged every weekend for a
    2-bars/day exchange session. The threshold is now session-aware."""
    spec = DEFAULT_ASSETS["BIST30"]
    src = _bist_source()
    out = resample_ohlcv(src, "4h", spec, min_bars_fill=None,
                         now=pd.Timestamp("2025-06-01", tz=UTC))
    rep = qc.qc_asset(out, spec, "4h", source_df=src, min_rows=10)
    gap_findings = [f for f in rep.findings if f.check == "completeness" and "gaps larger" in f.message]
    assert not gap_findings, [f.message for f in gap_findings]
    # 10:00 lokal grid + day_start 05:00 + min_src=4 => seans basina 2 TAM bar
    assert rep.stats["bars_per_session_observed"] == 2.0
    # esik = max(16, ceil(3*5)+1) = 16 bar; hafta sonu (3-6 bar) ve 3-4 gunluk
    # resmi/dini tatil (6-12 bar) artik YANLIS alarm uretmez.
    assert rep.stats["gap_threshold_bars"] == 18.0


def test_all_nan_optional_columns_are_not_reported_populated() -> None:
    """Regression: the canonical schema materialises every optional column, so
    all-NaN / all-zero columns were listed as 'populated'."""
    spec = DEFAULT_ASSETS["BTC"]
    src = _hourly("2024-05-01 00:00:00", 24 * 40)
    out = resample_ohlcv(src, "4h", spec, now=pd.Timestamp("2024-07-01", tz=UTC))
    out["quote_volume"] = np.nan
    out["open_interest"] = 0.0
    rep = qc.qc_asset(out, spec, "4h", source_df=src, min_rows=10)
    assert "quote_volume" not in rep.stats["optional_populated"]
    assert "open_interest" not in rep.stats["optional_populated"]


def test_session_date_uses_explicit_day_start() -> None:
    """H4 regression (final): the session roll point is ``session_day_start_local``,
    an explicit session-calendar decision decoupled from BOTH the bar grid anchor
    and the session open. BIST30 rolls at 05:00 local, so an early-morning bin
    still belongs to the same trading day and bars/session stays uniform."""
    spec = DEFAULT_ASSETS["BIST30"]
    assert spec.session_day_start_local == "05:00"
    sess = session_date(pd.DatetimeIndex(pd.to_datetime(
        ["2024-01-08 05:00", "2024-01-08 06:00", "2024-01-08 10:00",
         "2024-01-08 14:00", "2024-01-09 04:59"])), spec)
    assert [str(d.date()) for d in sess] == [
        "2024-01-08", "2024-01-08", "2024-01-08", "2024-01-08", "2024-01-08"]
    src = _bist_source()
    out = resample_ohlcv(src, "4h", spec, min_bars_fill=None,
                         now=pd.Timestamp("2025-06-01", tz=UTC))
    rep = qc.qc_asset(out, spec, "4h", source_df=src, min_rows=10)
    # tekdüze 2 TAM bar/seans -> 'partial session' uyarisi YOK
    assert rep.stats["bars_per_session_median"] == 2.0
    assert rep.stats["bars_per_session_min"] >= 1
    partial = [f for f in rep.findings if f.check == "session" and "partial" in f.message]
    assert not partial, [f.message for f in partial]


def test_normal_session_gaps_are_not_flagged_as_outage() -> None:
    """BIST30'da her gunun ilk bari bir onceki gunun son barindan 4 bar uzaktadir
    ve bu NORMALDIR. Ham 'gap > 1 bar' kurali barlarin %33'unu yanlis sekilde
    'veri kesintisi' sayiyordu; yeni kural seans-beklenen boslugu baz alir."""
    spec = DEFAULT_ASSETS["BIST30"]
    src = _bist_source(90)
    out = resample_ohlcv(src, "4h", spec, min_bars_fill=1,
                         now=pd.Timestamp("2025-06-01", tz=UTC))
    rep = qc.qc_asset(out, spec, "4h", source_df=src, min_rows=10)
    # tatilsiz sentetik seride HIC beklenmedik kesinti olmamali
    assert rep.stats["bars_crossing_data_gap"] == 0, rep.stats
    # ama seans ici normal gece/hafta sonu bosluklari SAYILMALI (bilgi amacli).
    # 90 is gunu => ~89 gece boslugu (tatiller haric)
    assert rep.stats["bars_after_normal_session_gap"] >= 80, rep.stats
    assert not any(f.check == "continuity" and f.severity != "INFO" for f in rep.findings)


def test_continuity_severity_is_systemic_only() -> None:
    """Birkac tatil/kesinti WARN'dur; ERROR ancak feed sistemik bozuksa
    (barlarin >%5'i beklenmedik bosluk atliyorsa) uretilir. Gerekce: exchange
    tatil takvimi kullanilmiyor, yani uzun tatiller yanlis pozitif uretebilir."""
    spec = DEFAULT_ASSETS["BTC"]
    src = _hourly("2024-05-01 00:00:00", 24 * 200)
    # 240 saatlik delik = 60 4H bar >> tolerans (13 bar) -> GERCEK kesinti
    src = src.drop(src.index[400:640])
    out = resample_ohlcv(src, "4h", spec, now=pd.Timestamp("2024-09-01", tz=UTC))
    rep = qc.qc_asset(out, spec, "4h", source_df=src, min_rows=10)
    cont = [f for f in rep.findings if f.check == "continuity"]
    assert cont and cont[0].severity == "WARN", [(f.severity, f.message) for f in cont]
    assert rep.stats["bars_crossing_data_gap"] == 1
    # tolerans SEANS bazlidir ve 24/7 varlikta 2 seanstir (12 bar) + 1
    assert rep.stats["gap_anomaly_tolerance_bars"] == 13.0


def test_front_month_futures_are_gated_until_adjusted() -> None:
    """KARAR 2/3: GC=F ve SI=F adjust pipeline'i calismadan 'model icin uygun'
    sayilmaz; pipeline calistiginda kapi ACILIR (kanit: attrs + return_valid)."""
    from quant4h.data.adjust import adjust_asset
    for key in ("GOLD", "SILVER"):
        spec = DEFAULT_ASSETS[key]
        assert spec.requires_adjustment is True
        # NOT: metallerin grid'i 18:00 NY lokal; kaynak UTC olursa barlar grid'e
        # oturmaz ve QC grid-hiza ERROR'u uretir. Bu yuzden tz=America/New_York.
        src = _hourly("2024-05-01 00:00:00", 24 * 200, tz="America/New_York")
        out = resample_ohlcv(src, "4h", spec, now=pd.Timestamp("2024-09-01", tz=UTC))
        # ONCE: pipeline calismadi -> ERROR + usable=False
        rep = qc.qc_asset(out, spec, "4h", source_df=src, min_rows=10)
        assert not rep.usable_for_modelling, key
        assert rep.stats["adjust_pipeline_ran"] is False
        assert any(f.check == "adjustment" and f.severity == "ERROR" for f in rep.findings), key
        # SONRA: pipeline calisir -> kapi acilir
        adj, _rep_adj, _log = adjust_asset(out, spec, "4h", src_timeframe="1h",
                                           now=pd.Timestamp("2024-09-01", tz=UTC))
        rep2 = qc.qc_asset(adj, spec, "4h", source_df=src, min_rows=10)
        assert rep2.stats["adjust_pipeline_ran"] is True, key
        assert not any(f.check == "adjustment" and f.severity == "ERROR" for f in rep2.findings), key
        assert rep2.usable_for_modelling, key
    # BTC spot icin boyle bir kapi YOKTUR (roll tanim geregi imkansiz)
    assert DEFAULT_ASSETS["BTC"].requires_adjustment is False


def test_metals_session_date_uses_halt_aware_day_start() -> None:
    """Metaller 17:30 NY'da rol olur: 17:00-18:00 gunluk bakim molasi BITEN
    seansa aittir, 18:00 sonrasi YENI seanstir."""
    spec = DEFAULT_ASSETS["GOLD"]
    assert spec.session_day_start_local == "17:30"
    sess = session_date(pd.DatetimeIndex(pd.to_datetime(
        ["2024-01-08 18:00", "2024-01-09 01:00", "2024-01-09 17:00",
         "2024-01-09 17:29", "2024-01-09 17:30", "2024-01-09 18:30"])), spec)
    assert [str(d.date()) for d in sess] == [
        "2024-01-08", "2024-01-08", "2024-01-08",
        "2024-01-08", "2024-01-09", "2024-01-09"]


def test_watch_only_and_volume_not_required_downgrade_blockers() -> None:
    """KARAR 1: BIST30 watch_only + volume_required=False -> hacim ERROR'u
    WARN'a duser, ama yetersiz gecmis yine AMBER olarak isaretlenir."""
    spec = DEFAULT_ASSETS["BIST30"]
    assert spec.mode == "watch_only" and spec.volume_required is False
    src = _bist_source(120)
    out = resample_ohlcv(src, "4h", spec, now=pd.Timestamp("2025-06-01", tz=UTC))
    rep = qc.qc_asset(out, spec, "4h", source_df=src, min_rows=1500)
    assert rep.n_error == 0, [f.message for f in rep.findings if f.severity == "ERROR"]
    assert not rep.usable_for_modelling and not rep.enough_history
    assert rep.verdict.startswith("AMBER")
    assert rep.stats["mode"] == "watch_only"
    msgs = " ".join(f.message for f in rep.findings)
    assert "watch_only" in msgs and "DEVRE DISIDIR" in msgs
    # KARAR 1: spec'e gomulu ZORUNLU caveat'ler (5 adet) raporda AYNEN basilmali
    assert len(spec.caveats) >= 5, len(spec.caveats)
    missing = [c for c in spec.caveats if c not in msgs]
    assert not missing, missing


def test_portfolio_correlation_is_pairwise_complete() -> None:
    """Regression: joining mismatched 4H grids (UTC-anchored BTC vs
    local-anchored BIST) produced an all-NaN matrix and corr=None everywhere."""
    btc_spec, bist_spec = DEFAULT_ASSETS["BTC"], DEFAULT_ASSETS["BIST30"]
    btc = resample_ohlcv(_hourly("2024-01-02 00:00:00", 24 * 150), "4h", btc_spec,
                         now=pd.Timestamp("2024-08-01", tz=UTC))
    bist = resample_ohlcv(_bist_source(150), "4h", bist_spec,
                          now=pd.Timestamp("2024-08-01", tz=UTC))
    rep = qc.qc_portfolio({"BTC": btc, "BIST30": bist}, min_overlap_bars=10)
    assert rep["daily"]["rows"] > 50
    # kanonik anahtar alfabetiktir: sorted({"BTC","BIST30"}) -> BIST30|BTC
    assert rep["daily"]["corr"]["BIST30|BTC"] is not None
    # the 4H view legitimately has (near) zero overlap between a UTC grid and
    # a +2h-offset local grid -> that must be reported, not silently dropped
    assert rep["pairwise"]["BIST30|BTC"]["n"] < 50


def _ny_hourly(start: str, end: str, seed: int = 5, px0: float = 2900.0) -> pd.DataFrame:
    """Synthetic COMEX-like hourly feed in America/New_York, converted to UTC."""
    idx = pd.date_range(start, end, freq="h", tz="America/New_York")
    rng = np.random.default_rng(seed)
    close = px0 * np.exp(np.cumsum(rng.normal(0, 0.001, len(idx))))
    open_ = np.r_[px0, close[:-1]]
    # OHLC zarfi GERCEK verideki gibi korunmali: high >= max(o,c), low <= min(o,c)
    high = np.fmax(open_, close) * (1 + rng.uniform(0, 0.0005, len(idx)))
    low = np.fmin(open_, close) * (1 - rng.uniform(0, 0.0005, len(idx)))
    return pd.DataFrame({
        "symbol": "GC=F", "timestamp_utc": idx.tz_convert(UTC),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.uniform(100, 500, len(idx)),
    })


def test_dst_transition_produces_no_duplicate_or_crash() -> None:
    """Regression: 2025-03-09 02:00 America/New_York does not exist. The
    local-naive grid still emits that bin, which used to crash tz_localize and
    can otherwise create a duplicate UTC timestamp (02:00 shifted == 03:00 EDT).
    Real GOLD/SILVER data spans this date, so the tests must too."""
    spec = DEFAULT_ASSETS["GOLD"]

    spring = _ny_hourly("2025-03-05", "2025-03-14 23:00:00")
    out = resample_ohlcv(spring, "4h", spec, now=pd.Timestamp("2025-04-01", tz=UTC))
    assert len(out) > 0
    ts = out["timestamp_utc"]
    assert not ts.duplicated().any(), ts[ts.duplicated(keep=False)].tolist()
    assert ts.is_monotonic_increasing
    assert (out["high"] >= out["low"]).all()
    assert (out["high"] >= out[["open", "close"]].max(axis=1) - 1e-9).all()

    autumn = _ny_hourly("2025-10-28", "2025-11-06 23:00:00", seed=6)
    out2 = resample_ohlcv(autumn, "4h", spec, now=pd.Timestamp("2025-12-01", tz=UTC))
    assert len(out2) > 0
    assert not out2["timestamp_utc"].duplicated().any()
    assert out2["timestamp_utc"].is_monotonic_increasing

    # ayni kontrol BIST30 (DST yok) icin de zararsiz olmali
    bist = DEFAULT_ASSETS["BIST30"]
    out3 = resample_ohlcv(_bist_source(60), "4h", bist,
                          min_bars_fill=None,
                          now=pd.Timestamp("2025-06-01", tz=UTC))
    assert not out3["timestamp_utc"].duplicated().any()


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
