"""R11: Pine otomatik kilidi — üretilmiş çıktı lint + yasak-kelime + şablon bütünlüğü.

Çalıştırma: `.venv/bin/python tests/test_pine_lint.py` (pytest ile de geçerli).
Üreteç içi lint'i depo tarafında tamamlar:
  (1) üretilmiş per-asset pine lint_pine'dan temiz geçmeli,
  (2) üretilmiş multi pine lint_multi'dan temiz geçmeli,
  (3) taahhütlü şablonlar + çıktılar yasak indikatör kelimesi içermemeli
      (EKİM MAINT: donchian_high/low(20) başlıkları swing_high/low(20) oldu),
  (4) şablonlarda PAYLOAD-BEGIN/END işaretleri dengeli durmalı.
"""
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import export_viz_payload as E                                  # noqa: E402

FORBIDDEN = ("ichimoku", "keltner", "donchian", "supertrend", "stoch",
             "vwap", "renko", "heikin", "parabolic sar", "psar")
T_PER = os.path.join(ROOT, "pine", "quant4h_viz.pine")
T_MULTI = os.path.join(ROOT, "pine", "quant4h_viz_multi.pine")


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _gen_all():
    with tempfile.TemporaryDirectory() as td:
        old = sys.argv
        sys.argv = ["export_viz_payload.py", "--out", td]
        try:
            assert E.main() == 0
            files = {f: _read(os.path.join(td, f)) for f in os.listdir(td)}
        finally:
            sys.argv = old
    return files


def test_generated_per_asset_lints_clean() -> None:
    files = _gen_all()
    per = [t for f, t in files.items()
           if f.endswith(".pine") and "multi" not in f]
    assert len(per) == 4, len(per)
    for t in per:
        assert not E.lint_pine(t)


def test_generated_multi_lints_clean() -> None:
    files = _gen_all()
    m = [t for f, t in files.items() if "multi" in f and f.endswith(".pine")]
    assert len(m) == 1
    assert not E.lint_multi(m[0])
    assert "tr_review" not in m[0]


def test_templates_and_outputs_forbidden_free() -> None:
    texts = {"per-asset-şablon": _read(T_PER), "multi-şablon": _read(T_MULTI)}
    for f, t in _gen_all().items():
        texts[f] = t
    for name, txt in texts.items():
        low = txt.lower()
        hits = [w for w in FORBIDDEN if w in low]
        assert not hits, (name, hits)


def test_templates_payload_markers_balanced() -> None:
    for p in (T_PER, T_MULTI):
        t = _read(p)
        assert t.count("PAYLOAD-BEGIN") == t.count("PAYLOAD-END") == 1, p
        assert t.startswith("//@version=5"), p


def _run_all() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for f in fns:
        f()
        print(f"  [ok] {f.__name__}")
    print(f"test_pine_lint: {len(fns)}/{len(fns)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(_run_all())
