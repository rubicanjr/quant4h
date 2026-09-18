"""M11-DASH — yerel terminal dashboard (salt RENDERER · watch_only).

Paneller (koyu tema, OpenTerminal-benzeri yerleşim):
  header  : watch_only banner + son güncelleme + QC kararları
  REJİM   : varlık başına trend|vol + long/short_ok + XU030 bağlam (close vs EMA200)
  SEVİYE  : swing low/high · Donchian(20) · yapısal stop_long · MOMENTUM (σ)
  SİNYAL  : son final sinyaller (ham tetik → kapılar → final, capped) + 30g sayaç
  CADENCE : son bildirim dosyası + SAĞLIK satırı + slot tablosu + son fetch
  LOOK    : look #2 geri sayımı (ops_runbook §B) + kota notu

VERİ: YALNIZ yerel artefaktlar (data/processed frame'leri = Python motorunun
çıktısı · reports/qc_report.json · reports/cadence/*). Ağ varsayılan KAPALI;
`--fetch` runbook rate kapısına (>=200 dk, cadence state) bağlıdır ve TAM
zinciri koşar (cadence_4h_status.maybe_fetch ile TEK kaynak). Bu script hiçbir
indikatör/hesap ÜRETMEZ — kolonları OLDUĞU GİBİ çizer (renderer).

SINIRLAR: emir YOK · tavsiye YOK · **EYLEM: YOK sabit** · hüküm/seçim/look
etkisi YOK · look hakkı TÜKETMEZ. UNTESTED-VIZ DEĞİL: görsel katman yok,
metin renderer'ı; doğruluk kaynağı Python motoru kalır.

Çalıştırma:
    python3 -W ignore scripts/run_dash.py                 # Live TUI (q/CTRL-C çıkış)
    python3 -W ignore scripts/run_dash.py --once          # tek kare bas (test/CI)
    python3 -W ignore scripts/run_dash.py --fetch --once  # rate-kapılı tazeleme ile
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
from datetime import date, datetime, timezone, timedelta
from typing import Dict, Optional

import pandas as pd
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))
sys.path.insert(0, _HERE)

import run_exit_grid as G  # noqa: E402  (frame kaynağı: capped P0xA0 — TEK kaynak)
from cadence_4h_status import (FETCH_GATE_MIN, SLOTS_BIST, SLOTS_CORE,  # noqa: E402
                               TZ_LOCAL, load_state, maybe_fetch, save_state)

ROOT = G.ROOT
ASSETS = ("BTC", "GOLD", "SILVER", "BIST30")
NETWORK_DEFAULT = False                       # M11 sınırı: ağ varsayılan KAPALI
NEXT_LOOK_DATE = date(2026, 12, 17)           # ops_runbook §B: look #2 EN ERKEN tarih
LOOK_NOTE = ("look #2 · kota 2026: 3/4 kaldı (look #1 = Aşama 9, 2026-09-17) · "
             "dashboard look hakkı TÜKETMEZ")
BANNER = ("quant4h watch_only — trade YOK · emir YOK · tavsiye YOK · "
          "EYLEM: YOK · hüküm/seçim/look etkisi YOK")


def load_frames(tf: str = "4h") -> Dict[str, pd.DataFrame]:
    return {k: G._signals_for(k, tf, False, None, "A0") for k in ASSETS}


def qc_map() -> Dict[str, Dict]:
    p = os.path.join(ROOT, "reports", "qc_report.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        q = json.load(fh)
    out = {a.get("asset_key"): a for a in (q.get("assets") or []) if isinstance(a, dict)}
    out["__generated_at__"] = q.get("generated_at", "?")
    return out


def last_cadence() -> Dict[str, str]:
    files = sorted(glob.glob(os.path.join(ROOT, "reports", "cadence", "*.md")))
    if not files:
        return {"name": "(bildirim yok)", "saglik": "—", "rejim": "—", "sinyal": "—"}
    p = files[-1]
    txt = open(p, encoding="utf-8").read()
    def grab(tag: str) -> str:
        for line in txt.splitlines():
            if line.startswith(f"- **{tag}"):
                return line[:150]
        return "—"
    return {"name": os.path.basename(p), "saglik": grab("SAĞLIK"),
            "rejim": grab("REJİM"), "sinyal": grab("SİNYAL")}


def _yn(v) -> str:
    try:
        return "✓" if bool(v) else "✗"
    except Exception:                                        # noqa: BLE001
        return "?"


def build_layout(frames: Dict[str, pd.DataFrame], qc: Dict[str, Dict],
                 cad: Dict[str, str], now_local: datetime, width: int) -> Layout:
    st = load_state()
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(Layout(name="left", ratio=1), Layout(name="right", ratio=1))
    layout["left"].split_column(Layout(name="rejim"), Layout(name="seviye"))
    layout["right"].split_column(Layout(name="sinyal", ratio=3),
                                 Layout(name="cadence", ratio=2),
                                 Layout(name="look", ratio=1))

    qcg = qc.get("__generated_at__", "?")
    head = Text()
    head.append("◉ ", style="bold red")
    head.append(BANNER + "\n", style="bold white on red")
    head.append(f"son güncelleme: QC {str(qcg)[:16]} · yerel saat {now_local:%Y-%m-%d %H:%M} "
                f"(UTC+3) · veri: YEREL artefaktlar · ağ: KAPALI (varsayılan)",
                style="dim")
    verdicts = "  ".join(f"{k}:{str(qc.get(k, {}).get('verdict', '?')).split(' ')[0]}" for k in ASSETS)
    head.append(f"  ·  QC: {verdicts}", style="yellow")
    layout["header"].update(Panel(head, title="header", border_style="red"))

    t = Table(box=None, pad_edge=False, show_header=True, header_style="bold cyan")
    for c in ("varlık", "rejim", "L/S ok", "bağlam (XU030)"):
        t.add_column(c)
    for k in ASSETS:
        f = frames[k]
        r = f.iloc[-1]
        ctx = "—"
        if k == "BIST30":
            try:
                c_, e_ = float(r["close"]), float(r["ema_trend"])
                ctx = "ÜSTÜNDE→long AÇIK" if c_ > e_ else "ALTINDA→long KAPALI"
            except (KeyError, TypeError, ValueError):
                ctx = "BELİRSİZ→KAPALI"
        t.add_row(k, str(r.get("regime", "?")),
                  f"{_yn(r.get('long_regime_ok'))}/{_yn(r.get('short_regime_ok'))}", ctx)
    layout["rejim"].update(Panel(t, title="REJİM / BAĞLAM", border_style="cyan"))

    t2 = Table(box=None, pad_edge=False, show_header=True, header_style="bold green")
    for c in ("varlık", "swing L/H", "donch L/H", "stop_long", "mom σ", "mom ok"):
        t2.add_column(c)
    for k in ASSETS:
        r = frames[k].iloc[-1]
        def f2(x):
            try:
                return f"{float(x):,.0f}"
            except (TypeError, ValueError):
                return "—"
        t2.add_row(k, f"{f2(r.get('last_swing_low'))}/{f2(r.get('last_swing_high'))}",
                   f"{f2(r.get('donchian_low'))}/{f2(r.get('donchian_high'))}",
                   f2(r.get("stop_long")), f"{float(r.get('mom', float('nan'))):+.2f}"
                   if pd.notna(r.get("mom")) else "—", _yn(r.get("momentum_ok")))
    layout["seviye"].update(Panel(t2, title="SEVİYE + MOMENTUM (σ)", border_style="green"))

    events = []
    for k in ASSETS:
        f = frames[k]
        ts = pd.to_datetime(f["timestamp_utc"], utc=True)
        mask = f["long_signal"].astype(bool) | f["short_signal"].astype(bool)
        for i in f.index[mask]:
            r = f.loc[i]
            side = "L" if bool(r["long_signal"]) else "S"
            events.append((ts[i], k, side,
                           f"trig✓ rej{_yn(r.get('long_regime_ok'))} "
                           f"trad{_yn(not r.get('non_tradable', False))} "
                           f"ret{_yn(r.get('return_valid'))} "
                           f"mom{_yn(r.get('momentum_ok'))} "
                           f"stop{_yn(r.get('stop_valid_long'))} → final✓"))
    events.sort(key=lambda e: e[0], reverse=True)
    t3 = Table(box=None, pad_edge=False, show_header=True, header_style="bold magenta")
    for c in ("tarih (UTC)", "varlık", "yön", "ham→kapılar→final"):
        t3.add_column(c)
    for e in events[:10]:
        t3.add_row(f"{e[0]:%m-%d %H:%M}", e[1], e[2], e[3])
    n30 = sum(1 for e in events if e[0] >= ts.max() - pd.Timedelta(days=30))
    t3.add_row("", "", "", f"[dim]son 30g final sinyal: {n30}[/dim]")
    layout["sinyal"].update(Panel(t3, title="SİNYAL log'u (capped, ham→kapılar→final)",
                                  border_style="magenta"))

    cad_txt = Text()
    cad_txt.append(f"son bildirim: {cad['name']}\n", style="bold")
    cad_txt.append(cad["saglik"] + "\n", style="dim")
    cad_txt.append(f"slotlar: BIST {'/'.join(SLOTS_BIST)} · core {'/'.join(SLOTS_CORE[:3])}…\n",
                   style="dim")
    lf = st.get("last_fetch_utc")
    cad_txt.append(f"son fetch: {str(lf)[:16] if lf else '(yok)'} · rate kapısı ≥{FETCH_GATE_MIN} dk",
                   style="dim")
    layout["cadence"].update(Panel(cad_txt, title="CADENCE (son bildirim)", border_style="blue"))

    days = (NEXT_LOOK_DATE - now_local.date()).days
    lk = Text()
    lk.append(f"look #2'ye: {max(days, 0)} gün", style="bold yellow")
    lk.append(f" ({NEXT_LOOK_DATE.isoformat()} EN ERKEN)\n")
    lk.append(LOOK_NOTE + "\n", style="dim")
    lk.append("ön-kayıtsız look = protokol ihlali (runbook §B)", style="dim red")
    layout["look"].update(Panel(lk, title="LOOK TAKVİMİ", border_style="yellow"))

    foot = Text("EYLEM: YOK (sabit) · bu panel karar ÜRETMEZ · kaynak: Python motoru "
                "kolonları (renderer) · UNTESTED-VIZ değildir: görsel katman yok",
                style="bold white on black")
    layout["footer"].update(Panel(foot, border_style="white"))
    return layout


def render_once(now: Optional[datetime] = None, width: int = 132) -> str:
    now_local = (now or datetime.now(timezone.utc)).astimezone(TZ_LOCAL)
    frames = load_frames()
    qc = qc_map()
    cad = last_cadence()
    console = Console(record=True, width=width, height=40, force_terminal=False,
                      file=io.StringIO(), no_color=False)
    console.print(build_layout(frames, qc, cad, now_local, width))
    return console.export_text()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="tek kare bas ve çık (test/CI)")
    ap.add_argument("--refresh", type=int, default=60, help="Live yenileme sn (varsayılan 60)")
    ap.add_argument("--fetch", action="store_true",
                    help=f"başlamadan rate-kapılı tazeleme (≥{FETCH_GATE_MIN} dk; TAM zincir)")
    ap.add_argument("--width", type=int, default=132)
    args = ap.parse_args()

    if args.fetch:
        now_utc = datetime.now(timezone.utc)
        st = load_state()
        note = maybe_fetch(st, now_utc)
        save_state(st)
        print(f"[fetch] {note}")
        if any(str(v.get("verdict", "")).startswith("RED") for k, v in qc_map().items()
               if isinstance(v, dict) and k != "__generated_at__"):
            print("FAIL-CLOSED: QC RED — dashboard bayat veriyle uyarı gösterir")

    if args.once:
        print(render_once(width=args.width))
        return 0

    console = Console(width=args.width)
    from rich.live import Live
    with Live(console=console, refresh_per_second=1 / max(args.refresh, 5), screen=True) as live:
        try:
            while True:
                live.update(build_layout(load_frames(), qc_map(), last_cadence(),
                                         datetime.now(timezone.utc).astimezone(TZ_LOCAL),
                                         args.width))
                import time as _t
                _t.sleep(max(args.refresh, 5))
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
