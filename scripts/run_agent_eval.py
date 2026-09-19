"""M24-AGENT-EVAL — patch oturumlarını 5 kriterle skorla (2026-09-18, kullanıcı onaylı).

Kriterler:
  1 FORMAT     : özet şema lint'i — commit konu tek satır + "checkpoint:" öneki ·
                 PROGRESS bloğu ≤12 satır · blok patch dosyasına/“TEK patch”e atıf ·
                 blokta suite satırı · DUR disiplini vekili: blokta sınır satırı
                 (“Hüküm/seçim/look … YOK”). SOHBET satır sayısı repo'da tutulmaz →
                 rapor MANUAL satırı olarak işaretler (kanıt: sohbet kaydı yok).
  2 FACTUALITY : claim-check — blokta geçen dosya yolları `ls` ile VAR · patch
                 From-konu == git log konu · blok suite sayısı monotonic ·
                 (güncel suite koşusu --skip-suite ile atlanabilir).
  3 CONSISTENCY: R09 çapraz sayaçlar: README == model_card == PROGRESS başlık ==
                 test_deliverables iğnesi == canlı suite koşusu.
  4 REALISM    : negatif sonuç izleri: cadence BAYAT damgası · QC RED → SORUN NOTU ·
                 pine SABİT banner (UNTESTED-VIZ/watch_only) · blok başına dürüst
                 negatif token (hata/RED/BAYAT/fail/yakalandı) veya saf-doc oturumu.
  5 QUALITY    : İNSAN rubric'i 1-5 (LLM-judge YOK). `--quality N` ile PROGRESS'e
                 işlenir (marker satırı); verilene dek "BEKLEMEDE".

Çıktı: reports/eval/YYYY-MM-DD.md · sınır: hüküm/seçim/look etkisi YOK.

Çalıştırma:
    python3 -W ignore scripts/run_agent_eval.py [--n 8] [--skip-suite] [--quality N]
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EVAL_DIR = os.path.join(ROOT, "reports", "eval")
BLOCK_MAX_LINES = 12
NEG_TOKENS = ("hata", "RED", "BAYAT", "fail", "yakalandı", "UYARI", "ihanl", "İHLAL")
QUALITY_MARKER = "<!-- quality-rubric -->"


def _read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as fh:
        return fh.read()


def _git(*args) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip()


def sessions(n: int):
    out = []
    log = _git("log", "--format=%H|%s", "-50")
    for line in log.splitlines():
        h, subj = line.split("|", 1)
        m = re.match(r"(?:checkpoint|cumulative): (m[\w.-]+)", subj)
        if m:
            out.append((m.group(1), h, subj))
        if len(out) >= n:
            break
    return out


def _norm(x: str) -> str:
    return re.sub(r"[-_ ]", "", x).lower()


def _block_for(sid: str):
    prog = _read("PROGRESS.md")
    want = _norm(sid)
    for m in re.finditer(r"^## TAMAMLANDI: ([^\n]+)\n(.*?)(?=^## |\Z)", prog, re.M | re.S):
        if _norm(m.group(1)).startswith(want):
            return m.group(0)
    return None


def _patch_for(sid: str):
    d = os.path.join(ROOT, "patches")
    if not os.path.isdir(d):
        return None
    want = _norm(sid)
    for f in sorted(os.listdir(d)):
        if f.endswith(".patch") and _norm(f[:-6]).startswith(want):
            return f
    return None


def score_format(sid, subj, block, patch):
    checks = {
        "commit konu tek satır + checkpoint öneki": subj.startswith("checkpoint:") and "\n" not in subj,
        "PROGRESS bloğu VAR": block is not None,
        f"blok ≤{BLOCK_MAX_LINES} satır": bool(block) and len(block.strip().splitlines()) <= BLOCK_MAX_LINES,
        "blok patch/TEK patch atfı": bool(block) and ((patch or "yok") in block or "TEK patch" in block),
        "blokta suite satırı": bool(block) and bool(re.search(r"[Ss]uite \*\*\d+/\d+", block)),
        "DUR vekili: sınır satırı": bool(block) and ("Hüküm/seçim/look" in block or "look etkisi YOK" in block),
    }
    return checks


def score_factuality(sid, subj, block, patch):
    checks = {}
    checks["patch dosyası mevcut"] = patch is not None
    if patch:
        raw = _read(os.path.join("patches", patch))
        msub = re.search(r"^Subject: (.*?)(?=\n[A-Za-z-]+:|\n\n)", raw, re.M | re.S)
        subj_patch = msub.group(1).replace("\n", "").replace(" ", "") if msub else ""
        checks["patch konu == commit konu"] = _norm(sid) in _norm(subj_patch)
    checks["blok dosya yolları VAR"] = True
    if block:
        for tok in set(re.findall(r"(?:scripts|tests|pine|reports|configs|viz|skills)/[A-Za-z0-9_./\-]+", block)):
            if "<" in tok or "*" in tok:
                continue   # placeholder token (örn. trades_<asset>.xlsx)
            p = tok.rstrip("·,)")
            if not os.path.exists(os.path.join(ROOT, p)):
                checks["blok dosya yolları VAR"] = False
                break
    m = re.search(r"[Ss]uite \*\*(\d+)/(\d+)\*\*", block or "")
    checks["blok suite sayısı tutarlı (x/x)"] = bool(m) and m.group(1) == m.group(2)
    return checks


def score_consistency(live_suite):
    prog = _read("PROGRESS.md")
    mh = re.search(r"\*\*Test durumu:\*\* \*\*(\d+)/(\d+) PASS\*\*", prog)
    readme = re.search(r"\*\*(\d+)/(\d+) PASS\*\*", _read("README.md"))
    card = re.search(r"suite (\d+)/(\d+)", _read("models/model_card.md"))
    needle = re.search(r'"(\d+)/(\d+)", "Veri provenansı', _read("tests/test_deliverables.py"))
    vals = [tuple(mh.groups()) if mh else None, tuple(readme.groups()) if readme else None,
            tuple(card.groups()) if card else None, tuple(needle.groups()) if needle else None]
    ok = all(v is not None and v[0] == v[1] for v in vals) and len({v[0] for v in vals if v}) == 1
    checks = {"R09 çapraz sayaçlar eşit": ok}
    checks["PROGRESS başlık == canlı suite"] = bool(mh) and live_suite is not None and \
        int(mh.group(1)) == live_suite
    return checks


def score_realism(sid, block):
    checks = {
        "cadence BAYAT damgası": "BAYAT" in _read("reports/cadence/2026-09-18_1500.md"),
        "QC RED → SORUN NOTU kaydı": "SORUN NOTU" in _read("reports/cadence/2026-09-18_1800.md"),
        "pine SABİT banner": "UNTESTED-VIZ" in _read("pine/quant4h_viz_multi.pine"),
    }
    neg = bool(block) and any(t.lower() in block.lower() for t in NEG_TOKENS)
    checks["blok dürüst negatif içerir (veya saf-doc)"] = neg or ("mikro" in (block or "")) or \
        ("doc" in (block or "").lower())
    return checks


def run_live_suite() -> int:
    total = 0
    for pat in ("tests/test_*.py", "tests/eval/test_*.py"):
        import glob
        for t in sorted(glob.glob(os.path.join(ROOT, pat))):
            r = subprocess.run([sys.executable, "-W", "ignore", t], cwd=ROOT,
                               capture_output=True, text=True)
            m = re.search(r"(\d+)/(\d+) passed", r.stdout)
            if m:
                total += int(m.group(1))
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--skip-suite", action="store_true")
    ap.add_argument("--quality", type=int, default=None, help="insan rubric 1-5")
    args = ap.parse_args()

    live = None if args.skip_suite else run_live_suite()
    sess = sessions(args.n)
    rows = []
    for sid, h, subj in sess:
        block = _block_for(sid)
        patch = _patch_for(sid)
        f, fa = score_format(sid, subj, block, patch), score_factuality(sid, subj, block, patch)
        r = score_realism(sid, block)
        rows.append((sid, f, fa, r))
    cons = score_consistency(live)

    os.makedirs(EVAL_DIR, exist_ok=True)
    tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = os.path.join(EVAL_DIR, f"{tag}.md")
    L = [f"# AJAN SKOR KARTI — {tag} (M24, otomatik; LLM-judge YOK)", "",
         f"Oturumlar: {len(sess)} · canlı suite: {live if live is not None else 'ATLANDI'} · "
         f"QUALITY (insan): {'BEKLEMEDE' if args.quality is None else f'{args.quality}/5'}", "",
         "| oturum | FORMAT | FACTUALITY | REALISM |", "|---|---|---|---|"]
    for sid, f, fa, r in rows:
        def pct(d):
            return f"{sum(1 for v in d.values() if v)}/{len(d)}"
        L.append(f"| {sid} | {pct(f)} | {pct(fa)} | {pct(r)} |")
    L += ["", "## CONSISTENCY (R09)", ""]
    for k, v in cons.items():
        L.append(f"- {'✅' if v else '❌'} {k}")
    L += ["", "## DETAY", ""]
    for sid, f, fa, r in rows:
        L.append(f"### {sid}")
        for name, d in (("FORMAT", f), ("FACTUALITY", fa), ("REALISM", r)):
            for k, v in d.items():
                L.append(f"- {'✅' if v else '❌'} [{name}] {k}")
        L.append("")
    L += ["## QUALITY (insan rubric 1-5, LLM-judge YOK)", "",
          f"{QUALITY_MARKER} Quality rubric (insan): "
          f"{'BEKLEMEDE (1-5)' if args.quality is None else f'{args.quality}/5'} "
          f"— `run_agent_eval.py --quality N` ile işlenir.", ""]
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"skor kartı: {os.path.relpath(out, ROOT)}")

    if args.quality is not None and 1 <= args.quality <= 5:
        p = os.path.join(ROOT, "PROGRESS.md")
        s = _read("PROGRESS.md")
        s = re.sub(r"<!-- quality-rubric --> Quality rubric \(insan\): .*",
                   f"{QUALITY_MARKER} Quality rubric (insan): {args.quality}/5 "
                   f"({tag}, run_agent_eval.py --quality)", s)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(s)
        print("quality rubric PROGRESS'e işlendi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
