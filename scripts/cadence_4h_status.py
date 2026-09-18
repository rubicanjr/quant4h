"""M9-CADENCE (direktif 2026-09-18) — 4H mum kapanışlarına göre DURUM bildirimi.

watch_only · trade YOK · emir YOK · tavsiye YOK · hüküm YOK · look hakkı TÜKETMEZ.
Manuel tetiklenir (scheduler YOK — ops_runbook §A-cadence).

Zamanlama (Europe/Istanbul = UTC+3, Türkiye'de DST yok → yıl boyu sabit):
  * BIST30            : 11:00, 15:00 (4H) + 18:00 (seans sonu 1H)
  * BTC/GOLD/SILVER   : 03:00, 07:00, 11:00, 15:00, 19:00, 23:00 (4H)
  * Her bildirim: son mum TAMAMLANDIĞINDA (15 dk tolerans).

DÜRÜSTLÜK NOTU (olduğu gibi uygulandı, direktif bağlayıcıdır): BIST30'un
11:00/15:00 slotları v1.1 ızgarasının 4H kapanışlarıyla (lokal 14:00/18:00)
ÇAKIŞMAZ. Script hiçbir slot için mum UYDURMAZ: her zaman "slot anında
KAPALI olan son mum" + yaşını raporlar; uyumsuz slotlarda referans mum bir
önceki seansın kapanışı olur ve yaş açıkça yazılır (kullanıcı slot revizyonu
isterse tablo aşağıdaki SLOTS sabitinden değiştirilir — onay gerektirir).

Şablon (direktif B): SAĞLIK → REJİM → SEVİYE → MOMENTUM → SİNYAL → EYLEM.

Çalıştırma:
  python3 -W ignore scripts/cadence_4h_status.py                     # en yakın geçmiş slot
  python3 -W ignore scripts/cadence_4h_status.py --slot 15:00 --date 2026-09-18
  python3 -W ignore scripts/cadence_4h_status.py --fetch             # veri tazeleyerek (rate-kapılı)
Çıktı: reports/cadence/YYYY-MM-DD_HHMM.md (+ stdout)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))
sys.path.insert(0, _HERE)

import run_exit_grid as G  # noqa: E402  (_signals_for + RB yardımcıları; P0×A0 capped frame)

ROOT = G.ROOT
RB = G.RB
CADENCE_DIR = os.path.join(ROOT, "reports", "cadence")
STATE_PATH = os.path.join(CADENCE_DIR, ".state.json")

TZ_LOCAL = timezone(timedelta(hours=3), name="Europe/Istanbul (UTC+3, DST yok)")
GRACE_MIN = 15                     # direktif A.3: mum kapanışı + 15 dk tolerans
FETCH_GATE_MIN = 200               # --fetch için asgari ara (Yahoo rate-limit dersi, runbook v1.1)

# Slot tabloları (LOKAL saat, direktif A.1/A.2 — birebir)
SLOTS_BIST = ("11:00", "15:00", "18:00")          # 18:00 = seans sonu (1H kaynak; frame 4H)
SLOTS_CORE = ("03:00", "07:00", "11:00", "15:00", "19:00", "23:00")
CORE_ASSETS = ("BTC", "GOLD", "SILVER")
# frozen (checkpoint) satır sayıları — ilk çalıştırmada "+X bar" referansı
FROZEN_ROWS = {"BTC": 19888, "GOLD": 3606, "SILVER": 3606, "BIST30": 1435}
# BAYATLIK eşikleri (saat): slot anında frame'in son mum kapanışı bu eşiği
# aşıyorsa ⚠️ BAYAT bayrağı (fail-closed). Eşikler TAKVİM-DUYARSIZDIR
# (hafta sonu/tatil/metallerdeki bakım molası bilerek toleransa dahil edildi);
# bayrak bir IDDİA değil, "veri taze değil — fetch gerekir" uyarısıdır.
STALE_AFTER_H = {"BTC": 6.0, "GOLD": 28.0, "SILVER": 28.0, "BIST30": 28.0}


def groups_for_slot(slot: str) -> List[str]:
    g = []
    if slot in SLOTS_BIST:
        g.append("BIST30")
    if slot in SLOTS_CORE:
        g.append("CORE")
    return g


def resolve_slot(now_local: datetime, want_date: Optional[str], want_slot: Optional[str]) -> Tuple[datetime, str]:
    """(slot yerel datetime, slot HH:MM). Verilen slot tabloda olmalı; verilmezse
    şimdiye kadar olan EN YAKIN slot (tüm slotlar birleşik)."""
    all_slots = sorted(set(SLOTS_BIST) | set(SLOTS_CORE))
    if want_slot:
        if want_slot not in all_slots:
            raise ValueError(f"slot '{want_slot}' tabloda yok: {all_slots}")
        d = datetime.strptime(want_date, "%Y-%m-%d").date() if want_date else now_local.date()
        hh, mm = map(int, want_slot.split(":"))
        return datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ_LOCAL), want_slot
    base = now_local.date() if not want_date else datetime.strptime(want_date, "%Y-%m-%d").date()
    best = None
    for day in (base - timedelta(days=1), base):
        for s in all_slots:
            hh, mm = map(int, s.split(":"))
            cand = datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ_LOCAL)
            if cand <= now_local and (best is None or cand > best[0]):
                best = (cand, s)
    if best is None:
        raise ValueError("geçmiş slot bulunamadı — --slot/--date verin")
    return best


def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {"last_fetch_utc": None, "runs": [], "assets": {}}


def save_state(st: Dict[str, Any]) -> None:
    os.makedirs(CADENCE_DIR, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=2, default=str)


def maybe_fetch(st: Dict[str, Any], now_utc: datetime) -> str:
    """--fetch: rate-kapılı TAM zincir (fail-closed: kapı geçilmeden ÇEKİLMEZ).

    Zincir (runbook §A sırası BAĞLAYICI): run_data_qc (resample→adjust→QC) →
    run_regime_report → run_levels_report → run_momentum_report →
    run_signal_report. QC-only fetch frame'leri TAZELEMEZ (M9 demo2 bulgusu)."""
    last = st.get("last_fetch_utc")
    if last:
        dt = (now_utc - pd.Timestamp(last).tz_convert("UTC").to_pydatetime()).total_seconds() / 60.0
        if dt < FETCH_GATE_MIN:
            return (f"RED: son fetch'ten {dt:.0f} dk geçti (< {FETCH_GATE_MIN} dk kapısı) — "
                    f"Yahoo rate-limit dersi (runbook v1.1). Cache ile devam edildi.")
    os.makedirs(CADENCE_DIR, exist_ok=True)
    log = os.path.join(CADENCE_DIR, "last_fetch.log")
    steps = [
        [sys.executable, "-W", "ignore", os.path.join(ROOT, "scripts", "run_data_qc.py"),
         "--assets", "BTC", "GOLD", "SILVER", "BIST30",
         "--start", "2017-08-17", "--timeframe", "4h", "--min-rows", "1500", "--no-cache"],
        [sys.executable, "-W", "ignore", os.path.join(ROOT, "scripts", "run_regime_report.py")],
        [sys.executable, "-W", "ignore", os.path.join(ROOT, "scripts", "run_levels_report.py")],
        [sys.executable, "-W", "ignore", os.path.join(ROOT, "scripts", "run_momentum_report.py")],
        [sys.executable, "-W", "ignore", os.path.join(ROOT, "scripts", "run_signal_report.py")],
    ]
    with open(log, "w", encoding="utf-8") as fh:
        for cmd in steps:
            fh.write(f"\n===== {' '.join(os.path.basename(c) if c.endswith('.py') else c for c in cmd)} =====\n")
            fh.flush()
            rc = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=ROOT)
            if rc != 0:
                return (f"UYARI: zincir adımı exit {rc} — {os.path.basename(cmd[-1] if cmd[-1].endswith('.py') else cmd[2])}; "
                        f"log: reports/cadence/last_fetch.log (mevcut frame'lerle devam, BAYAT bayrakları geçerli)")
    st["last_fetch_utc"] = now_utc.isoformat()
    return "fetch+zincir OK (run_data_qc --no-cache --start 2017-08-17 → regime → levels → momentum → signal; log: reports/cadence/last_fetch.log)"


def qc_red_assets() -> List[str]:
    return [k for k, v in qc_verdicts().items() if str(v.get("verdict", "")).startswith("RED")]


def qc_verdicts() -> Dict[str, Dict[str, Any]]:
    p = os.path.join(ROOT, "reports", "qc_report.json")
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as fh:
        q = json.load(fh)
    return {a.get("asset_key"): a for a in (q.get("assets") or []) if isinstance(a, dict)}


def qc_verdicts_generated_at() -> str:
    p = os.path.join(ROOT, "reports", "qc_report.json")
    if not os.path.exists(p):
        return "?"
    with open(p, "r", encoding="utf-8") as fh:
        q = json.load(fh)
    return str(q.get("generated_at", "?"))[:16]


def _bool(v) -> str:
    try:
        return "✓" if bool(v) else "✗"
    except Exception:                                        # noqa: BLE001
        return "?"


def asset_section(key: str, slot_dt_local: datetime, now_utc: datetime,
                  st: Dict[str, Any]) -> List[str]:
    frame = G._signals_for(key, "4h", False, None, "A0")   # capped akış, A0 anchor, P0 sözleşmesi
    if frame is None or not len(frame):
        return [f"## {key}", "", "**VERİ YOK** — frame üretilemedi (fail-closed: bölüm atlandı).", ""]
    ts = pd.to_datetime(frame["timestamp_utc"], utc=True)
    close = ts + pd.Timedelta(hours=4)                      # mum kapanışı = etiket(open) + 4h
    slot_utc = slot_dt_local.astimezone(timezone.utc)
    ref_mask = close <= slot_utc                            # slot anında KAPALI olan mumlar
    if not ref_mask.any():
        return [f"## {key}", "", "**REFERANS MUM YOK** (slot öncesi kapalı bar bulunamadı).", ""]
    ref_i = int(np.flatnonzero(ref_mask.to_numpy())[-1])
    r = frame.iloc[ref_i]
    ref_close = close.iloc[ref_i]
    age_h = (slot_utc - ref_close).total_seconds() / 3600.0
    last_close = close.iloc[-1]
    stale_h = STALE_AFTER_H.get(key, 28.0)
    stale = age_h > stale_h                                 # takvim-duyarsız eşik (bkz. STALE_AFTER_H)
    grace = timedelta(0) <= (now_utc - slot_utc) < timedelta(minutes=GRACE_MIN)

    prev = st.get("assets", {}).get(key, {})
    base_rows = prev.get("rows", FROZEN_ROWS.get(key))
    new_bars = len(frame) - int(base_rows) if base_rows else 0

    qc = qc_verdicts().get(key, {})
    qc_gen = qc_verdicts_generated_at()
    L: List[str] = []
    L.append(f"## {key}")
    L.append("")
    # 4) SAĞLIK
    L.append(f"- **SAĞLIK:** QC `{qc.get('verdict', '?')}` (QC raporu: {qc_gen}) · "
             f"frame son bar **{str(ts.iloc[-1])[:16]} UTC** (kapanış {str(last_close)[:16]}) · "
             f"**{new_bars:+d} bar** (önceki bildirim/frozen baseline) · "
             f"referans mum kapanışı {str(ref_close)[:16]} UTC (slot'a yaşı {age_h:.1f}h)"
             + (" · tolerans penceresi (15 dk) içinde" if grace else "")
             + (f" · ⚠️ **BAYAT** (yaş {age_h:.1f}h > eşik {stale_h:.0f}h, takvim-duyarsız) — "
                f"`--fetch` gerekir; bu bildirim piyasa durumu İDDİASI içermez"
                if stale else ""))
    # 5) REJİM
    L.append(f"- **REJİM:** `{r.get('regime', '?')}` · long_ok={_bool(r.get('long_regime_ok'))} "
             f"short_ok={_bool(r.get('short_regime_ok'))} "
             f"(trend=`{r.get('trend_state','?')}`, vol=`{r.get('vol_state','?')}`)")
    # 6) SEVİYE
    def f4(x):
        try:
            return f"{float(x):,.2f}"
        except (TypeError, ValueError):
            return "—"
    ctx = ""
    if key == "BIST30":
        try:
            c_val, e_val = float(r.get("close")), float(r.get("ema_trend"))
            if not (np.isfinite(c_val) and np.isfinite(e_val)):
                ctx_state = "BELİRSİZ (fail-closed: hisse long izni KAPALI)"
            else:
                ctx_state = ("ÜSTÜNDE (hisse long izni AÇIK)" if c_val > e_val
                             else "ALTINDA (hisse long izni KAPALI)")
            ctx = f" · **bağlam:** close {f4(c_val)} vs EMA200 {f4(e_val)} → {ctx_state}"
        except (TypeError, ValueError):
            ctx = " · **bağlam:** okunamadı (fail-closed: izin KAPALI varsayılır)"
    L.append(f"- **SEVİYE:** destek: swing_low {f4(r.get('last_swing_low'))} · donchian_low {f4(r.get('donchian_low'))} · "
             f"direnç: swing_high {f4(r.get('last_swing_high'))} · donchian_high {f4(r.get('donchian_high'))} · "
             f"yapısal stop_long {f4(r.get('stop_long'))} (valid={_bool(r.get('stop_valid_long'))}){ctx}")
    # 7) MOMENTUM
    mv = r.get("mom")
    L.append(f"- **MOMENTUM:** mom = {f4(mv)} σ (ATR-normalize ROC, n=10) · valid={_bool(r.get('momentum_valid'))} "
             f"long_ok={_bool(r.get('momentum_ok'))}")
    # 8) SİNYAL (referans mum: ham → kapılar → final, capped)
    L.append(f"- **SİNYAL** (referans mum {str(ts.iloc[ref_i])[:16]}): "
             f"trigger L/S={_bool(r.get('trigger_long'))}/{_bool(r.get('trigger_short'))} → "
             f"ham L/S={_bool(r.get('long_signal_raw'))}/{_bool(r.get('short_signal_raw'))} → "
             f"kapılar[rejim={_bool(r.get('long_regime_ok'))} tradable={_bool(not r.get('non_tradable', False))} "
             f"ret_ok={_bool(r.get('return_valid'))} mom={_bool(r.get('momentum_ok'))} "
             f"stop={_bool(r.get('stop_valid_long'))}] → "
             f"**final L/S={_bool(r.get('long_signal'))}/{_bool(r.get('short_signal'))}** "
             f"(bastırma: pozisyon={_bool(r.get('suppressed_by_position'))} cooldown={_bool(r.get('suppressed_by_cooldown'))})")
    d24 = ts >= (slot_utc - pd.Timedelta(hours=24))
    n24 = int((frame.loc[d24, "long_signal"].astype(bool) | frame.loc[d24, "short_signal"].astype(bool)).sum())
    L.append(f"  - son 24h final sinyal (capped): **{n24}**")
    L.append("")
    return L


def build_report(slot_dt: datetime, slot: str, fetch_note: Optional[str],
                 now_utc: datetime) -> Tuple[str, List[str]]:
    st = load_state()
    groups = groups_for_slot(slot)
    assets: List[str] = []
    if "BIST30" in groups:
        assets.append("BIST30")
    if "CORE" in groups:
        assets.extend(CORE_ASSETS)
    L: List[str] = []
    L.append(f"# 4H durum bildirimi — {slot_dt.strftime('%Y-%m-%d %H:%M')} (UTC+3) · slot `{slot}`")
    L.append("")
    L.append(f"**watch_only · trade YOK · emir YOK · tavsiye YOK · hüküm YOK · look hakkı TÜKETMEZ** · "
             f"gruplar: {', '.join(groups)} · üretim: {now_utc.isoformat(timespec='seconds')}")
    L.append("")
    if fetch_note:
        L.append(f"> fetch: {fetch_note}")
        L.append("")
    if (slot in SLOTS_BIST) and slot != "18:00":
        L.append("> ⚠️ DÜRÜSTLÜK NOTU: bu BIST30 slotu v1.1 ızgara kapanışıyla (lokal 14:00/18:00) "
                 "çakışmıyor; referans mum = slot anında KAPALI olan son mum (yaşı aşağıda). "
                 "Slot tablosu direktifle birebirdir; revizyon kullanıcı onayı gerektirir.")
        L.append("")
    for a in assets:
        L.extend(asset_section(a, slot_dt, now_utc, st))
    # 9) EYLEM — sabit
    L.append("## EYLEM")
    L.append("")
    L.append("**YOK** — watch_only · Aşama 9 hükmü: **GEÇTİ = 0** (tüm varlıklar watch_only) · "
             "look #2 en erken: **17 Aralık 2026** (ops_runbook §B, ön-kayıtlı) · "
             "bu bildirim look hakkı tüketmez, hükme dokunmaz, trade ÖNERMEZ.")
    L.append("")
    L.append("---")
    L.append("*İzleme artefaktıdır; yatırım tavsiyesi DEĞİLDİR. Veri taze değilse (STALE) "
             "bildirim yalnız altyapı kanıtıdır, piyasa durumu İDDİASI içermez.*")
    fname = f"{slot_dt.strftime('%Y-%m-%d_%H%M')}.md"
    # state güncelle (satır sayıları + son bar) — bir sonraki "+X bar" referansı
    for a in assets:
        frame = G._signals_for(a, "4h", False, None, "A0")
        if frame is not None and len(frame):
            st.setdefault("assets", {})[a] = {"rows": len(frame),
                                              "last_ts": str(pd.to_datetime(frame["timestamp_utc"], utc=True).iloc[-1])}
    st.setdefault("runs", []).append({"slot_local": str(slot_dt), "file": fname,
                                      "groups": groups, "generated_utc": now_utc.isoformat(timespec="seconds")})
    save_state(st)
    return fname, L


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=None, help="lokal tarih YYYY-MM-DD (varsayılan: bugün)")
    ap.add_argument("--slot", default=None, help="HH:MM (slot tablosundan; varsayılan: en yakın geçmiş slot)")
    ap.add_argument("--fetch", action="store_true",
                    help=f"bildirimden önce canlı çekim (rate kapısı: >= {FETCH_GATE_MIN} dk ara)")
    ap.add_argument("--out", default=CADENCE_DIR)
    args = ap.parse_args()

    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(TZ_LOCAL)
    slot_dt, slot = resolve_slot(now_local, args.date, args.slot)
    if slot_dt > now_local:
        print(f"UYARI: slot ({slot_dt}) henüz GELMEDİ — rapor erken üretiliyor (fail-closed notlarla)")
    fetch_note = None
    if args.fetch:
        st0 = load_state()
        fetch_note = maybe_fetch(st0, now_utc)
        save_state(st0)
        print(f"[fetch] {fetch_note}")
    # FAIL-CLOSED YAYIM KURALI (runbook §A ile aynı): kapsamdaki herhangi bir
    # varlık QC RED ise durum bildirimi YAYIMLANMAZ; yerine SORUN NOTU üretilir.
    scope: List[str] = []
    if "BIST30" in groups_for_slot(slot):
        scope.append("BIST30")
    if "CORE" in groups_for_slot(slot):
        scope.extend(CORE_ASSETS)
    reds = sorted(set(qc_red_assets()) & set(scope))
    if reds:
        fname = f"{slot_dt.strftime('%Y-%m-%d_%H%M')}.md"
        note = [
            f"# 4H durum bildirimi — {slot_dt.strftime('%Y-%m-%d %H:%M')} (UTC+3) · slot `{slot}`",
            "",
            "## ⛔ SORUN NOTU — BİLDİRİM YAYIMLANMADI (fail-closed)",
            "",
            f"QC RED varlık(lar): **{', '.join(reds)}** (kaynak: `reports/qc_report.json`, "
            f"{qc_verdicts_generated_at()}). Runbook §A kuralı: QC RED iken durum bildirimi "
            "YAYIMLANMAZ; piyasa durumu bölümü üretilmez (bayat/bozuk veriyle izleme yanıltıcıdır).",
            "",
            "Aksiyon: fetch logu (`reports/cadence/last_fetch.log`) ve `reports/qc_report.md` "
            "incelenmeli; veri kaynağı sorunu çözülünce bildirim yeniden üretilir. "
            "(watch_only · trade YOK · look hakkı TÜKETMEZ.)",
        ]
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, fname), "w", encoding="utf-8") as fh:
            fh.write("\n".join(note) + "\n")
        print("\n".join(note))
        print(f"\n[sorun notu] {os.path.relpath(os.path.join(args.out, fname), ROOT)}")
        return 3
    fname, lines = build_report(slot_dt, slot, fetch_note, now_utc)
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, fname)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[bildirım dosyası] {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
