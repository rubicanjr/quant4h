"""Tests for M24-AGENT-EVAL harness (skor fonksiyonları + rapor üretimi).

Run: python3 -W ignore tests/eval/test_agent_eval.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

import run_agent_eval as E  # noqa: E402

GOOD_BLOCK = """## TAMAMLANDI: MTEST (2026-09-18, kullanıcı onaylı TEK patch)

Özet: scripts/foo.py + tests/test_foo.py · Suite **246/246** · hüküm/seçim/look etkisi YOK.
"""


def _g(d, *a):
    return subprocess.run(["git", "-C", d, *a], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def test_sessions_detected() -> None:
    # M26: cp1254 locale simülasyonu — encoding açık utf-8 olduğundan
    # getpreferredencoding(cp1254) altında bile _git str döner, çökmez
    import locale
    orig = locale.getpreferredencoding
    locale.getpreferredencoding = lambda *a, **k: "cp1254"
    try:
        out = E._git("log", "--format=%H|%s", "-3")
        assert isinstance(out, str)
        sess = E.sessions(8)
        has_git = E._git("rev-parse", "HEAD") != ""
    finally:
        locale.getpreferredencoding = orig
    if has_git:   # git yoksa (sandbox tur başı vb.) gerçek-repo assert'i atlanır
        assert len(sess) >= 3, sess
        sids = [x[0] for x in sess]
        assert any(x.startswith("m23") or x.startswith("m15c") for x in sids), sids
    # M26: frozen fixture — Türkçe commit mesajlı tmp repo'da determinizm
    with tempfile.TemporaryDirectory() as td:
        _g(td, "init", "-q")
        _g(td, "config", "user.email", "t@t")
        _g(td, "config", "user.name", "t")
        for i, msg in enumerate(("checkpoint: mtr1 — Türkçe özet çşğü İÜ",
                                 "checkpoint: mtr2 — ikinci çşğü")):
            with open(os.path.join(td, "a.txt"), "w", encoding="utf-8") as fh:
                fh.write(str(i))
            _g(td, "add", "-A")
            _g(td, "commit", "-q", "-m", msg)
        old_root = E.ROOT
        E.ROOT = td
        try:
            s1, s2 = E.sessions(5), E.sessions(5)
        finally:
            E.ROOT = old_root
        assert s1 == s2 and [x[0] for x in s1] == ["mtr2", "mtr1"], s1


def test_format_scoring_synthetic() -> None:
    chk = E.score_format("mtest", "checkpoint: mtest — özet", GOOD_BLOCK, "mtest_x.patch")
    assert all(chk.values()), chk
    bad = E.score_format("mtest", "checkpoint: mtest\nikinci satır", GOOD_BLOCK, None)
    assert not bad["commit konu tek satır + checkpoint öneki"]
    big = GOOD_BLOCK + "\n".join(f"f{i}" for i in range(30))
    chk2 = E.score_format("mtest", "checkpoint: mtest", big, "mtest_x.patch")
    assert not chk2[f"blok ≤{E.BLOCK_MAX_LINES} satır"]
    assert not E.score_format("mtest", "checkpoint: mtest", None, None)["PROGRESS bloğu VAR"]


def test_factuality_paths_checked() -> None:
    blk = GOOD_BLOCK.replace("scripts/foo.py", "scripts/run_agent_eval.py") \
                    .replace("tests/test_foo.py", "tests/eval/test_agent_eval.py")
    chk = E.score_factuality("mtest", "checkpoint: mtest", blk, None)
    assert chk["blok dosya yolları VAR"]
    blk2 = GOOD_BLOCK + " scripts/olmayan_dosya_xyz.py"
    chk2 = E.score_factuality("mtest", "checkpoint: mtest", blk2, None)
    assert not chk2["blok dosya yolları VAR"]
    m = re.search(r"[Ss]uite \*\*(\d+)/(\d+)\*\*", blk)
    assert chk["blok suite sayısı tutarlı (x/x)"] and m


def test_consistency_r09_cross() -> None:
    chk = E.score_consistency(None)
    assert chk["R09 çapraz sayaçlar eşit"], chk
    assert not chk["PROGRESS başlık == canlı suite"]   # live=None → False


def test_realism_negatives_present() -> None:
    chk = E.score_realism("m23", GOOD_BLOCK + " hata yakalandı.")
    assert chk["cadence BAYAT damgası"] and chk["QC RED → SORUN NOTU kaydı"]
    assert chk["pine SABİT banner"] and chk["blok dürüst negatif içerir (veya saf-doc)"]


def test_report_generation_skip_suite() -> None:
    rc = E.main.__wrapped__() if hasattr(E.main, "__wrapped__") else None
    import subprocess
    r = subprocess.run([sys.executable, "-W", "ignore",
                        os.path.join(E.ROOT, "scripts", "run_agent_eval.py"), "--skip-suite"],
                       capture_output=True, text=True, cwd=E.ROOT,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-500:]
    # M26: child cp1254 stdout ile bile ebeveyn çökmez (errors=replace)
    r2 = subprocess.run([sys.executable, "-W", "ignore",
                         os.path.join(E.ROOT, "scripts", "run_agent_eval.py"), "--skip-suite"],
                        capture_output=True, text=True, cwd=E.ROOT,
                        encoding="utf-8", errors="replace",
                        env={**os.environ, "PYTHONIOENCODING": "cp1254"})
    assert r2.returncode == 0, r2.stderr[-500:]
    from datetime import datetime, timezone
    tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = os.path.join(E.EVAL_DIR, f"{tag}.md")
    assert os.path.exists(p)
    with open(p, encoding="utf-8") as fh:
        txt = fh.read()
    for needle in ("AJAN SKOR KARTI", "FORMAT", "FACTUALITY", "REALISM",
                   "CONSISTENCY", "QUALITY (insan rubric 1-5, LLM-judge YOK)",
                   "<!-- quality-rubric -->"):
        assert needle in txt, needle


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
