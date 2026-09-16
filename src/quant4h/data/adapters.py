"""Data adapters.

Only two free, verifiable sources are implemented for the bootstrap study:

* ``binance``  - public REST klines (spot). Deep 4H history, real volume,
  real trades. Best data quality of anything free.
* ``yahoo``    - via ``yfinance``. Used for GC=F / SI=F (1h -> 4h) and for
  XU030.IS (index, 1h -> 4h, volume == 0). Rate limited and *front-month
  only*, so results on metals carry roll-gap risk.

``user_csv`` is the adapter that matters in production: it ingests the
user's own CSV/parquet dump in the canonical schema (see docs/02).

Every adapter returns the canonical schema, UTC-aware, bar OPEN time.
Raw downloads are always persisted untouched under ``data/raw`` first, so
the QC step can be re-run and any transformation audited.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import AssetSpec, CONTEXT_SERIES, UTC
from . import schema

_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"}


class DataFetchError(RuntimeError):
    pass


def _http_json(url: str, timeout: int = 30, retries: int = 4,
               backoff: float = 2.0) -> Any:
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:      # 429/418 -> back off hard
            last = exc
            if exc.code in (418, 429, 500, 502, 503, 504):
                time.sleep(backoff ** attempt * (1.0 + 0.3 * attempt))
                continue
            raise DataFetchError(f"HTTP {exc.code} for {url}") from exc
        except Exception as exc:                    # noqa: BLE001 - network flake
            last = exc
            time.sleep(backoff ** attempt)
    raise DataFetchError(f"failed after {retries} attempts: {url} ({last})")


# --------------------------------------------------------------------------
# Binance (spot klines)
# --------------------------------------------------------------------------

_BINANCE_KLINE_LIMIT = 1000
_INTERVAL_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000,
}


def binance_klines(symbol: str, interval: str = "4h",
                   start_ms: Optional[int] = None,
                   end_ms: Optional[int] = None,
                   base_url: str = "https://api.binance.com",
                   sleep_s: float = 0.25,
                   max_pages: int = 400) -> pd.DataFrame:
    """Paginated spot klines -> canonical frame.

    Binance returns ``[openTime, open, high, low, close, volume, closeTime,
    quoteVolume, trades, takerBuyBase, takerBuyQuote, ignore]``.
    """
    if interval not in _INTERVAL_MS:
        raise ValueError(f"unsupported interval {interval}")
    step = _INTERVAL_MS[interval]
    cursor = int(start_ms or 0)
    end = int(end_ms or time.time() * 1000)
    rows: List[list] = []
    for _ in range(max_pages):
        params = {"symbol": symbol, "interval": interval, "limit": _BINANCE_KLINE_LIMIT}
        if cursor:
            params["startTime"] = cursor
        if end:
            params["endTime"] = end
        batch = _http_json(f"{base_url}/api/v3/klines?{urllib.parse.urlencode(params)}")
        if not batch:
            break
        rows.extend(batch)
        last_open = int(batch[-1][0])
        if len(batch) < _BINANCE_KLINE_LIMIT or last_open + step >= end:
            break
        cursor = last_open + step
        time.sleep(sleep_s)
    if not rows:
        return schema.empty_frame()
    raw = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
    ])
    for col in ("open", "high", "low", "close", "volume", "quote_volume",
                "trades", "taker_buy_base"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw = raw.drop_duplicates(subset="open_time").sort_values("open_time")
    df = pd.DataFrame({
        "symbol": symbol,
        "timestamp_utc": pd.to_datetime(raw["open_time"].astype("int64"), unit="ms", utc=True),
        "open": raw["open"].to_numpy(), "high": raw["high"].to_numpy(),
        "low": raw["low"].to_numpy(), "close": raw["close"].to_numpy(),
        "volume": raw["volume"].to_numpy(),
        "quote_volume": raw["quote_volume"].to_numpy(),
        "trades": raw["trades"].to_numpy(),
        "taker_buy_volume": raw["taker_buy_base"].to_numpy(),
    })
    return schema.coerce(df)


def binance_funding(symbol: str = "BTCUSDT", start_ms: Optional[int] = None,
                    base_url: str = "https://fapi.binance.com",
                    sleep_s: float = 0.25) -> pd.DataFrame:
    """Perpetual funding history (8h). Optional cross-asset feature for BTC."""
    out: List[list] = []
    cursor = int(start_ms or 0)
    for _ in range(200):
        params: Dict[str, Any] = {"symbol": symbol, "limit": 1000}
        if cursor:
            params["startTime"] = cursor
        try:
            batch = _http_json(f"{base_url}/fapi/v1/fundingRate?{urllib.parse.urlencode(params)}",
                               retries=2)
        except DataFetchError:
            break
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 1000:
            break
        cursor = int(batch[-1]["fundingTime"]) + 1
        time.sleep(sleep_s)
    if not out:
        return pd.DataFrame(columns=["symbol", "funding_time_utc", "funding_rate"])
    df = pd.DataFrame(out)
    df["funding_time_utc"] = pd.to_datetime(pd.to_numeric(df["fundingTime"]), unit="ms", utc=True)
    df["funding_rate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    return (df[["symbol", "funding_time_utc", "funding_rate"]]
            .drop_duplicates("funding_time_utc").sort_values("funding_time_utc")
            .reset_index(drop=True))


# --------------------------------------------------------------------------
# Yahoo Finance (via yfinance)
# --------------------------------------------------------------------------

# Yahoo's chart endpoint silently returns an EMPTY payload for
# interval=1h & period=max. The usable intraday windows are hard limits on
# their side: 1m=7d, 2m/5m/15m/30m/90m=60d, 1h=730d, 1d/1wk/1mo=all.
_INTRADAY_MAX_PERIOD = {"1m": "7d", "2m": "60d", "5m": "60d", "15m": "60d",
                        "30m": "60d", "60m": "730d", "1h": "730d"}


def yahoo_ohlcv(ticker: str, interval: str = "1h", period: str = "max",
                start: Optional[str] = None, end: Optional[str] = None,
                retries: int = 4, sleep_s: float = 5.0) -> pd.DataFrame:
    """yfinance download -> canonical frame (timezone normalised to UTC).

    ``auto_adjust=False``: we keep raw prices and expose ``adjclose`` as an
    extra column so that any split/dividend adjustment stays auditable and is
    never silently applied to a futures series.
    """
    import yfinance as yf  # heavy, optional dependency

    if start is None and interval in _INTRADAY_MAX_PERIOD:
        # 'max' is not served for intraday bars; fall back to the deepest window.
        period = _INTRADAY_MAX_PERIOD[interval]
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            kwargs: Dict[str, Any] = dict(
                tickers=ticker, interval=interval, auto_adjust=False,
                progress=False, threads=False, group_by="column",
            )
            if start:
                kwargs.update(start=start, end=end)
            else:
                kwargs["period"] = period
            df = yf.download(**kwargs)
            if df is None or len(df) == 0:
                raise DataFetchError(f"empty response for {ticker} {interval} {period}")
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            break
        except Exception as exc:                     # noqa: BLE001
            last = exc
            time.sleep(sleep_s * (attempt + 1))
    else:
        raise DataFetchError(f"yahoo failed for {ticker}: {last}")

    idx = df.index
    if getattr(idx, "tz", None) is None:             # daily bars are tz-naive
        idx = idx.tz_localize(UTC)
    else:
        idx = idx.tz_convert(UTC)
    cols = {str(c).lower().replace(" ", ""): c for c in df.columns}
    out = pd.DataFrame({
        "symbol": ticker,
        "timestamp_utc": idx,
        "open": pd.to_numeric(df[cols["open"]], errors="coerce").to_numpy(),
        "high": pd.to_numeric(df[cols["high"]], errors="coerce").to_numpy(),
        "low": pd.to_numeric(df[cols["low"]], errors="coerce").to_numpy(),
        "close": pd.to_numeric(df[cols["close"]], errors="coerce").to_numpy(),
        "volume": pd.to_numeric(df[cols.get("volume", "Volume")], errors="coerce")
                  .fillna(0.0).to_numpy() if "volume" in cols else 0.0,
    })
    if "adjclose" in cols:
        out["adjclose"] = pd.to_numeric(df[cols["adjclose"]], errors="coerce").to_numpy()
    out = out.dropna(subset=["open", "high", "low", "close"])
    return schema.coerce(out)


# --------------------------------------------------------------------------
# User supplied CSV / parquet
# --------------------------------------------------------------------------

_ALIASES = {
    "date": "timestamp_utc", "time": "timestamp_utc", "datetime": "timestamp_utc",
    "timestamp": "timestamp_utc", "ts": "timestamp_utc", "open_time": "timestamp_utc",
    "utc_time": "timestamp_utc", "ticker": "symbol", "instrument": "symbol",
    "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "vol": "volume",
    "oi": "open_interest", "funding": "funding_rate", "spread_bps": "spread",
}


def read_user_table(path: str, symbol: Optional[str] = None,
                    timestamp_unit: Optional[str] = None) -> pd.DataFrame:
    """Read a user CSV/parquet in (roughly) the canonical schema.

    Tolerated inputs: column aliases, epoch seconds/milliseconds/nanoseconds,
    tz-naive timestamps (assumed UTC, flagged in the QC report), missing
    ``symbol`` (filled from ``symbol`` argument or file name), missing
    ``volume`` (filled with 0 and flagged as ``has_volume=False``).
    """
    if path.endswith((".parquet", ".pq")):
        raw = pd.read_parquet(path)
    else:
        raw = pd.read_csv(path)
    raw.columns = [str(c).strip() for c in raw.columns]
    renames = {c: _ALIASES[c.strip().lower()] for c in raw.columns
               if c.strip().lower() in _ALIASES}
    raw = raw.rename(columns=renames)
    lower = {c.strip().lower(): c for c in raw.columns}
    for need in ("open", "high", "low", "close"):
        if need not in lower:
            raise DataFetchError(f"{path}: missing required column '{need}'")
    raw = raw.rename(columns={lower[c]: c for c in lower})

    if "timestamp_utc" not in raw.columns:
        raise DataFetchError(f"{path}: no recognisable timestamp column")
    ts = raw["timestamp_utc"]
    if pd.api.types.is_numeric_dtype(ts):
        unit = timestamp_unit or ("s" if float(ts.max()) < 1e11 else
                                  "ms" if float(ts.max()) < 1e14 else "ns")
        ts = pd.to_datetime(ts.astype("float64"), unit=unit, utc=True)
    else:
        parsed = pd.to_datetime(ts, utc=True, errors="coerce", format="mixed")
        ts = parsed
    raw["timestamp_utc"] = ts

    if "symbol" not in raw.columns or raw["symbol"].isna().all():
        if symbol is None:
            import os
            symbol = os.path.splitext(os.path.basename(path))[0]
        raw["symbol"] = symbol
    if "volume" not in raw.columns:
        raw["volume"] = 0.0
    return schema.coerce(raw)


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------

@dataclass
class FetchResult:
    asset_key: str
    symbol: str
    timeframe: str
    frames: Dict[str, pd.DataFrame]      # timeframe -> canonical frame
    meta: Dict[str, Any]


def fetch_asset(spec: AssetSpec, timeframe: str = "4h",
                start: Optional[str] = None,
                include_context: bool = False,
                raw_cache_dir: Optional[str] = None) -> FetchResult:
    """Fetch one asset at the requested timeframe (resampling if needed)."""
    from .resample import resample_ohlcv  # local import: avoids a cycle

    frames: Dict[str, pd.DataFrame] = {}
    meta: Dict[str, Any] = {"venue": spec.venue, "source_ticker": spec.source_ticker,
                            "requested_timeframe": timeframe}

    if spec.venue.startswith("binance"):
        start_ms = int(pd.Timestamp(start, tz=UTC).timestamp() * 1000) if start else None
        src_tf = spec.raw_timeframe if spec.raw_timeframe == timeframe else "1h"
        raw = binance_klines(spec.source_ticker, interval=src_tf, start_ms=start_ms)
        meta["native_timeframe"] = src_tf
    elif spec.venue.startswith("yahoo"):
        raw = yahoo_ohlcv(spec.source_ticker, interval=spec.raw_timeframe,
                          period="max" if not start else None, start=start)
        meta["native_timeframe"] = spec.raw_timeframe
    else:
        raise DataFetchError(f"unknown venue {spec.venue}")

    if raw_cache_dir:
        import os
        os.makedirs(raw_cache_dir, exist_ok=True)
        safe = spec.key.lower()
        raw.to_parquet(os.path.join(raw_cache_dir, f"{safe}_{meta['native_timeframe']}_raw.parquet"),
                       index=False)

    frames[meta["native_timeframe"]] = raw
    if meta["native_timeframe"] != timeframe:
        frames[timeframe] = resample_ohlcv(raw, timeframe, spec)
    else:
        frames[timeframe] = raw
    meta["rows_raw"] = int(len(raw))
    meta["rows_target"] = int(len(frames[timeframe]))
    return FetchResult(asset_key=spec.key, symbol=frames[timeframe]["symbol"].iloc[0]
                       if len(frames[timeframe]) else spec.symbol,
                       timeframe=timeframe, frames=frames, meta=meta)


def fetch_context(names: Optional[List[str]] = None,
                  start: Optional[str] = None) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for name, spec in CONTEXT_SERIES.items():
        if names and name not in names:
            continue
        try:
            out[name] = yahoo_ohlcv(spec["ticker"], interval=spec["timeframe"],
                                    period="max" if not start else None, start=start)
            time.sleep(2.0)
        except Exception as exc:                        # noqa: BLE001
            out[name] = schema.empty_frame()
            out[name].attrs["error"] = str(exc)
    return out


__all__ = ["DataFetchError", "binance_klines", "binance_funding", "yahoo_ohlcv",
           "read_user_table", "fetch_asset", "fetch_context", "FetchResult"]
