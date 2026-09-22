"""Tests for AŞAMA 9 — walk-forward OOS protokolü (kilitli direktif 2026-09-17).

Kilitlenen garantiler:
  * pencereler `used` bloklarındançözümlenir; train < valid < test + purge/embargo boşluğu
  * trade atfı giriş zamanına göre, ayrık + gap kovası
  * seçim: argmax TRAIN expR, n>=50 şartı, deterministik tie-break, ZAYIF -> a-priori P0xA0
  * VALID sağduyu: expR<0 / CI üstü<0 / trade yok -> False (TEST koşulmaz)
  * go/no-go: ZAYIF (n<min) -> watch_only; tüm eşikler -> GEÇTİ; tek eşik ihlali -> KALDI
  * Monte Carlo deterministik (seed 42)
  * duyarlılık komşuları (profil ±1, anchor ±1) + overfit sivrilik bayrağı
  * seçim DONMADAN (selected_cells.yaml yok/hash'i bozuk) verdict REDDEDİLİR (exit 2 yolu)
  * teslimat artefaktı selected_cells.yaml şema + hash tutarlılığı
  * max_open_positions=6 senkronu (yaml + config.py)

Run: python3 -W ignore tests/test_stage9.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from types import SimpleNamespace

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import run_stage9 as S9  # noqa: E402


def _trade(entry_ts: str, r: float = 0.1, net: float = 10.0, eqb: float = 100000.0):
    return SimpleNamespace(entry_timestamp_utc=entry_ts, exit_timestamp_utc=entry_ts,
                           r_multiple=r, net_pnl=net, equity_before=eqb,
                           return_frac=net / eqb)


# ---------------------------------------------------------------------------
# pencereler + atama
# ---------------------------------------------------------------------------

def test_load_windows_used_blocks_ordered_with_gaps() -> None:
    w = S9.load_windows()
    assert w["policy_version"] == "1.1"
    for k in S9.ASSET_CLASSES:
        tr, va, te = w[k]["train"], w[k]["valid"], w[k]["test"]
        assert tr[0] < tr[1] < va[0] < va[1] < te[0] < te[1], k
        assert (va[0] - tr[1]) >= pd.Timedelta(hours=4), k     # purge+embargo boşluğu
        assert (te[0] - va[1]) >= pd.Timedelta(hours=4), k
        assert w[k]["purge_bars"] == 30 and w[k]["embargo_bars"] == 12
        assert os.path.exists(os.path.join(S9.ROOT, w[k]["frozen_file"])), k


def test_assign_windows_disjoint_with_gap_bucket() -> None:
    w = S9.load_windows()["BTC"]
    tr_mid = w["train"][0] + (w["train"][1] - w["train"][0]) / 2
    va_mid = w["valid"][0] + (w["valid"][1] - w["valid"][0]) / 2
    te_mid = w["test"][0] + (w["test"][1] - w["test"][0]) / 2
    gap_ts = w["train"][1] + pd.Timedelta(hours=4)             # purge/embargo aralığı
    trades = [_trade(str(tr_mid)), _trade(str(va_mid)), _trade(str(te_mid)), _trade(str(gap_ts))]
    b = S9.assign_windows(trades, w)
    assert (len(b["train"]), len(b["valid"]), len(b["test"])) == (1, 1, 1)
    assert len(b["gap"]) == 1
    assert sum(len(v) for v in b.values()) == len(trades)      # ayrık + kapsayıcı


# ---------------------------------------------------------------------------
# seçim + sağduyu + go/no-go
# ---------------------------------------------------------------------------

def test_select_cell_argmax_min50_and_tiebreak() -> None:
    grid = {c: {"n_trades": 10, "expectancy_r": 0.9, "profit_factor_net": 2.0} for c in S9.CELLS}
    grid["P3xA2"] = {"n_trades": 60, "expectancy_r": 0.5, "profit_factor_net": 1.5}
    grid["P1xA0"] = {"n_trades": 55, "expectancy_r": 0.7, "profit_factor_net": 1.5}
    cell, dflt, note = S9.select_cell(grid)
    assert cell == "P1xA0" and dflt is False                   # n>=50 olanlar içinde argmax
    grid2 = {c: {"n_trades": 5, "expectancy_r": 0.9} for c in S9.CELLS}
    cell2, dflt2, _ = S9.select_cell(grid2)
    assert cell2 is None and dflt2 is True                     # hepsi <50 -> SEÇİM YOK
    grid3 = {c: {"n_trades": 60, "expectancy_r": 0.3} for c in S9.CELLS}
    cell3, _, _ = S9.select_cell(grid3)
    assert cell3 == S9.CELLS[0]                                # tie -> CELLS sırası (P0xA0)


def test_valid_sanity_rules() -> None:
    assert S9.valid_sanity_check({"n_trades": 0})[0] is False
    assert S9.valid_sanity_check({"n_trades": 7, "expectancy_r": -0.32,
                                  "expR_ci95": [-0.5, -0.1]})[0] is False
    assert S9.valid_sanity_check({"n_trades": 7, "expectancy_r": 0.1,
                                  "expR_ci95": [-0.4, -0.01]})[0] is False   # CI üstü < 0
    assert S9.valid_sanity_check({"n_trades": 7, "expectancy_r": 0.1,
                                  "expR_ci95": [-0.1, 0.3]})[0] is True
    ok, note = S9.valid_sanity_check({"n_trades": 3, "expectancy_r": 0.2, "expR_ci95": None})
    assert ok is True and "CI hesaplanamadı" in note           # n<5: expR ile sınırlı sağduyu


def test_go_nogo_thresholds() -> None:
    base = {"n_trades": 120, "expectancy_r": 0.2, "expR_ci95": [0.01, 0.4],
            "profit_factor_net": 1.5, "max_dd_path_frac": -0.10}
    v, m, _ = S9.go_nogo(dict(base), 100)
    assert (v, m) == ("GEÇTİ", "paper_observe_candidate")
    v, m, _ = S9.go_nogo({**base, "n_trades": 99}, 100)
    assert v == "ZAYIF (örneklem)" and m == "watch_only"       # örneklem kapısı
    for bad in ({"expectancy_r": 0.0}, {"expR_ci95": [-0.01, 0.4]},
                {"profit_factor_net": 1.19}, {"max_dd_path_frac": -0.26}):
        v, m, reasons = S9.go_nogo({**base, **bad}, 100)
        assert v == "KALDI" and m == "watch_only" and reasons, bad
    v, _, _ = S9.go_nogo({**base, "n_trades": 149}, 150)        # basket eşiği
    assert v == "ZAYIF (örneklem)"


def test_monte_carlo_deterministic() -> None:
    trades = [_trade("2025-01-01", r=float(x), net=float(x) * 100.0)
              for x in np.linspace(-0.5, 0.8, 12)]
    a = S9.monte_carlo(trades)
    b = S9.monte_carlo(trades)
    assert a == b and a["B"] == 1000 and a["seed"] == 42
    assert 0.0 <= a["prob_maxDD_worse_than_25pct"] <= 1.0
    assert a["maxDD_p05"] <= a["maxDD_p50"] <= a["maxDD_p95"] <= 0.0
    assert "note" in S9.monte_carlo(trades[:3])                  # n<5 -> MC yok


def test_sensitivity_neighbors_and_overfit_flag() -> None:
    assert S9.sensitivity_neighbors("P2xA2") == ["P1xA2", "P3xA2", "P2xA1"]
    assert S9.sensitivity_neighbors("P0xA0") == ["P1xA0", "P0xA1"]
    grid = {"P2xA2": {"expectancy_r": 0.60}, "P1xA2": {"expectancy_r": 0.10},
            "P3xA2": {"expectancy_r": 0.20}, "P2xA1": {"expectancy_r": 0.15}}
    flag, _ = S9.overfit_flag(grid, "P2xA2")
    assert flag is True                                          # 0.60-0.20 > 0.25 sivrilik
    grid2 = dict(grid, P2xA2={"expectancy_r": 0.30})
    assert S9.overfit_flag(grid2, "P2xA2")[0] is False


# ---------------------------------------------------------------------------
# dondurma kilidi + teslimat artefaktı + senkron
# ---------------------------------------------------------------------------

def test_verdict_rejected_without_frozen_selection() -> None:
    wins = S9.load_windows()
    old = S9.SELECTED_YAML
    try:
        with tempfile.TemporaryDirectory() as td:
            S9.SELECTED_YAML = os.path.join(td, "yok.yaml")
            try:
                S9.phase_verdict(None, wins, None)               # runner'a ulaşmadan RED
                raise AssertionError("seçim donmadan verdict REDDEDİLMELİ")
            except PermissionError as e:
                assert "selected_cells.yaml YOK" in str(e)
            # hash'i bozuk dondurma -> RED
            with open(old, "r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
            doc["assets"]["BTC"]["frozen_sha256"] = "0" * 64
            p = os.path.join(td, "bozuk.yaml")
            with open(p, "w", encoding="utf-8") as fh:
                yaml.safe_dump(doc, fh, allow_unicode=True)
            S9.SELECTED_YAML = p
            try:
                S9.phase_verdict(None, wins, None)
                raise AssertionError("bozuk hash ile verdict REDDEDİLMELİ")
            except PermissionError as e:
                assert "frozen hash" in str(e)
    finally:
        S9.SELECTED_YAML = old


def test_delivered_selected_cells_yaml_is_consistent() -> None:
    assert os.path.exists(S9.SELECTED_YAML), "teslimat: selected_cells.yaml yazılmalı"
    with open(S9.SELECTED_YAML, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    wins = S9.load_windows()
    assert str(doc["policy_version"]) == wins["policy_version"]
    for k in S9.ASSET_CLASSES:
        a = doc["assets"][k]
        assert a["selected_cell"] in S9.CELLS
        if not a["selection_made"]:
            assert a["selected_cell"] == S9.DEFAULT_CELL and a["default_used"] is True
        assert a["frozen_sha256"] == S9.sha256_file(os.path.join(S9.ROOT, a["frozen_file"]))
        assert a["frozen_sha256"] == wins[k]["frozen_sha256"]
        assert set(a["train_grid"]) == set(S9.CELLS)             # 12 hücre TRAIN'de ölçüldü


def test_max_open_positions_synced_yaml_and_config() -> None:
    from quant4h.config import RISK_PROFILES
    with open(os.path.join(S9.ROOT, "configs", "user_decisions.yaml"),
              encoding="utf-8") as fh:
        y = yaml.safe_load(fh)
    assert y["risk"]["active"]["max_open_positions"] == 6
    assert y["risk"]["presets"]["balanced"]["max_open_positions"] == 6
    assert RISK_PROFILES["balanced"].max_open_positions == 6


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
