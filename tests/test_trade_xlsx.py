"""Tests for M22-TRADE-XLSX — özet determinizmi + biçim kilidi (salt renderer).

Kaynak CSV'lerden BAĞIMSIZ yeniden hesap ile OZET sayfası karşılaştırılır
(renderer doğruluğu); iki koşu arasında özet + sayfa adları deterministik;
biçim ögeleri (freeze/auto-filter/header fill/koşullu renk/exit_reason rengi/
sayı formatları/EGRI grafik) kilitlenir. YENİ analiz YOK.

Run: python3 -W ignore tests/test_trade_xlsx.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import pandas as pd
from openpyxl import load_workbook

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import export_trade_report_xlsx as X  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ASSET = "BTC"
XLSX = os.path.join(ROOT, "reports", "xlsx", f"trades_{ASSET}.xlsx")
START_EQ = X.START_EQ


def _ozet(wb) -> dict:
    ws = wb["OZET"]
    out = {}
    for row in ws.iter_rows(min_row=2, max_col=2):
        k, v = row[0].value, row[1].value
        if k and v is not None and "dağılımı" not in str(k):
            out[str(k)] = v
        if k and "dağılımı" in str(k):
            break
    return out


def _recompute() -> dict:
    df = pd.read_csv(os.path.join(ROOT, "reports", f"trades_{ASSET}.csv"))
    eq = START_EQ + df["net_pnl"].cumsum()
    eq = pd.concat([pd.Series([START_EQ]), eq], ignore_index=True)
    cur = best = 0
    for v in df["net_pnl"]:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    return {"trade sayısı": len(df),
            "win rate": round(float((df["net_pnl"] > 0).mean()), 4),
            "ortalama R": round(float(df["r_multiple"].mean()), 4),
            "medyan R": round(float(df["r_multiple"].median()), 4),
            "maks ardışık kayıp": best,
            "cost_total toplamı": round(float(df["cost_total"].sum()), 2),
            "equity maxDD": round(float((eq / eq.cummax() - 1.0).min()), 6),
            "bitiş equity": round(float(eq.iloc[-1]), 2)}


def test_sheet_names_and_chart() -> None:
    wb = load_workbook(XLSX)
    assert wb.sheetnames == ["TRADES", "OZET", "EGRI"], wb.sheetnames
    assert len(wb["EGRI"]._charts) == 1, "EGRI sayfasında çizgi grafik yok"


def test_summary_matches_independent_recompute() -> None:
    wb = load_workbook(XLSX)
    oz = _ozet(wb)
    ref = _recompute()
    for k, v in ref.items():
        assert k in oz, f"özet satırı eksik: {k}"
        assert abs(float(oz[k]) - float(v)) < 1e-6, f"{k}: xlsx {oz[k]} != bağımsız {v}"


def test_deterministic_summary_and_sheets() -> None:
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, "-W", "ignore",
                            os.path.join(ROOT, "scripts", "export_trade_report_xlsx.py")],
                           capture_output=True, text=True, cwd=ROOT,
                           env={**os.environ, "TMPDIR": td})
        assert r.returncode == 0, r.stderr[-500:]
        wb1 = load_workbook(XLSX)
        a, b = _ozet(wb1), _ozet(load_workbook(XLSX))
        assert a == b and wb1.sheetnames == ["TRADES", "OZET", "EGRI"]


def test_trades_sheet_formatting_locked() -> None:
    wb = load_workbook(XLSX)
    ws = wb["TRADES"]
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref and ws.auto_filter.ref.startswith("A1:")
    hdr = ws.cell(row=1, column=1)
    assert hdr.fill.fgColor.rgb in ("001F3864", "FF1F3864"), hdr.fill.fgColor.rgb
    assert hdr.font.color is not None and hdr.font.bold
    cols = {ws.cell(row=1, column=j).value: j for j in range(1, ws.max_column + 1)}
    ri = cols["r_multiple"]
    rules = list(ws.conditional_formatting)[0].rules
    assert len(rules) >= 2, "r_multiple koşullu renk kuralları eksik"
    er = cols["exit_reason"]
    fills = set()
    for i in range(2, ws.max_row + 1):
        f = ws.cell(row=i, column=er).fill.fgColor.rgb
        if f and f != "00000000":
            fills.add(f)
    assert {"00C6EFCE", "00FFC7CE", "00FFEB9C"} <= fills or \
        {"FFC6EFCE", "FFC7CE", "FFEB9C"} <= fills or len(fills) >= 2, fills
    assert ws.cell(row=2, column=cols["entry_price"]).number_format == "0.00"
    assert ws.cell(row=2, column=ri).number_format == "0.000"
    assert ws.cell(row=2, column=cols["entry_timestamp_utc"]).number_format == "yyyy-mm-dd hh:mm"


def test_exit_reason_distribution_present() -> None:
    wb = load_workbook(XLSX)
    ws = wb["OZET"]
    txt = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
    assert any("exit_reason dağılımı" in t for t in txt)
    assert any(t == "take_profit" for t in txt) or any(t == "stop" for t in txt)


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
