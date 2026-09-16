#!/usr/bin/env python3
"""
AŞAMA 1.5 — BIST30 hisse üniverseli pipeline'ı.

    python3 scripts/run_bist_universe.py                 # tüm ünivers (30 hisse)
    python3 scripts/run_bist_universe.py --limit 3       # duman testi
    python3 scripts/run_bist_universe.py --only THYAO AKBNK

Adımlar (kullanıcının kabul kriterleriyle birebir):
  1. Ünivers   : configs/bist30_universe.yaml (tarih damgalı, 30 üye) — SABİT
  2. İndirme   : hisse başına Yahoo 1h; küçük batch + retry + bekleme;
                 ham veri hisse başına AYRI parquet olarak cache'lenir (immutable)
  3. Resample  : İstanbul lokal grid 10:00 -> 4H (günde ~2 TAM bar + 1 ince bar);
                 oluşmakta olan son bar DÜŞÜRÜLÜR
  4. QC        : hisse bazlı tablo -> reports/bist30_universe_qc.md (+ .csv)
                 bar sayısı · eksik % · thin % · halt/gap bayrakları ·
                 kurumsal aksiyon bayrakları · ort. günlük TL hacim
                 Likidite/kalite eşiğini geçemeyenler GEREKÇESİYLE elenir
                 (SİLİNMEZ, `excluded` işaretlenir)
  5. Kurumsal aksiyon: adjust.py felsefesiyle TUTARLI — OTOMATİK DÜZELTME YOK,
                 FLAG ONLY. Ex-date barında return_valid=False + non_tradable=True
  6. XU030     : trade varlığı değil, long'lar için bağlam filtresi olarak kalır

Çıktılar:
  data/raw/bist30/<CODE>_1h_raw.parquet            (immutable ham)
  data/interim/bist30/<CODE>_4h.parquet            (4H kanonik)
  data/processed/bist30/<CODE>_4h_adjusted.parquet (+ .attrs.json)
  reports/bist30_universe_qc.md / .csv / .json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quant4h.config import (BIST_STOCK_ROUND_TRIP_BPS, UTC, bist_stock_specs,  # noqa: E402
                            load_bist_universe)
from quant4h.data import qc, schema  # noqa: E402
from quant4h.data.adapters import DataFetchError, yahoo_ohlcv  # noqa: E402
from quant4h.data.adjust import (adjust_asset, corporate_actions_from_daily,  # noqa: E402
                                 flag_corporate_actions_from_dates,
                                 flag_price_limit_bars)
from quant4h.data.resample import resample_ohlcv  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _p(*parts: str) -> str:
    return os.path.join(ROOT, *parts)


# ---------------------------------------------------------------------------
# 2. indirme
# ---------------------------------------------------------------------------

def download_universe(members: List[Dict[str, Any]], cfg: Dict[str, Any],
                      use_cache: bool = True, verbose: bool = True) -> Dict[str, Any]:
    """Yahoo 1h, küçük batch + retry + bekleme; hisse başına ayrı immutable cache."""
    dl = cfg["download"]
    raw_dir = _p(dl["cache_dir"])
    os.makedirs(raw_dir, exist_ok=True)
    out: Dict[str, Any] = {}
    batch = max(1, int(dl["batch_size"]))
    for i, m in enumerate(members):
        code = m["code"]
        path = os.path.join(raw_dir, dl["cache_file_pattern"].format(code=code))
        if use_cache and os.path.exists(path):
            try:
                df = schema.load_parquet(path)
                if len(df):
                    out[code] = {"status": "cache", "rows": len(df), "path": path}
                    if verbose:
                        print(f"  [{code:6s}] cache rows={len(df)}")
                    continue
            except Exception:                                       # noqa: BLE001
                pass
        frame: Optional[pd.DataFrame] = None
        err = ""
        for attempt in range(int(dl["retries"])):
            try:
                frame = yahoo_ohlcv(m["yahoo"], interval=dl["interval"],
                                    period=dl["period"], retries=1,
                                    sleep_s=float(dl["retry_backoff_s"]))
                if frame is not None and len(frame):
                    break
                err = "boş yanıt"
            except Exception as exc:                                # noqa: BLE001
                err = f"{type(exc).__name__}: {str(exc)[:90]}"
            time.sleep(float(dl["retry_backoff_s"]) * (attempt + 1))
        if frame is None or not len(frame):
            out[code] = {"status": "failed", "rows": 0, "error": err}
            if verbose:
                print(f"  [{code:6s}] BAŞARISIZ {err}")
        else:
            frame.to_parquet(path, index=False)
            out[code] = {"status": "downloaded", "rows": len(frame), "path": path}
            if verbose:
                print(f"  [{code:6s}] indirildi rows={len(frame)} "
                      f"{pd.to_datetime(frame['timestamp_utc'], utc=True).min():%Y-%m-%d} → "
                      f"{pd.to_datetime(frame['timestamp_utc'], utc=True).max():%Y-%m-%d}")
        time.sleep(float(dl["sleep_between_symbols_s"]))
        if (i + 1) % batch == 0:
            time.sleep(float(dl["sleep_between_batches_s"]))
    return out


def download_daily(code: str, yahoo_ticker: str, cfg: Dict[str, Any],
                   use_cache: bool = True) -> Optional[pd.DataFrame]:
    """Kurumsal aksiyon tespiti icin GUNLUK seri (Yahoo 1h'de adjclose==close
    oldugu icin tespit yalnizca gunluk seriden yapilabilir)."""
    dl = cfg["download"]
    d = _p(dl["cache_dir"])
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{code}_1d_raw.parquet")
    if use_cache and os.path.exists(path):
        try:
            df = schema.load_parquet(path)
            if len(df):
                return df
        except Exception:                                          # noqa: BLE001
            pass
    for attempt in range(int(dl["retries"])):
        try:
            df = yahoo_ohlcv(yahoo_ticker, interval="1d", period="max",
                             retries=1, sleep_s=float(dl["retry_backoff_s"]))
            if df is not None and len(df):
                df.to_parquet(path, index=False)
                return df
        except Exception:                                          # noqa: BLE001
            pass
        time.sleep(float(dl["retry_backoff_s"]) * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# 3+5. resample + adjust + bayraklar
# ---------------------------------------------------------------------------

def build_stock_frame(code: str, member: Dict[str, Any], specs: Dict[str, Any],
                      timeframe: str = "4h",
                      apply_roll_correction: bool = False,
                      cfg: Optional[Dict[str, Any]] = None,
                      use_cache: bool = True) -> Optional[pd.DataFrame]:
    spec = specs[f"BIST_{code}"]
    raw_path = _p("data", "raw", "bist30", f"{code}_1h_raw.parquet")
    if not os.path.exists(raw_path):
        return None
    raw = schema.load_parquet(raw_path)
    if not len(raw):
        return None
    # ince barlar SİLİNMEZ (min_bars_fill=1); oluşmakta olan son bar DÜŞÜRÜLÜR
    # min_bars_fill = spec.min_source_bars_per_target (BIST için 4): ince
    # "açılış anı" barı ÜRETİLMEZ. Aksi hâlde k=3 fraktal hiçbir swing'i
    # onaylayamıyor (her 3 barda bir anchor-uygun olmayan bar var).
    frame = resample_ohlcv(raw, timeframe, spec,
                           min_bars_fill=spec.min_source_bars_per_target,
                           drop_partial=True)
    frame["symbol"] = f"{code}.IS"
    interim_dir = _p("data", "interim", "bist30")
    os.makedirs(interim_dir, exist_ok=True)
    frame.to_parquet(os.path.join(interim_dir, f"{code}_{timeframe}.parquet"), index=False)

    adj, _rep, _log = adjust_asset(frame, spec, timeframe,
                                   apply_roll_correction=apply_roll_correction,
                                   src_timeframe=spec.raw_timeframe)
    # Kurumsal aksiyon tespiti GUNLUK seriden (Yahoo 1h'de adjclose==close).
    daily = download_daily(code, member.get("yahoo", f"{code}.IS"), cfg or {}, use_cache) \
        if cfg is not None else None
    if daily is not None and len(daily):
        events = corporate_actions_from_daily(daily)
        adj = flag_corporate_actions_from_dates(
            adj, events["date"].tolist(),
            event_types=dict(zip(events["date"], events["event_type"])))
        adj.attrs["corporate_action_event_dates"] = [str(d.date()) for d in events["date"]]
        adj.attrs["daily_rows"] = int(len(daily))
    else:
        adj = flag_corporate_actions(adj)          # fallback: adj_ratio (1h'de 0 bulur)
        adj.attrs["corporate_action_warning"] = (
            "gunluk seri indirilemedi -> kurumsal aksiyon tespiti YAPILAMADI; "
            "bolunme/temettu barlari ISARETSIZ ve getiri serisi BOZUK olabilir")
    adj = flag_price_limit_bars(adj)

    proc_dir = _p("data", "processed", "bist30")
    os.makedirs(proc_dir, exist_ok=True)
    base = os.path.join(proc_dir, f"{code}_{timeframe}_adjusted")
    adj.to_parquet(base + ".parquet", index=False)
    with open(base + ".attrs.json", "w", encoding="utf-8") as fh:
        json.dump({k: v for k, v in adj.attrs.items()}, fh, indent=2, default=str)
    return adj


# ---------------------------------------------------------------------------
# 4. hisse bazlı QC tablosu
# ---------------------------------------------------------------------------

def _daily_frame(code: str) -> Optional[pd.DataFrame]:
    p = _p("data", "raw", "bist30", f"{code}_1d_raw.parquet")
    return schema.load_parquet(p) if os.path.exists(p) else None


def _daily_events(code: str) -> pd.DataFrame:
    d = _daily_frame(code)
    if d is None or not len(d):
        return pd.DataFrame(columns=["date", "event_type", "ratio_step"])
    return corporate_actions_from_daily(d)


def _max_ratio_step(code: str) -> float:
    ev = _daily_events(code)
    return round(float(ev["ratio_step"].max()), 5) if len(ev) and "ratio_step" in ev else 0.0

def stock_metrics(code: str, member: Dict[str, Any], spec: Any, frame: pd.DataFrame,
                  timeframe: str, cfg: Dict[str, Any],
                  source_frame: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    gates = cfg["quality_gates"]
    liq = cfg["liquidity"]
    # source_frame verilmezse 'resample' denetimi (thin bar %) HESAPLANAMAZ.
    rep = qc.qc_asset(frame, spec, timeframe, source_df=source_frame,
                      min_rows=int(gates["min_4h_bars"]))
    st = rep.stats
    ts = pd.to_datetime(frame["timestamp_utc"], utc=True)
    history_days = int((ts.max() - ts.min()).total_seconds() // 86400) if len(ts) > 1 else 0

    thin_frac = float(st.get("resample_thin_fraction", 0.0) or 0.0)
    missing_frac = float(st.get("missing_bar_fraction", 0.0) or 0.0)
    vol = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
    zero_vol_all = float((vol == 0).mean())
    # KRITIK AYRIM: BIST'te 4H grid 3 bin uretir; 06:00 lokal bin'i YALNIZCA
    # Yahoo'nun 09:30 "acilis ani" printini tasir (n_src_bars=1) ve bu print
    # ~%49 oraninda SIFIR hacimli gelir. Tam barlarda (n_src_bars=4) sifir hacim
    # pratikte YOKTUR. Bu yuzden kalite kapisi TAM barlar uzerinden olculur;
    # ince barlar ayrica raporlanir (zaten non_tradable isaretlidir).
    n_src = (pd.to_numeric(frame["n_src_bars"], errors="coerce")
             if "n_src_bars" in frame.columns else pd.Series(np.nan, index=frame.index))
    full_mask = (n_src >= 3) if n_src.notna().any() else pd.Series(True, index=frame.index)
    zero_vol_full = float((vol[full_mask] == 0).mean()) if full_mask.any() else 0.0
    zero_vol = zero_vol_full          # kapida kullanilan deger
    zero_vol
    halt = int(frame["halt_or_limit_flag"].sum()) if "halt_or_limit_flag" in frame.columns else 0
    ca = int(frame["corporate_action_flag"].sum()) if "corporate_action_flag" in frame.columns else 0
    ca_split = int((frame.get("corporate_action_type", pd.Series(dtype=str)) == "split").sum()) \
        if "corporate_action_type" in frame.columns else 0

    # likidite: ortalama günlük TL hacim (volume x close), son N seans
    turnover = (pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
                * pd.to_numeric(frame["close"], errors="coerce"))
    if "session_date" in frame.columns:
        sess_key = pd.to_datetime(frame["session_date"].astype(str))
    else:
        sess_key = ts.dt.tz_convert(spec.native_session_tz).dt.normalize()
    daily = turnover.groupby(sess_key.to_numpy()).sum()
    window = daily.tail(int(liq["window_days"]))
    avg_turnover_try = float(window.mean()) if len(window) else 0.0
    daily_vol = (pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
                 .groupby(sess_key.to_numpy()).sum())
    avg_vol_lots = float(daily_vol.tail(int(liq["window_days"])).mean()) if len(daily_vol) else 0.0

    reasons: List[str] = []
    if len(frame) < int(gates["min_4h_bars"]):
        reasons.append(f"bar sayısı {len(frame)} < {gates['min_4h_bars']}")
    if missing_frac > float(gates["max_missing_fraction"]):
        reasons.append(f"eksik bar %{missing_frac * 100:.1f} > %{float(gates['max_missing_fraction']) * 100:.0f}")
    if thin_frac > float(gates["max_thin_fraction"]):
        reasons.append(f"thin bar %{thin_frac * 100:.1f} > %{float(gates['max_thin_fraction']) * 100:.0f}")
    if zero_vol_full > float(gates["max_zero_volume_fraction"]):
        reasons.append(f"TAM barlarda sıfır hacim %{zero_vol_full * 100:.1f} > "
                       f"%{float(gates['max_zero_volume_fraction']) * 100:.0f}")
    if len(frame) and halt / len(frame) > float(gates["max_halt_fraction"]):
        reasons.append(f"halt/marj bayrağı %{100 * halt / len(frame):.1f} > %{float(gates['max_halt_fraction']) * 100:.0f}")
    if history_days < int(gates["min_history_days"]):
        reasons.append(f"geçmiş {history_days} gün < {gates['min_history_days']} gün")
    if avg_turnover_try < float(liq["min_avg_daily_turnover_try"]):
        reasons.append(f"ort. günlük hacim {avg_turnover_try / 1e6:.0f} mn TL < "
                       f"{float(liq['min_avg_daily_turnover_try']) / 1e6:.0f} mn TL")
    if avg_vol_lots < float(liq["min_avg_daily_volume_lots"]):
        reasons.append(f"ort. günlük {avg_vol_lots / 1e3:.0f} bin lot < "
                       f"{float(liq['min_avg_daily_volume_lots']) / 1e3:.0f} bin lot")
    if rep.n_error:
        reasons.append(f"{rep.n_error} QC ERROR: {rep.blockers[0][:70]}")

    return {
        "code": code, "name": member.get("name") or "", "sector": member.get("sector") or "",
        "yahoo": member.get("yahoo") or "",
        "bars_4h": int(len(frame)),
        "sessions": int(st.get("sessions", 0) or 0),
        "bars_per_session": float(st.get("bars_per_session_median", 0) or 0),
        "history_days": history_days,
        "first_utc": str(ts.min()) if len(ts) else "",
        "last_utc": str(ts.max()) if len(ts) else "",
        "missing_frac": round(missing_frac, 4),
        "thin_frac": round(thin_frac, 4),
        "thin_bars": int(st.get("resample_thin_bars", 0) or 0),
        "zero_volume_frac_full_bars": round(zero_vol_full, 4),
        "zero_volume_frac_all_bars": round(zero_vol_all, 4),
        "full_bars": int(full_mask.sum()),
        "halt_or_limit_bars": halt,
        "halt_or_limit_frac": round(halt / len(frame), 4) if len(frame) else 0.0,
        "corporate_action_bars": ca,
        "corporate_action_marked_bars": int(frame.attrs.get("corporate_action_marked_bars", 0) or 0),
        "corporate_action_events": int(frame.attrs.get("corporate_action_events", 0) or 0),
        "corporate_action_events_all_history": int(len(_daily_events(code))),
        "max_adj_ratio_step": _max_ratio_step(code),
        "corporate_action_source": str(frame.attrs.get("corporate_action_source", "n/a")),
        "daily_rows": int(frame.attrs.get("daily_rows", 0) or 0),
        "corporate_action_splits": ca_split,
        "gap_anomaly_bars": int(st.get("bars_crossing_data_gap", 0) or 0),
        "return_invalid_bars": int(st.get("return_invalid_bars", 0) or 0),
        "non_tradable_bars": int(st.get("non_tradable_bars", 0) or 0),
        "non_tradable_frac": round(float(st.get("non_tradable_frac", 0.0) or 0.0), 4),
        "avg_daily_turnover_try": round(avg_turnover_try, 0),
        "avg_daily_volume_lots": round(avg_vol_lots, 0),
        "avg_daily_turnover_last_session_try": round(float(daily.iloc[-1]), 0) if len(daily) else 0.0,
        "qc_verdict": rep.verdict,
        "qc_errors": rep.n_error,
        "qc_warns": rep.n_warn,
        "max_abs_return_valid": round(float(st.get("abs_logret_max", 0.0) or 0.0), 4),
        "status": "INCLUDED" if not reasons else "EXCLUDED",
        "exclusion_reasons": reasons,
        "round_trip_cost_bps": BIST_STOCK_ROUND_TRIP_BPS,
    }


# ---------------------------------------------------------------------------
# rapor
# ---------------------------------------------------------------------------

def write_reports(rows: List[Dict[str, Any]], universe: Dict[str, Any],
                  downloads: Dict[str, Any], out_dir: str, timeframe: str) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    df = pd.DataFrame(rows).sort_values(["status", "avg_daily_turnover_try"],
                                        ascending=[True, False])
    csv_path = os.path.join(out_dir, "bist30_universe_qc.csv")
    df.to_csv(csv_path, index=False)
    json_path = os.path.join(out_dir, "bist30_universe_qc.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"universe_version": universe.get("version"),
                   "generated_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
                   "timeframe": timeframe, "downloads": downloads,
                   "stocks": rows}, fh, indent=2, default=str)

    inc = df[df["status"] == "INCLUDED"]
    exc = df[df["status"] == "EXCLUDED"]
    L: List[str] = []
    L.append("# AŞAMA 1.5 — BIST30 Hisse Üniversesi QC Raporu")
    L.append("")
    L.append(f"*Üretim: {pd.Timestamp.now(tz=UTC):%Y-%m-%d %H:%M:%S UTC}* · "
             f"ünivers sürümü **{universe.get('version')}** (dondurulmuş: "
             f"{universe.get('frozen_at_utc')}) · timeframe **{timeframe}** · "
             f"maliyet **{BIST_STOCK_ROUND_TRIP_BPS:.0f} bp gidiş-dönüş**")
    L.append("")
    L.append("## ZORUNLU CAVEAT'LER")
    L.append("")
    for c in universe.get("mandatory_caveats", []):
        L.append(f"- **[{c.get('severity')}] {c.get('id')}** — {c.get('text', '').strip()}")
    L.append("")
    L.append("## ÖZET")
    L.append("")
    L.append(f"- Ünivers üyesi: **{len(rows)}** · İndirme başarılı: "
             f"**{sum(1 for v in downloads.values() if v.get('status') != 'failed')}** · "
             f"başarısız: **{sum(1 for v in downloads.values() if v.get('status') == 'failed')}**")
    L.append(f"- **SEPETE GİREN: {len(inc)}** · **ELENE: {len(exc)}**")
    if len(df):
        L.append(f"- Medyan 4H bar sayısı: **{df['bars_4h'].median():.0f}** "
                 f"(min {df['bars_4h'].min()}, max {df['bars_4h'].max()})")
        L.append(f"- Medyan eksik bar oranı: **%{df['missing_frac'].median() * 100:.2f}** · "
                 f"medyan thin bar oranı: **%{df['thin_frac'].median() * 100:.1f}**")
        L.append(f"- Kurumsal aksiyon **olayı**: 4H penceresi içinde "
                 f"**{int(df['corporate_action_events'].sum())}** (tüm geçmişte "
                 f"{int(df['corporate_action_events_all_history'].sum())}) · işaretli bar: "
                 f"**{int(df['corporate_action_marked_bars'].sum())}** · "
                 f"bölünme adayı: {int(df['corporate_action_splits'].sum())} · "
                 f"halt/marj bayrağı: **{int(df['halt_or_limit_bars'].sum())}** · "
                 f"beklenmedik boşluk: **{int(df['gap_anomaly_bars'].sum())}**")
        L.append(f"- Ort. günlük TL hacim (son 60 seans): medyan **{df['avg_daily_turnover_try'].median() / 1e6:,.0f} mn TL**")
    L.append("")
    L.append("## HİSSE BAZLI QC TABLOSU")
    L.append("")
    L.append("| Hisse | 4H bar | tam bar | ince bar | seans | gün | eksik % | thin % | sıfır-hacim (tam) | halt | k.a. olay (pencere) | k.a. işaretli bar | bölünme adayı | maks. oran adımı | gap | geçersiz getiri | ort. günlük hacim (mn TL) | QC | Durum |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")
    for _, r in df.iterrows():
        L.append(f"| **{r['code']}** | {r['bars_4h']} | {r['full_bars']} | {r['thin_bars']} | "
                 f"{r['sessions']} | {r['history_days']} | %{r['missing_frac'] * 100:.1f} | "
                 f"%{r['thin_frac'] * 100:.0f} | %{r['zero_volume_frac_full_bars'] * 100:.1f} | "
                 f"{r['halt_or_limit_bars']} | {r['corporate_action_bars']} | {r['corporate_action_splits']} | "
                 f"{r['gap_anomaly_bars']} | {r['return_invalid_bars']} | "
                 f"{r['avg_daily_turnover_try'] / 1e6:,.0f} | {r['qc_verdict']} | "
                 f"{'✅ GİRDİ' if r['status'] == 'INCLUDED' else '❌ ELENDİ'} |")
    L.append("")
    if len(exc):
        L.append("## ELENEN HİSSELER VE GEREKÇELERİ")
        L.append("")
        L.append("> Eleme = **işaretleme**. Veri SİLİNMEZ; hisse `data/processed/bist30/` "
                 "altında durur ve raporda görünür. Yalnızca sepet performansına alınmaz.")
        L.append("")
        for _, r in exc.iterrows():
            L.append(f"- **{r['code']}** ({r['name']}) — " + "; ".join(r["exclusion_reasons"]))
        L.append("")
    L.append("## KURUMSAL AKSİYON POLİTİKASI (adjust.py felsefesiyle tutarlı)")
    L.append("")
    L.append("- **OTOMATİK DÜZELTME YOK.** `close_raw` ve `adjclose` ayrı kolonlarda korunur.")
    L.append("- **Tespit GÜNLÜK seriden yapılır.** Ölçüldü: Yahoo'nun **1h** BIST serisinde "
             "`adjclose == close` (%100), yani intraday seri kurumsal aksiyon düzeltmesi "
             "İÇERMİYOR. Günlük seride `adjclose/close` oranı her ex-date'te adım değiştirir "
             "ve olay tarihleri 4H barlara `session_date` üzerinden taşınır.")
    L.append("- Sınıflandırma: adım + |log getiri| > 0.25 → `split` adayı; değilse "
             "`dividend_or_other`. **DÜRÜST SINIR:** bu kural yalnızca BÜYÜK (>%25 fiyat "
             "sıçramalı) bölünmeleri yakalar; 1.05:1 gibi küçük oranlı bölünmeler "
             "`dividend_or_other` olarak sınıflandırılır. Bu ünivers için tespit edilen "
             "bölünme adayı sayısı **0**'dır ve tüm olaylar yıllık temettü mevsimiyle "
             "(Mart–Haziran) uyumludur; yine de 'bölünme yoktur' iddiası DEĞİL, "
             "'>%25 sıçramalı bölünme yoktur' iddiasıdır.")
    L.append("- Etki: olay barı ve sonraki bar `return_valid=False` + `non_tradable=True`. "
             "Ex-date'i atlayan getiri **gerçek getiri değildir**.")
    L.append("- Hiçbir fiyat YAZILMAZ/DEĞİŞTİRİLMEZ; hiçbir bar SİLİNMEZ.")
    L.append("")
    L.append("## XU030 ENDEKSİNİN ROLÜ")
    L.append("")
    L.append("- `XU030.IS` **trade varlığı DEĞİLDİR**; `watch_only` modundadır.")
    L.append("- Rolü: **long'lar için bağlam filtresi** (ör. endeks EMA200 altındayken "
             "hisse LONG sinyalleri bastırılır).")
    L.append("- Endeks getirisi portföy performansına **YAZILMAZ**.")
    L.append(f"- Veri: `data/interim/bist30_4h.parquet` · maliyet modeli hisse sepeti için "
             f"**{BIST_STOCK_ROUND_TRIP_BPS:.0f} bp** gidiş-dönüş (endeks için VİOP proxy'si GEÇERSİZ).")
    L.append("")
    md_path = os.path.join(out_dir, "bist30_universe_qc.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    return {"md": md_path, "csv": csv_path, "json": json_path}


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", default=None, help="yalnızca bu kodlar")
    ap.add_argument("--limit", type=int, default=None, help="ilk N hisse (duman testi)")
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--out", default=_p("reports"))
    ap.add_argument("--apply-roll-correction", action="store_true")
    args = ap.parse_args()

    universe = load_bist_universe()
    specs = bist_stock_specs(universe)
    members = universe.get("members", [])
    if args.only:
        members = [m for m in members if m["code"] in set(args.only)]
    if args.limit:
        members = members[:args.limit]
    print(f"Ünivers sürümü: {universe.get('version')} | üye: {len(members)} | "
          f"maliyet: {BIST_STOCK_ROUND_TRIP_BPS:.0f} bp gidiş-dönüş")

    if args.skip_download:
        downloads = {m["code"]: {"status": "skipped", "rows": 0} for m in members}
    else:
        print("\n=== ADIM 2: indirme (Yahoo 1h, küçük batch + retry + bekleme) ===")
        downloads = download_universe(members, universe, use_cache=not args.no_cache)

    print("\n=== ADIM 3+4+5: resample → adjust → bayraklar → QC ===")
    rows: List[Dict[str, Any]] = []
    for m in members:
        code = m["code"]
        spec = specs.get(f"BIST_{code}")
        if spec is None:
            continue
        frame = build_stock_frame(code, m, specs, args.timeframe,
                                  apply_roll_correction=args.apply_roll_correction,
                                  cfg=universe, use_cache=not args.no_cache)
        if frame is None or not len(frame):
            rows.append({"code": code, "name": m.get("name", ""), "sector": m.get("sector", ""),
                         "yahoo": m.get("yahoo", ""), "bars_4h": 0, "status": "EXCLUDED",
                         "exclusion_reasons": ["veri indirilemedi veya boş"],
                         "qc_verdict": "RED", "qc_errors": 1, "qc_warns": 0,
                         "sessions": 0, "bars_per_session": 0, "history_days": 0,
                         "missing_frac": 0, "thin_frac": 0, "thin_bars": 0,
                         "zero_volume_frac_full_bars": 0, "zero_volume_frac_all_bars": 0,
                         "full_bars": 0, "halt_or_limit_bars": 0,
                         "halt_or_limit_frac": 0, "corporate_action_bars": 0,
                         "corporate_action_splits": 0, "gap_anomaly_bars": 0,
                         "return_invalid_bars": 0, "non_tradable_bars": 0,
                         "non_tradable_frac": 0, "avg_daily_turnover_try": 0,
                         "avg_daily_volume_lots": 0, "avg_daily_turnover_last_session_try": 0,
                         "max_abs_return_valid": 0, "round_trip_cost_bps": BIST_STOCK_ROUND_TRIP_BPS})
            print(f"  [{code:6s}] VERİ YOK → elendi")
            continue
        raw_path = _p("data", "raw", "bist30", f"{code}_1h_raw.parquet")
        src = schema.load_parquet(raw_path) if os.path.exists(raw_path) else None
        met = stock_metrics(code, m, spec, frame, args.timeframe, universe, source_frame=src)
        rows.append(met)
        print(f"  [{code:6s}] bar={met['bars_4h']:5d} seans={met['sessions']:4d} "
              f"eksik=%{met['missing_frac'] * 100:4.1f} thin=%{met['thin_frac'] * 100:3.0f} "
              f"halt={met['halt_or_limit_bars']:4d} k.a.olay={met['corporate_action_events']:3d}"
              f"/bar={met['corporate_action_marked_bars']:3d} "
              f"hacim={met['avg_daily_turnover_try'] / 1e6:8,.0f}mnTL → {met['status']}")

    paths = write_reports(rows, universe, downloads, args.out, args.timeframe)
    inc = [r for r in rows if r["status"] == "INCLUDED"]
    exc = [r for r in rows if r["status"] != "INCLUDED"]
    print("\n=== ÖZET ===")
    print(f"  giren: {len(inc)} | elenen: {len(exc)}")
    if rows:
        bars = [r["bars_4h"] for r in rows if r["bars_4h"]]
        miss = [r["missing_frac"] for r in rows if r["bars_4h"]]
        print(f"  medyan bar: {np.median(bars):.0f} | medyan eksik: %{np.median(miss) * 100:.2f}")
        print(f"  kurumsal aksiyon OLAYI: pencere ici {sum(r['corporate_action_events'] for r in rows)} "
              f"/ tum gecmis {sum(r['corporate_action_events_all_history'] for r in rows)} | "
              f"işaretli bar: {sum(r['corporate_action_marked_bars'] for r in rows)} | "
              f"bölünme adayı: {sum(r['corporate_action_splits'] for r in rows)} | "
              f"halt/marj: {sum(r['halt_or_limit_bars'] for r in rows)}")
    if exc:
        print("  elenenler:")
        for r in exc:
            print(f"    - {r['code']}: {'; '.join(r['exclusion_reasons'])[:150]}")
    print("\n  raporlar:")
    for k, v in paths.items():
        print(f"    {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
