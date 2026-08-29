#!/usr/bin/env python3
"""Compare a hypothesis JSON to local gold (eval/, gitignored).

Match segments by approximate time, then count matching words vs
substitution / deletion / insertion on the rest.

  python3 scripts/compare_eval.py path/to/hypothesis.json --gold eval/test_voice.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def norm_text(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> list[str]:
    return [t for t in norm_text(s).split() if t]


def load_segments(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    segs = data["segments"] if isinstance(data, dict) else data
    out = []
    for i, s in enumerate(segs):
        out.append(
            {
                "id": s.get("id", i),
                "start": float(s["start"]),
                "end": float(s["end"]),
                "text": s.get("text") or "",
                "speaker": s.get("speaker"),
            }
        )
    return out


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def gap(a0: float, a1: float, b0: float, b1: float) -> float:
    if overlap(a0, a1, b0, b1) > 0:
        return 0.0
    if a1 <= b0:
        return b0 - a1
    return a0 - b1


def word_ops(ref: list[str], hyp: list[str]) -> tuple[int, int, int, int]:
    """Return (match, sub, delete, insert) via Levenshtein traceback."""
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    bt = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
        bt[i][0] = "D"
    for j in range(1, m + 1):
        dp[0][j] = j
        bt[0][j] = "I"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
                bt[i][j] = "M"
            else:
                sub = dp[i - 1][j - 1] + 1
                dele = dp[i - 1][j] + 1
                ins = dp[i][j - 1] + 1
                best = min(sub, dele, ins)
                dp[i][j] = best
                bt[i][j] = "S" if best == sub else ("D" if best == dele else "I")
    i, j = n, m
    match = sub = dele = ins = 0
    while i > 0 or j > 0:
        op = bt[i][j]
        if op == "M":
            match += 1
            i -= 1
            j -= 1
        elif op == "S":
            sub += 1
            i -= 1
            j -= 1
        elif op == "D":
            dele += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return match, sub, dele, ins


def pair_segments(
    gold: list[dict], hyp: list[dict], collar: float
) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    """Greedy one-to-one: max overlap, else nearest if gap <= collar."""
    used: set[int] = set()
    pairs: list[tuple[dict, dict]] = []
    for g in gold:
        best_j = None
        best_ov = -1.0
        for j, h in enumerate(hyp):
            if j in used:
                continue
            ov = overlap(g["start"], g["end"], h["start"], h["end"])
            if ov > best_ov:
                best_ov = ov
                best_j = j
        if best_j is not None and best_ov > 0:
            used.add(best_j)
            pairs.append((g, hyp[best_j]))
            continue
        best_j = None
        best_gap = None
        for j, h in enumerate(hyp):
            if j in used:
                continue
            d = gap(g["start"], g["end"], h["start"], h["end"])
            if best_gap is None or d < best_gap:
                best_gap = d
                best_j = j
        if best_j is not None and best_gap is not None and best_gap <= collar:
            used.add(best_j)
            pairs.append((g, hyp[best_j]))
    unmatched_g = [g for g in gold if all(g is not a for a, _ in pairs)]
    unmatched_h = [h for j, h in enumerate(hyp) if j not in used]
    return pairs, unmatched_g, unmatched_h


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare hypothesis to local gold.")
    parser.add_argument("hypothesis", type=Path)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument(
        "--collar",
        type=float,
        default=0.5,
        help="max gap in seconds to still pair segments (default 0.5)",
    )
    args = parser.parse_args()

    if not args.gold.is_file():
        print(f"No gold at {args.gold} (local-only eval/). Nothing to score.", file=sys.stderr)
        return 2
    if not args.hypothesis.is_file():
        print(f"No hypothesis at {args.hypothesis}", file=sys.stderr)
        return 2

    gold = load_segments(args.gold)
    hyp = load_segments(args.hypothesis)
    pairs, miss_g, extra_h = pair_segments(gold, hyp, args.collar)

    match = sub = dele = ins = 0
    start_err: list[float] = []
    for g, h in pairs:
        m, s, d, i = word_ops(tokens(g["text"]), tokens(h["text"]))
        match += m
        sub += s
        dele += d
        ins += i
        start_err.append(abs(g["start"] - h["start"]))
    for g in miss_g:
        dele += len(tokens(g["text"]))
    for h in extra_h:
        ins += len(tokens(h["text"]))

    gold_n = sum(len(tokens(s["text"])) for s in gold)
    hyp_n = sum(len(tokens(s["text"])) for s in hyp)
    errors = sub + dele + ins
    wer = errors / gold_n if gold_n else 0.0
    start_err.sort()
    med_start = start_err[len(start_err) // 2] if start_err else None

    print(f"gold={args.gold}  hyp={args.hypothesis}")
    print(f"segments  gold={len(gold)} hyp={len(hyp)} paired={len(pairs)} missed={len(miss_g)} extra={len(extra_h)}")
    print(f"words     gold={gold_n} hyp={hyp_n} matched={match} errors={errors} (S={sub} D={dele} I={ins})")
    print(f"wer={wer:.3f}  matched_ratio={match / gold_n if gold_n else 0:.3f}")
    if med_start is not None:
        print(f"median_|start_err|={med_start:.3f}s  collar={args.collar}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
