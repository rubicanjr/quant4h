#!/usr/bin/env python3
"""
Phase-0/1 driver: bootstrap the study datasets and run data-quality control.

    python scripts/run_data_qc.py --assets BTC GOLD SILVER BIST30 \
        --start 2017-08-17 --timeframe 4h --out reports

What it does
------------
1. Downloads (or re-reads the cache of) each asset at its native timeframe.
2. Resamples to the target timeframe using the asset's own session calendar.
3. Runs the QC battery on the target frame (and audits it against the source).
4. Writes data/raw/*.parquet, data/interim/*_4h.parquet and reports/qc_*.

It does NOT clean, impute or adjust anything. Raw stays raw.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import pandas as pd  # noqa: E402

from quant4h.config import DEFAULT_ASSETS, TIMEFRAME, UTC  # noqa: E402
from quant4h.data import adapters, qc, schema  # noqa: E402
from quant4h.data.resample import resample_ohlcv  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _cache_path(key: str, tf: str) -> str:
    return os.path.join(ROOT, "data", "raw", f"{key.lower()}_{tf}_raw.parquet")


def get_native(spec, start: Optional[str], use_cache: bool) -> pd.DataFrame:
    key = spec.key.lower()
    path = _cache_path(key, spec.raw_timeframe)
    if use_cache and os.path.exists(path):
        df = schema.load_parquet(path)
        if len(df):
            print(f"  [cache] {path} rows={len(df)}")
            return df
    print(f"  [fetch] venue={spec.venue} ticker={spec.source_ticker} tf={spec.raw_timeframe}")
    if spec.venue.startswith("binance"):
        start_ms = int(pd.Timestamp(start, tz=UTC).timestamp() * 1000) if start else None
        df = adapters.binance_klines(spec.source_ticker, interval=spec.raw_timeframe,
                                     start_ms=start_ms)
    elif spec.venue.startswith("yahoo"):
        df = adapters.yahoo_ohlcv(spec.source_ticker, interval=spec.raw_timeframe,
                                  period="max" if not start else None, start=start)
    else:
        raise SystemExit(f"unsupported venue {spec.venue}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"  [saved] {path} rows={len(df)}")
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets", nargs="*", default=list(DEFAULT_ASSETS),
                    help=f"subset of {list(DEFAULT_ASSETS)}")
    ap.add_argument("--timeframe", default=TIMEFRAME)
    ap.add_argument("--start", default=None, help="ISO date, e.g. 2017-08-17")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    ap.add_argument("--min-rows", type=int, default=1500)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--with-context", action="store_true", help="also fetch DXY/US10Y/USDTRY")
    ap.add_argument("--funding", action="store_true", help="also fetch BTC perpetual funding")
    ap.add_argument("--retries", type=int, default=3, help="retries per asset on fetch failure")
    ap.add_argument("--retry-sleep", type=float, default=25.0)
    ap.add_argument("--no-adjust", action="store_true",
                    help="adjust pipeline'i atla (yalnizca ham QC)")
    ap.add_argument("--apply-roll-correction", action="store_true",
                    help="bayrakli roll'lerde fiyati back-adjust et (varsayilan: SADECE ISARETLE)")
    ap.add_argument("--roll-atr-multiple", type=float, default=3.0)
    args = ap.parse_args()

    t0 = time.time()
    frames: Dict[str, pd.DataFrame] = {}
    sources: Dict[str, pd.DataFrame] = {}
    reports = []
    evidence: List[Dict[str, Any]] = []

    for key in args.assets:
        if key not in DEFAULT_ASSETS:
            print(f"!! unknown asset {key}; known: {list(DEFAULT_ASSETS)}")
            continue
        spec = DEFAULT_ASSETS[key]
        print(f"\n=== {key} ({spec.symbol}) ===")
        print(f"  note: {spec.tradability_note}")
        native = None
        for attempt in range(max(1, args.retries)):
            try:
                native = get_native(spec, args.start, use_cache=not args.no_cache)
                break
            except Exception as exc:                                # noqa: BLE001
                print(f"  !! fetch attempt {attempt + 1} failed: {type(exc).__name__}: {exc}")
                if attempt + 1 < max(1, args.retries):
                    time.sleep(args.retry_sleep * (attempt + 1))
        if native is None:
            exc = RuntimeError("all fetch attempts failed")
            reports.append(qc.AssetQCReport(key, spec.symbol, args.timeframe, 0, None, None))
            reports[-1].add("fetch", "ERROR", f"data fetch failed: {type(exc).__name__}: {exc}")
            reports[-1].finalise(args.min_rows)
            continue
        sources[key] = native
        if spec.raw_timeframe == args.timeframe:
            target = native
        else:
            # min_bars_fill=1: ince (thin) barlar DUSURULMEZ, n_src_bars ile
            # isaretlenir ve QC'da seffaf sekilde raporlanir. Veri kaybi yok.
            target = resample_ohlcv(native, args.timeframe, spec,
                                    min_bars_fill=spec.min_source_bars_per_target)
        target["symbol"] = spec.symbol
        interim = os.path.join(ROOT, "data", "interim", f"{key.lower()}_{args.timeframe}.parquet")
        os.makedirs(os.path.dirname(interim), exist_ok=True)
        target.to_parquet(interim, index=False)
        # --- adjust pipeline (KARAR 2 & 3) --------------------------------
        # Ayni 'target' frame uzerinde calistirilir; boylece interim yeniden
        # uretildiginde 1 barlik kayma OLMAZ (ayri calistirmada olmustu).
        # attrs parquet'te saklanamadigi icin sidecar JSON'a yazilir.
        if not args.no_adjust:
            from quant4h.data.adjust import adjust_asset
            adj, arep, alog = adjust_asset(target, spec, args.timeframe,
                                           roll_atr_multiple=args.roll_atr_multiple,
                                           apply_roll_correction=args.apply_roll_correction,
                                           src_timeframe=spec.raw_timeframe)
            assert len(adj) == len(target), "adjust bar sayisini degistirdi"
            os.makedirs(os.path.join(ROOT, "data", "processed"), exist_ok=True)
            base = os.path.join(ROOT, "data", "processed",
                                f"{key.lower()}_{args.timeframe}_adjusted")
            adj.to_parquet(base + ".parquet", index=False)
            with open(base + ".attrs.json", "w", encoding="utf-8") as fh:
                json.dump(dict(adj.attrs), fh, indent=2, default=str)
            print(f"  [adjust] {arep.rows_in}->{arep.rows_out} bar (silinen 0, eklenen 0) | "
                  f"kesinti {len(arep.outage_windows)} | non-tradable {arep.n_non_tradable} | "
                  f"gecersiz getiri {arep.n_return_invalid} | aday {arep.n_roll_candidate} | "
                  f"duzeltilen {arep.n_roll_event}")
            evidence.append({"key": key, "spec_symbol": spec.symbol, "mode": spec.mode,
                               "requires_adjustment": spec.requires_adjustment,
                               "report": arep.to_dict(), "log": alog.to_dict(),
                               "before_rows": len(target), "after_rows": len(adj),
                               "raw_close_identical": bool(
                                   (adj["close_raw"].to_numpy() == target["close"].to_numpy()).all()),
                               "timestamps_identical": bool(
                                   list(adj["timestamp_utc"]) == list(target["timestamp_utc"]))})
            target = adj
        frames[key] = target
        print(f"  [target] {args.timeframe}: rows={len(target)} "
              f"{target['timestamp_utc'].min()} -> {target['timestamp_utc'].max()}")
        rep = qc.qc_asset(target, spec, args.timeframe,
                          source_df=(native if spec.raw_timeframe != args.timeframe else None),
                          min_rows=args.min_rows)
        reports.append(rep)
        print(f"  [qc] verdict={rep.verdict} errors={rep.n_error} warns={rep.n_warn}")

    portfolio = qc.qc_portfolio(frames, min_overlap_bars=500) if len(frames) > 1 else {}

    if args.funding and "BTC" in frames:
        try:
            f = adapters.binance_funding("BTCUSDT")
            f.to_parquet(os.path.join(ROOT, "data", "raw", "btc_funding_raw.parquet"), index=False)
            print(f"\n[funding] rows={len(f)} {f['funding_time_utc'].min()} -> {f['funding_time_utc'].max()}")
        except Exception as exc:                                    # noqa: BLE001
            print(f"\n[funding] failed: {exc}")

    if args.with_context:
        ctx = adapters.fetch_context()
        for name, df in ctx.items():
            if len(df):
                df.to_parquet(os.path.join(ROOT, "data", "raw", f"ctx_{name.lower()}_1d.parquet"),
                              index=False)
                print(f"[context] {name}: rows={len(df)}")
            else:
                print(f"[context] {name}: FAILED {df.attrs.get('error', '')[:80]}")

    os.makedirs(args.out, exist_ok=True)
    if evidence:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from run_adjust import build_evidence_md
        with open(os.path.join(args.out, "adjust_evidence.md"), "w", encoding="utf-8") as fh:
            fh.write(build_evidence_md(evidence, args.apply_roll_correction,
                                       args.roll_atr_multiple))
        print(f"\nKanit tablosu: {os.path.join(args.out, 'adjust_evidence.md')}")
    paths = qc.save_reports(reports, portfolio, args.out)
    print("\n=== QC reports ===")
    for k, v in paths.items():
        print(f"  {k}: {v}")

    summary = {r.asset_key: {"verdict": r.verdict, "rows": r.rows,
                             "usable": r.usable_for_modelling,
                             "errors": r.n_error, "warns": r.n_warn}
               for r in reports}
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nportfolio: {json.dumps(portfolio, indent=2, default=str)[:3000]}")
    print(f"\nelapsed {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
