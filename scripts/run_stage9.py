"""AŞAMA 9 — Walk-forward OOS + TEK seçim noktası + go/no-go (MAHKEME AŞAMASI).

Protokol (kullanıcı direktifi 2026-09-17 — KİLİTLİ):
  1. Pencereler ön-kayıtlı split'lerden (configs/splits_preregistered.yaml,
     policy v1.1) — `used` blokları (purge 30 + embargo 12 DAHİL EDİLMİŞ hâli).
     SEÇİM YALNIZ TRAIN'de. VALID = sağduyu (yeniden seçim YOK). TEST = saf rapor.
     go/no-go OOS havuzu = VALID+TEST (seçim hiç dokunmadı).
  2. Aday kümesi kilitli: {P0..P3}×{A0..A2} = 12 hücre. Varlık sınıfı başına TEK
     seçim: argmax TRAIN expR. TRAIN trade < 50 -> SEÇİM YOK ("ZAYIF"), raporlama
     a-priori varsayılan P0xA0 ile yapılır. Seçim `configs/selected_cells.yaml`'a
     TRAIN veri hash'iyle (frozen sha256) YAZILIR; seçim donmadan TEST koşusu
     script tarafından REDDEDİLİR (exit 2).
  3. VALID sağduyusu: seçili hücrenin VALID expR < 0 veya CI üstü < 0 ise varlık
     KALDI; TEST ikinci şans olarak KOŞULMAZ.
  4. go/no-go (OOS havuzu): n < min (core 100 / basket 150) -> "ZAYIF (örneklem)"
     -> watch_only (edge hükmü verilmez). Sayı yeterse: expR > 0 VE bootstrap CI
     altı > 0 VE PF >= 1.2 VE maxDD <= %25 -> GEÇTİ; SAĞLANMAZSA KALDI -> watch_only.
     (user_decisions.yaml -> go_no_go: "tek eşik KALDI ise NO-GO".)
  5. Monte Carlo (OOS trade dizisi, B=1000, seed 42): balanced risk için maxDD
     dağılımı, P(maxDD > %25), ruin (equity < %50 başlangıç) tablosu.
  6. Duyarlılık: seçili hücrenin komşuları (profil ±1, anchor ±1) TRAIN expR
     gradyanı; keskin sivrilik (fark > 0.25R) -> overfit bayrağı.
  7. Çıktı: varlık başına hüküm + portföy düzeyi (core agregat + basket).
     GEÇTİ varlıklar = paper/observe modu adayları.

Çalıştırma (SIRA ZORUNLU):
    python3 -W ignore scripts/run_stage9.py --phase select    # TRAIN + dondurma
    python3 -W ignore scripts/run_stage9.py --phase verdict   # VALID/TEST + hüküm
Çıktı: configs/selected_cells.yaml · reports/stage9_oos_verdict.md|.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))
sys.path.insert(0, _HERE)

import run_exit_grid as G  # noqa: E402
from quant4h.backtest.engine import Trade, bootstrap_ci  # noqa: E402
from quant4h.config import DEFAULT_EXIT, RISK_PROFILES, ExitConfig, UTC  # noqa: E402

RB = G.RB
ROOT = G.ROOT
SPLITS_YAML = os.path.join(ROOT, "configs", "splits_preregistered.yaml")
SELECTED_YAML = os.path.join(ROOT, "configs", "selected_cells.yaml")

PROFILES = ("P0", "P1", "P2", "P3")
ANCHORS = ("A0", "A1", "A2")
CELLS = [f"{p}x{a}" for p in PROFILES for a in ANCHORS]
DEFAULT_CELL = "P0xA0"
CORE_ASSETS = ("BTC", "GOLD", "SILVER")
BASKET = "BIST30_BASKET"
ASSET_CLASSES = ("BTC", "GOLD", "SILVER", "BIST30_BASKET")

MIN_TRAIN_FOR_SELECTION = 50       # direktif md.2
MIN_TRADES_CORE = 100              # go_no_go (user_decisions.yaml)
MIN_TRADES_BASKET = 150
PF_MIN = 1.2
DD_MAX = 0.25
MC_B = 1000
MC_SEED = 42
RUIN_EQUITY_FRAC = 0.50
OVERFIT_SPIKE_R = 0.25


# ---------------------------------------------------------------------------
# pencereler + hash
# ---------------------------------------------------------------------------

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_windows(splits_path: str = SPLITS_YAML) -> Dict[str, Any]:
    """splits yaml -> {asset: {train/valid/test: (first_ts, last_ts, n_used), frozen_file,
    frozen_sha256, purge_bars, embargo_bars}} (yalnız `used` blokları; purge+embargo
    ön-kayıtta zaten düşülmüştür)."""
    with open(splits_path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    out: Dict[str, Any] = {"policy_version": str(doc.get("policy_version"))}
    src = {"BTC": doc["assets"]["BTC"], "GOLD": doc["assets"]["GOLD"],
           "SILVER": doc["assets"]["SILVER"], "BIST30_BASKET": doc["bist30_basket"]}
    for name, blk in src.items():
        w: Dict[str, Any] = {}
        for part in ("train", "valid", "test"):
            used = blk[part]["used"]
            w[part] = (pd.Timestamp(used["first_utc"]), pd.Timestamp(used["last_utc"]),
                       int(used.get("n_raw", used.get("grid_bars", -1))))
        w["frozen_file"] = blk["frozen_file"]
        w["frozen_sha256"] = blk["frozen_sha256"]
        w["purge_bars"] = int(blk.get("purge_bars", 30))
        w["embargo_bars"] = int(blk.get("embargo_bars", 12))
        out[name] = w
    return out


def assign_windows(trades: List[Trade], w: Dict[str, Any]) -> Dict[str, List[Trade]]:
    """Trade'leri GİRİŞ zamanına göre used pencerelerine ata. Pencereler arası
    purge/embargo boşluğuna düşen girişler `gap` kovasına (hiçbir pencereye sayılmaz)."""
    buckets: Dict[str, List[Trade]] = {"train": [], "valid": [], "test": [], "gap": []}
    for t in trades:
        ts = pd.Timestamp(t.entry_timestamp_utc)
        placed = False
        for part in ("train", "valid", "test"):
            first, last, _ = w[part]
            if first <= ts <= last:
                buckets[part].append(t)
                placed = True
                break
        if not placed:
            buckets["gap"].append(t)
    return buckets


# ---------------------------------------------------------------------------
# metrikler (Aşama 6/7 ile aynı aile; R-bazlı + net)
# ---------------------------------------------------------------------------

def metrics_from_trades(ts: List[Trade]) -> Dict[str, Any]:
    n = len(ts)
    if n == 0:
        return {"n_trades": 0, "expectancy_r": None, "expR_ci95": None,
                "prob_expR_positive": None, "profit_factor_net": None,
                "win_rate": None, "max_dd_path_frac": None, "net_pnl_total": 0.0}
    rs = np.array([t.r_multiple for t in ts], dtype="float64")
    nets = np.array([t.net_pnl for t in ts], dtype="float64")
    eqb = np.maximum(np.array([t.equity_before for t in ts], dtype="float64"), 1e-9)
    wins, losses = nets > 0, nets < 0
    npn, nln = float(nets[wins].sum()), float(-nets[losses].sum())
    pf = round(npn / nln, 4) if nln > 0 else (None if npn == 0 else float("inf"))
    boot = bootstrap_ci(rs[np.isfinite(rs)], nets / eqb, DEFAULT_EXIT) if n >= 5 else {}
    eq, peak, mdd = 1.0, 1.0, 0.0
    for t in ts:                                   # bileşik equity yolu (return_frac)
        rf = t.return_frac if np.isfinite(t.return_frac) else 0.0
        eq *= (1.0 + rf)
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1.0)
    return {"n_trades": n,
            "expectancy_r": round(float(np.nanmean(rs)), 4),
            "expR_ci95": boot.get("expectancy_r_ci95"),
            "prob_expR_positive": boot.get("prob_expectancy_positive"),
            "profit_factor_net": pf,
            "win_rate": round(float(wins.mean()), 4),
            "max_dd_path_frac": round(mdd, 6),
            "net_pnl_total": round(float(nets.sum()), 2)}


def select_cell(train_grid: Dict[str, Dict[str, Any]]) -> Tuple[Optional[str], bool, str]:
    """TEK seçim noktası: argmax TRAIN expR (adaylar: n >= 50, expR sonlu).
    Tie-break: CELLS sırası (deterministik). Dönüş: (cell|None, default_used, not)."""
    cands = [(c, train_grid[c]["expectancy_r"]) for c in CELLS
             if train_grid.get(c, {}).get("n_trades", 0) >= MIN_TRAIN_FOR_SELECTION
             and train_grid[c].get("expectancy_r") is not None
             and np.isfinite(train_grid[c]["expectancy_r"])]
    if not cands:
        return None, True, f"SEÇİM YOK: hiçbir hücrede TRAIN trade >= {MIN_TRAIN_FOR_SELECTION} değil (ZAYIF)"
    best = max(c[1] for c in cands)
    cell = next(c for c, v in cands if v == best)    # CELLS sırasında ilk
    return cell, False, f"argmax TRAIN expR = {best:+.4f} ({cell})"


def valid_sanity_check(vm: Dict[str, Any]) -> Tuple[bool, str]:
    """VALID sağduyusu: expR < 0 veya CI üstü < 0 -> False (KALDI, TEST koşulmaz)."""
    er = vm.get("expectancy_r")
    if vm.get("n_trades", 0) == 0:
        return False, "VALID trade YOK -> sağduyu BAŞARISIZ (fail-closed)"
    if er is not None and er < 0:
        return False, f"VALID expR {er:+.4f} < 0 -> KALDI (TEST koşulmaz)"
    ci = vm.get("expR_ci95")
    if ci and ci[1] is not None and ci[1] < 0:
        return False, f"VALID CI üstü {ci[1]:+.4f} < 0 -> KALDI (TEST koşulmaz)"
    if not ci:
        return True, "VALID expR >= 0; CI hesaplanamadı (n<5) — sağduyu expR ile sınırlı (not)"
    return True, "VALID sağduyu GEÇTİ"


def go_nogo(om: Dict[str, Any], min_trades: int) -> Tuple[str, str, List[str]]:
    """(hüküm, mod, gerekçe listesi). ZAYIF -> watch_only (edge hükmü verilmez)."""
    reasons: List[str] = []
    n = om.get("n_trades", 0)
    if n < min_trades:
        return ("ZAYIF (örneklem)", "watch_only",
                [f"OOS trade {n} < min {min_trades} -> edge hükmü VERİLMEZ"])
    er = om.get("expectancy_r")
    ci = om.get("expR_ci95")
    pf = om.get("profit_factor_net")
    dd = om.get("max_dd_path_frac")
    ok = True
    if er is None or er <= 0:
        ok = False; reasons.append(f"expR {er} <= 0")
    if not ci or ci[0] is None or ci[0] <= 0:
        ok = False; reasons.append(f"CI altı {ci[0] if ci else None} <= 0")
    if pf is None or (pf != float("inf") and pf < PF_MIN):
        ok = False; reasons.append(f"PF {pf} < {PF_MIN}")
    if dd is None or dd < -DD_MAX:
        ok = False; reasons.append(f"maxDD {dd} < -{DD_MAX}")
    if ok:
        return ("GEÇTİ", "paper_observe_candidate", ["tüm eşikler sağlandı"])
    return ("KALDI", "watch_only", reasons or ["eşik(ler) sağlanmadı"])


def monte_carlo(ts: List[Trade], b: int = MC_B, seed: int = MC_SEED) -> Dict[str, Any]:
    """OOS trade dizisinin getiri oranlarını (net/equity_before) REPLACEMENT ile
    yeniden örnekler; bileşik equity yollarından maxDD dağılımı + ruin üretir."""
    if len(ts) < 5:
        return {"note": f"MC için yetersiz OOS trade (n={len(ts)} < 5)", "n_trades": len(ts)}
    rets = np.array([t.net_pnl / max(t.equity_before, 1e-9) for t in ts], dtype="float64")
    rets = rets[np.isfinite(rets)]
    rng = np.random.default_rng(seed)
    n = len(rets)
    idx = rng.integers(0, n, size=(b, n))
    eq = np.cumprod(1.0 + rets[idx], axis=1)
    peak = np.maximum.accumulate(eq, axis=1)
    dd = (eq / peak - 1.0).min(axis=1)               # her çizimin maxDD'si (negatif)
    ruin = (eq.min(axis=1) < RUIN_EQUITY_FRAC).mean()
    return {"n_trades": n, "B": b, "seed": seed,
            "maxDD_p05": round(float(np.quantile(dd, 0.05)), 4),
            "maxDD_p50": round(float(np.quantile(dd, 0.50)), 4),
            "maxDD_p95": round(float(np.quantile(dd, 0.95)), 4),
            "prob_maxDD_worse_than_25pct": round(float((dd < -DD_MAX).mean()), 4),
            f"prob_ruin_equity_below_{int(RUIN_EQUITY_FRAC*100)}pct": round(float(ruin), 4)}


def sensitivity_neighbors(cell: str) -> List[str]:
    p, a = cell.split("x")
    pi, ai = PROFILES.index(p), ANCHORS.index(a)
    nb = []
    for dpi, dai in ((-1, 0), (+1, 0), (0, -1), (0, +1)):
        np_, na_ = pi + dpi, ai + dai
        if 0 <= np_ < len(PROFILES) and 0 <= na_ < len(ANCHORS):
            nb.append(f"{PROFILES[np_]}x{ANCHORS[na_]}")
    return nb


def overfit_flag(train_grid: Dict[str, Any], cell: str) -> Tuple[bool, str]:
    sel = train_grid.get(cell, {}).get("expectancy_r")
    if sel is None:
        return False, "seçili hücre TRAIN expR yok"
    nbs = {c: train_grid.get(c, {}).get("expectancy_r") for c in sensitivity_neighbors(cell)}
    finite = [v for v in nbs.values() if v is not None and np.isfinite(v)]
    if not finite:
        return False, "komşu TRAIN expR yok"
    gap = sel - max(finite)
    flag = bool(sel > 0 and gap > OVERFIT_SPIKE_R)
    return flag, (f"seçili {sel:+.4f} − en iyi komşu {max(finite):+.4f} = {gap:+.4f}"
                  + (" > 0.25 → KESKİN SİVRİLİK (overfit bayrağı)" if flag else ""))


# ---------------------------------------------------------------------------
# hücre koşuları (Aşama 6/7 desenleriyle aynı)
# ---------------------------------------------------------------------------

def _chain(trades: List[Trade], start_eq: float) -> List[Trade]:
    eq = start_eq
    out = sorted(trades, key=lambda t: (t.entry_timestamp_utc, t.exit_timestamp_utc))
    for t in out:
        t.equity_before = eq
        t.equity_after = eq + t.net_pnl
        eq = t.equity_after
    return out


class CellRunner:
    """Bir anchor'ın sinyal frame'lerini bir kez kurar; 4 profili üzerinde koşar."""

    def __init__(self, tf: str, codes: List[str], prof, start_eq: float):
        self.prof, self.start_eq = prof, start_eq
        self.tf = tf
        self.index_4h = RB._load(os.path.join(ROOT, "data", "interim", f"bist30_{tf}.parquet"))
        self.core_frames: Dict[str, Dict[str, pd.DataFrame]] = {}
        self.codes = sorted(codes)
        for key in CORE_ASSETS:
            self.core_frames[key] = {a: G._signals_for(key, tf, False, self.index_4h, a)
                                     for a in ANCHORS}
            for a in ANCHORS:
                if self.core_frames[key][a] is None:
                    raise FileNotFoundError(f"{key}/{a} frame yok")
        self._stock_cache: Dict[str, pd.DataFrame] = {}

    def _stock_frame(self, code: str, anchor: str) -> Optional[pd.DataFrame]:
        """Hisse frame'leri core ile AYNI yoldan kurulur: levels -> momentum ->
        bağlam -> anchor override -> capped sinyaller (run_exit_grid._signals_for)."""
        ck = f"{code}|{anchor}"
        if ck not in self._stock_cache:
            self._stock_cache[ck] = G._signals_for(code, self.tf, True, self.index_4h, anchor)
        return self._stock_cache[ck]

    def core_trades(self, key: str, cell: str) -> List[Trade]:
        p, a = cell.split("x")
        frame = self.core_frames[key][a]
        cfg = ExitConfig(profile=p)
        cost = RB._cost_for(key, False)
        lr = G.run_backtest(frame, cost, exit_cfg=cfg, risk_per_trade=self.prof.risk_per_trade,
                            starting_equity=self.start_eq, max_leverage=self.prof.max_leverage,
                            allow_short=False, asset=f"{key}_long")
        sr = G.run_backtest(frame, cost, exit_cfg=cfg, risk_per_trade=self.prof.risk_per_trade,
                            starting_equity=self.start_eq, max_leverage=self.prof.max_leverage,
                            allow_short=True, signal_col_long="__none__",
                            signal_col_short="short_signal", asset=f"{key}_short")
        merged = RB._merge_results(lr, sr, key)
        return list(merged.trades)

    def basket_trades(self, cell: str) -> List[Trade]:
        p, a = cell.split("x")
        cfg = ExitConfig(profile=p)
        all_tr: List[Trade] = []
        for code in self.codes:
            frame = self._stock_frame(code, a)
            if frame is None or not len(frame):
                continue
            cost = RB._cost_for(code, True)
            lr = G.run_backtest(frame, cost, exit_cfg=cfg, risk_per_trade=self.prof.risk_per_trade,
                                starting_equity=self.start_eq, max_leverage=1.0,
                                allow_short=False, asset=code)
            for t in lr.trades:
                t.group_key = code
            all_tr.extend(lr.trades)
        return _chain(all_tr, self.start_eq)

    def trades_for(self, klass: str, cell: str) -> List[Trade]:
        return self.basket_trades(cell) if klass == BASKET else self.core_trades(klass, cell)


# ---------------------------------------------------------------------------
# fazlar
# ---------------------------------------------------------------------------

def phase_select(runner: CellRunner, wins: Dict[str, Any], prof) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "stage": 9, "phase": "select",
        "policy_version": wins["policy_version"],
        "generated_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
        "selection_rule": (f"argmax TRAIN expR; {len(CELLS)} kilitli hücre {{P0..P3}}×{{A0..A2}}; "
                           f"TRAIN n < {MIN_TRAIN_FOR_SELECTION} -> seçim YOK, a-priori {DEFAULT_CELL}"),
        "min_train_trades_for_selection": MIN_TRAIN_FOR_SELECTION,
        "risk_profile": {"name": prof.name, "risk_per_trade": prof.risk_per_trade},
        "assets": {},
    }
    for klass in ASSET_CLASSES:
        w = wins[klass]
        grid: Dict[str, Any] = {}
        for cell in CELLS:
            tr = assign_windows(runner.trades_for(klass, cell), w)
            m = metrics_from_trades(tr["train"])
            grid[cell] = {"n_trades": m["n_trades"], "expectancy_r": m["expectancy_r"],
                          "profit_factor_net": m["profit_factor_net"]}
            print(f"  [select {klass:12s} {cell}] TRAIN n={m['n_trades']:4d} expR={m['expectancy_r']}")
        cell, default_used, note = select_cell(grid)
        frozen_path = os.path.join(ROOT, w["frozen_file"])
        sha = sha256_file(frozen_path)
        if sha != w["frozen_sha256"]:
            raise RuntimeError(f"{klass}: frozen sha256 ÖN-KAYITLA UYUŞMUYOR — seçim DURDURULDU")
        out["assets"][klass] = {
            "selected_cell": cell or DEFAULT_CELL,
            "selection_made": cell is not None,
            "default_used": default_used,
            "selection_note": note,
            "train_n_trades": grid[cell or DEFAULT_CELL]["n_trades"],
            "train_expR": grid[cell or DEFAULT_CELL]["expectancy_r"],
            "train_grid": grid,
            "frozen_file": w["frozen_file"],
            "frozen_sha256": sha,
            "windows": {p: {"first_utc": str(w[p][0]), "last_utc": str(w[p][1]),
                            "n_used": w[p][2]} for p in ("train", "valid", "test")},
        }
        print(f"  => {klass}: {note}")
    with open(SELECTED_YAML, "w", encoding="utf-8") as fh:
        yaml.safe_dump(out, fh, allow_unicode=True, sort_keys=False)
    print(f"\nSEÇİM DONDURULDU: {os.path.relpath(SELECTED_YAML, ROOT)}")
    return out


def _load_frozen_selection() -> Dict[str, Any]:
    if not os.path.exists(SELECTED_YAML):
        raise PermissionError(
            "RED: configs/selected_cells.yaml YOK — seçim DONMADAN TEST koşusu YASAK "
            "(protokol md.2). Önce --phase select çalıştırın.")
    with open(SELECTED_YAML, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def phase_verdict(runner: CellRunner, wins: Dict[str, Any], prof) -> Dict[str, Any]:
    sel = _load_frozen_selection()
    if str(sel.get("policy_version")) != str(wins["policy_version"]):
        raise PermissionError("RED: selected_cells.yaml policy_version ön-kayıtla uyuşmuyor")
    for klass in ASSET_CLASSES:
        rec = sel["assets"][klass]
        sha = sha256_file(os.path.join(ROOT, rec["frozen_file"]))
        if sha != rec["frozen_sha256"]:
            raise PermissionError(f"RED: {klass} frozen hash DONDURMA sonrasında değişmiş — TEST YASAK")
    print("seçim dondurması DOĞRULANDI (hash'ler ön-kayıtla birebir)")

    assets: Dict[str, Any] = {}
    oos_pool: Dict[str, List[Trade]] = {}
    for klass in ASSET_CLASSES:
        w = wins[klass]
        rec = sel["assets"][klass]
        cell = rec["selected_cell"]
        trades = runner.trades_for(klass, cell)
        buckets = assign_windows(trades, w)
        vm = metrics_from_trades(buckets["valid"])
        ok, note = valid_sanity_check(vm)
        entry: Dict[str, Any] = {"selected_cell": cell, "selection_made": rec["selection_made"],
                                 "default_used": rec["default_used"],
                                 "train_n_trades": rec["train_n_trades"],
                                 "train_expR": rec["train_expR"],
                                 "valid": vm, "valid_sanity_ok": ok, "valid_sanity_note": note,
                                 "gap_excluded_trades": len(buckets["gap"])}
        if not ok:
            entry.update({"test": None, "test_note": "KOŞULMADI (protokol md.3: TEST ikinci şans değil)",
                          "oos_pool": None, "verdict": "KALDI", "mode": "watch_only",
                          "verdict_reasons": [note]})
            oos_pool[klass] = buckets["valid"]        # agregasyon: yalnız VALID (TEST koşulmadı)
        else:
            tm = metrics_from_trades(buckets["test"])
            oos = buckets["valid"] + buckets["test"]
            oos = sorted(oos, key=lambda t: t.entry_timestamp_utc)
            oos_pool[klass] = oos
            om = metrics_from_trades(oos)
            min_n = MIN_TRADES_BASKET if klass == BASKET else MIN_TRADES_CORE
            verdict, mode, reasons = go_nogo(om, min_n)
            mc = monte_carlo(oos)
            entry.update({"test": tm, "oos_pool": om, "min_trades": min_n,
                          "verdict": verdict, "mode": mode, "verdict_reasons": reasons,
                          "monte_carlo": mc})
        flag, fnote = overfit_flag(rec["train_grid"], cell)
        nb = {c: rec["train_grid"].get(c, {}) for c in sensitivity_neighbors(cell)}
        entry["sensitivity"] = {"cell": cell, "neighbors_train": nb,
                                "overfit_flag": flag, "note": fnote}
        assets[klass] = entry
        print(f"  [{klass:12s} {cell}] VALID n={vm['n_trades']} expR={vm['expectancy_r']} "
              f"-> {'OK' if ok else 'KALDI'} · hüküm: {entry['verdict']} ({entry['mode']})")

    # ---- portföy düzeyi ----
    core_oos = sorted([t for k in CORE_ASSETS for t in oos_pool.get(k, [])],
                      key=lambda t: t.entry_timestamp_utc)
    core_oos = _chain(core_oos, runner.start_eq)
    core_m = metrics_from_trades(core_oos)
    core_verdict, core_mode, core_reasons = go_nogo(core_m, MIN_TRADES_CORE)
    kaldi_members = [k for k in CORE_ASSETS if assets.get(k, {}).get("verdict") == "KALDI"]
    if kaldi_members:
        core_reasons = core_reasons + [
            f"NOT: {', '.join(kaldi_members)} VALID sağduyudan KALDI (TEST koşulmadı) — "
            f"agregaya yalnız VALID trade'leriyle dahil; üye hükmü agregatla YUMUŞATILAMAZ"]
    basket_oos = _chain(list(oos_pool.get(BASKET, [])), runner.start_eq)
    basket_m = metrics_from_trades(basket_oos)
    b_verdict, b_mode, b_reasons = go_nogo(basket_m, MIN_TRADES_BASKET)
    if assets.get(BASKET, {}).get("verdict") == "KALDI":
        # varlık düzeyindeki KALDI (VALID sağduyu) portföy satırına AYNEN taşınır;
        # örneklem ZAYIF'ı gerekçeye not düşülür (kötü hüküm yumuşatılamaz).
        b_verdict, b_mode = "KALDI", "watch_only"
        b_reasons = ["üye VARLIK hükmü KALDI (VALID sağduyu başarısız, TEST koşulmadı); "
                     "havuz yalnız VALID"] + b_reasons
    portfolio = {
        "core_aggregate": {"metrics": core_m, "verdict": core_verdict, "mode": core_mode,
                           "reasons": core_reasons, "monte_carlo": monte_carlo(core_oos),
                           "note": "BTC+GOLD+SILVER OOS havuzlarının birleşimi (risk katmanı YOK; Aşama 8 tavanları ayrı rapor)"},
        "basket": {"metrics": basket_m, "verdict": b_verdict, "mode": b_mode,
                   "reasons": b_reasons, "monte_carlo": monte_carlo(basket_oos)},
    }
    payload = {
        "generated_at_utc": pd.Timestamp.now(tz=UTC).isoformat(),
        "stage": 9, "protocol": "kilitli (direktif 2026-09-17): seçim TRAIN'de TEK nokta; "
                                "VALID sağduyu; TEST saf rapor 1 KEZ; OOS havuzu = VALID+TEST",
        "policy_version": wins["policy_version"],
        "selected_cells_file": os.path.relpath(SELECTED_YAML, ROOT),
        "thresholds": {"min_trades_core": MIN_TRADES_CORE, "min_trades_basket": MIN_TRADES_BASKET,
                       "pf_min": PF_MIN, "dd_max": DD_MAX, "ci_lower_gt": 0.0, "expR_gt": 0.0},
        "assets": assets, "portfolio": portfolio,
        "caveats": [
            "TEK fold (ön-kayıtlı split v1.1); çok katlı walk-fold Aşama 9 sonrası genişletme adayıdır.",
            "Trade atfı GİRİŞ zamanına göre; pencere dışında kapanan çıkışlar giriş penceresine sayılır.",
            "Purge/embargo boşluğuna düşen girişler hiçbir pencereye sayılmadı (gap_excluded_trades).",
            "Sepet survivorship bias taşır; metals feed'inde düşük-kalite pencere (2026-01-26..02-06) TEST aralığı dışında.",
            "TEST bu teslimatta 1 KEZ koşuldu; yeniden koşum onay gerektirir.",
            "ZAYIF hükümler edge kanıtı DEĞİLDİR; watch_only = izle, edge iddiası YOK.",
        ],
    }
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "stage9_oos_verdict.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    with open(os.path.join(ROOT, "reports", "stage9_oos_verdict.md"), "w", encoding="utf-8") as fh:
        fh.write(_md(payload, sel))
    print("\nraporlar: reports/stage9_oos_verdict.md · .json")
    return payload


def _fmt_m(m: Optional[Dict[str, Any]]) -> str:
    if not m or not m.get("n_trades"):
        return "| 0 | — | — | — | — | — | — |"
    ci = m.get("expR_ci95") or [None, None]
    pf = m.get("profit_factor_net")
    return "| {n} | {er} | [{lo}, {hi}] | {pf} | {wr} | {dd} | {net:+,.0f} |".format(
        n=m["n_trades"],
        er=f"{m['expectancy_r']:+.4f}" if m.get("expectancy_r") is not None else "—",
        lo=f"{ci[0]:+.3f}" if ci[0] is not None else "—",
        hi=f"{ci[1]:+.3f}" if ci[1] is not None else "—",
        pf=f"{pf:.3f}" if isinstance(pf, (int, float)) and pf != float("inf") else ("∞" if pf == float("inf") else "—"),
        wr=f"{m['win_rate']*100:.1f}%" if m.get("win_rate") is not None else "—",
        dd=f"{m['max_dd_path_frac']*100:.2f}%" if m.get("max_dd_path_frac") is not None else "—",
        net=m.get("net_pnl_total") or 0.0)


def _md(payload: Dict[str, Any], sel: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append("# AŞAMA 9 — Walk-forward OOS hükmü (TEST 1 KEZ koşuldu)")
    L.append("")
    L.append(f"*Üretim: {payload['generated_at_utc']}* · ön-kayıt policy **v{payload['policy_version']}** · "
             f"seçim dosyası `{payload['selected_cells_file']}` (TRAIN hash'leriyle DONDURULMUŞ, "
             f"verdict fazı hash'leri doğrulamadan TEST'i REDDEDER)")
    L.append("")
    L.append("**Protokol (kilitli):** SEÇİM YALNIZ TRAIN'de, hücre başına TEK nokta "
             f"(argmax TRAIN expR; n<{MIN_TRAIN_FOR_SELECTION} → seçim YOK, a-priori `{DEFAULT_CELL}`) · "
             "VALID = sağduyu (expR<0 veya CI üstü<0 → KALDI, **TEST koşulmaz**) · "
             "TEST = saf rapor · go/no-go OOS havuzu = **VALID+TEST** · eşikler: n≥100(core)/150(basket), "
             "expR>0, CI altı>0, PF≥1.2, maxDD≤%25 (user_decisions.yaml → go_no_go).")
    L.append("")
    L.append("## HÜKÜM TABLOSU")
    L.append("")
    L.append("| varlık | seçili hücre | seçim yapıldı mı | OOS n | **HÜKÜM** | mod |")
    L.append("|---|---|---|---:|---|---|")
    for k in ASSET_CLASSES:
        a = payload["assets"][k]
        om = a.get("oos_pool") or {}
        L.append(f"| {k} | `{a['selected_cell']}` | "
                 f"{'EVET' if a['selection_made'] else 'HAYIR (TRAIN ZAYIF → a-priori ' + DEFAULT_CELL + ')'} | "
                 f"{om.get('n_trades', '—')} | **{a['verdict']}** | `{a['mode']}` |")
    for nm, key in (("CORE AGREGAT", "core_aggregate"), ("PORTFÖY-SEPET", "basket")):
        p = payload["portfolio"][key]
        L.append(f"| **{nm}** | (üye hücreleri) | — | {p['metrics'].get('n_trades', 0)} | "
                 f"**{p['verdict']}** | `{p['mode']}` |")
    L.append("")
    L.append("> GEÇTİ varlıklar **paper/observe modu adaylarıdır** (canlı emir YOK — kapsam dışı). "
             "ZAYIF/KALDI → `watch_only`: edge hükmü verilmez.")
    L.append("")
    for k in ASSET_CLASSES:
        a = payload["assets"][k]
        w = sel["assets"][k]["windows"]
        L.append(f"## {k} — `{a['selected_cell']}`")
        L.append("")
        L.append(f"Pencereler (used): TRAIN {w['train']['first_utc'][:10]}→{w['train']['last_utc'][:10]} "
                 f"({w['train']['n_used']} bar) · VALID {w['valid']['first_utc'][:10]}→{w['valid']['last_utc'][:10]} "
                 f"({w['valid']['n_used']}) · TEST {w['test']['first_utc'][:10]}→{w['test']['last_utc'][:10]} "
                 f"({w['test']['n_used']}) · gap-dışılanan trade: {a['gap_excluded_trades']}")
        L.append("")
        L.append(f"TRAIN seçim: n={a['train_n_trades']} expR={a['train_expR']} · "
                 f"{'seçim YAPILDI' if a['selection_made'] else 'seçim YOK (ZAYIF) — a-priori ' + DEFAULT_CELL}")
        L.append("")
        L.append("| pencere | n | expR | CI95 | PF | win | maxDD(yol) | net |")
        L.append("|---|---:|---:|---|---:|---:|---:|---:|")
        L.append(f"| VALID | {_fmt_m(a['valid'])[2:]}")
        if a.get("test") is not None:
            L.append(f"| TEST | {_fmt_m(a['test'])[2:]}")
            L.append(f"| **OOS (V+T)** | {_fmt_m(a['oos_pool'])[2:]}")
        else:
            L.append(f"| TEST | — | — | — | — | — | — | — |")
        L.append("")
        L.append(f"VALID sağduyu: {'✅' if a['valid_sanity_ok'] else '❌'} {a['valid_sanity_note']}")
        if a.get("verdict_reasons"):
            L.append(f"Hüküm gerekçesi: {'; '.join(a['verdict_reasons'])}")
        mc = a.get("monte_carlo")
        if mc and "maxDD_p50" in mc:
            L.append(f"Monte Carlo (OOS dizisi, B={mc['B']}, seed={mc['seed']}): "
                     f"maxDD p05/p50/p95 = %{mc['maxDD_p05']*100:.1f}/%{mc['maxDD_p50']*100:.1f}/%{mc['maxDD_p95']*100:.1f} · "
                     f"P(maxDD>%25)={mc['prob_maxDD_worse_than_25pct']:.2f} · "
                     f"P(ruin<%50 equity)={mc[f'prob_ruin_equity_below_{int(RUIN_EQUITY_FRAC*100)}pct']:.2f}")
        elif mc:
            L.append(f"Monte Carlo: {mc.get('note', '—')}")
        s = a["sensitivity"]
        nb = ", ".join(f"`{c}` {v.get('expectancy_r') if v.get('expectancy_r') is not None else '—'}"
                       for c, v in s["neighbors_train"].items())
        L.append(f"Duyarlılık (TRAIN expR komşuları): {nb} · {s['note']}"
                 + (" · ⚠️ **OVERFIT BAYRAĞI**" if s["overfit_flag"] else ""))
        L.append("")
    L.append("## PORTFÖY DÜZEYİ")
    L.append("")
    for nm, key in (("CORE AGREGAT (BTC+GOLD+SILVER OOS birleşimi)", "core_aggregate"),
                    ("SEPET (BIST30 OOS)", "basket")):
        p = payload["portfolio"][key]
        L.append(f"**{nm}**: {_fmt_m(p['metrics'])[2:-1].strip('|')}")
        L.append(f"  hüküm **{p['verdict']}** (`{p['mode']}`) — {'; '.join(p['reasons'])}")
        mc = p.get("monte_carlo") or {}
        if "maxDD_p50" in mc:
            L.append(f"  MC: maxDD p50 %{mc['maxDD_p50']*100:.1f} · P(maxDD>%25)={mc['prob_maxDD_worse_than_25pct']:.2f} · "
                     f"P(ruin)={mc[f'prob_ruin_equity_below_{int(RUIN_EQUITY_FRAC*100)}pct']:.2f}")
        L.append("")
    L.append("## CAVEAT'LER (zorunlu)")
    L.append("")
    for c in payload["caveats"]:
        L.append(f"- {c}")
    L.append("")
    L.append("*Bu rapor yatırım tavsiyesi DEĞİLDİR; tüm ölçümler ön-kayıtlı pencerelerde ve "
             "maliyet dahil yapılmıştır. Geçmiş performans geleceğin göstergesi değildir.*")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--phase", required=True, choices=("select", "verdict"))
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--risk-profile", default="balanced", choices=sorted(RISK_PROFILES))
    ap.add_argument("--starting-equity", type=float, default=100_000.0)
    args = ap.parse_args()
    prof = RISK_PROFILES[args.risk_profile]
    wins = load_windows()
    codes = RB._included(os.path.join(ROOT, "reports", "bist30_universe_qc.json"))
    runner = CellRunner(args.timeframe, codes, prof, args.starting_equity)
    print(f"Aşama 9 · faz={args.phase} · profil={prof.name} · {len(codes)} hisse · "
          f"policy v{wins['policy_version']} · protokol KİLİTLİ")
    if args.phase == "select":
        phase_select(runner, wins, prof)
    else:
        phase_verdict(runner, wins, prof)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PermissionError as e:
        print(f"\n{e}")
        raise SystemExit(2)
