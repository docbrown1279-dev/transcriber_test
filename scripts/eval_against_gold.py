#!/usr/bin/env python3
"""Score a local hypothesis JSON against eval/gold.json (gitignored)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path


def norm_text(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> list[str]:
    return [t for t in norm_text(s).split() if t]


def levenshtein(a: list[str], b: list[str]) -> tuple[int, int, int, int]:
    n, m = len(a), len(b)
    dp = list(range(m + 1))
    for i, ca in enumerate(a, 1):
        prev, dp[0] = dp[0], i
        for j, cb in enumerate(b, 1):
            cur = dp[j]
            if ca == cb:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = cur
    # dp[-1] is edit distance; split into S/D/I is approximate via distance only
    return dp[-1], n, m, max(n, 1)


def wer(ref: list[str], hyp: list[str]) -> float:
    dist, n, _m, _ = levenshtein(ref, hyp)
    return dist / n if n else 0.0


def tiou(a0: float, a1: float, b0: float, b1: float) -> float:
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    return inter / union if union > 0 else 0.0


def within_collar(g0: float, g1: float, p0: float, p1: float, collar: float) -> bool:
    return abs(g0 - p0) <= collar and abs(g1 - p1) <= collar


def load_segments(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    segs = data["segments"] if isinstance(data, dict) else data
    out = []
    for i, s in enumerate(segs):
        out.append(
            {
                "start": float(s["start"]),
                "end": float(s["end"]),
                "text": s.get("text") or "",
                "speaker": s.get("speaker"),
                "id": s.get("id", i),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("hypothesis", type=Path)
    parser.add_argument("--gold", type=Path, default=Path("eval/gold.json"))
    parser.add_argument("--collar", type=float, default=0.25)
    parser.add_argument("--tiou", type=float, default=0.5)
    args = parser.parse_args()

    if not args.gold.is_file():
        print(
            f"No gold file at {args.gold} (expected local-only). Nothing to score.",
            file=sys.stderr,
        )
        return 2

    gold = load_segments(args.gold)
    hyp = load_segments(args.hypothesis)
    gold_toks = tokens(" ".join(s["text"] for s in gold))
    hyp_toks = tokens(" ".join(s["text"] for s in hyp))
    print(f"wer={wer(gold_toks, hyp_toks):.4f}  gold_words={len(gold_toks)} hyp_words={len(hyp_toks)}")

    used = set()
    hits_iou = 0
    hits_collar = 0
    start_err = []
    end_err = []
    for g in gold:
        gtok = tokens(g["text"])
        if not gtok:
            continue
        best_j, best_r = None, -1.0
        for j, h in enumerate(hyp):
            if j in used:
                continue
            r = SequenceMatcher(None, gtok, tokens(h["text"])).ratio()
            if r > best_r:
                best_r, best_j = r, j
        if best_j is None or best_r < 0.6:
            continue
        used.add(best_j)
        h = hyp[best_j]
        iou = tiou(g["start"], g["end"], h["start"], h["end"])
        if iou >= args.tiou:
            hits_iou += 1
        if within_collar(g["start"], g["end"], h["start"], h["end"], args.collar):
            hits_collar += 1
        start_err.append(abs(g["start"] - h["start"]))
        end_err.append(abs(g["end"] - h["end"]))

    n = len([g for g in gold if tokens(g["text"])])
    print(f"aligned_pairs={len(start_err)}/{n}  (text ratio>=0.6)")
    print(f"recall_tIoU>={args.tiou:.2f}={hits_iou / n if n else 0:.3f}")
    print(f"recall_collar<={args.collar}s={hits_collar / n if n else 0:.3f}")
    if start_err:
        start_err.sort()
        end_err.sort()
        mid = len(start_err) // 2
        print(f"median_|start_err|={start_err[mid]:.3f}s  median_|end_err|={end_err[mid]:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
