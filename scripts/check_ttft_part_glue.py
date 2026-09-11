#!/usr/bin/env python3
"""Glue-check part01 transcript + chapters vs prior full-run windows (not gold).

Chapters == packing-C chunks. No cloud agent required — pure local code.

Checks
------
Transcript window:
  T1 time order, T2 no big overlaps, T3 inside part, T4 word coverage vs baseline,
  T5 length ratio (catch dropped/duplicated text).

Chapters (chunks) window:
  C0 nonempty, C1 time order, C2 no overlap, C3 inside part,
  C4 speech-coverage vs baseline chapter union (soft; packing on part-only may differ),
  C5 count sanity vs baseline (WARN if far).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+", re.UNICODE)


def _words(text: str) -> list[str]:
    return [m.group(0).casefold() for m in _WORD_RE.finditer(text or "")]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _segments(doc: dict[str, Any]) -> list[dict[str, Any]]:
    if "segments" in doc:
        return list(doc["segments"])
    raise ValueError(f"expected segments[] in {doc.keys()}")


def _chapters(doc: dict[str, Any]) -> list[dict[str, Any]]:
    if "chapters" in doc:
        return list(doc["chapters"])
    raise ValueError(f"expected chapters[] in {doc.keys()}")


def _part_end(doc: dict[str, Any], fallback: float = 0.0) -> float:
    part = doc.get("part") or {}
    return float(part.get("end", fallback))


def _intervals(items: list[dict[str, Any]]) -> list[tuple[float, float]]:
    out = [(float(x["start"]), float(x["end"])) for x in items]
    out.sort(key=lambda x: x[0])
    return out


def _merge_union(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_s, last_e = merged[-1]
        if start <= last_e + 1e-6:
            merged[-1] = (last_s, max(last_e, end))
        else:
            merged.append((start, end))
    return merged


def _span(intervals: list[tuple[float, float]]) -> float:
    return sum(max(0.0, e - s) for s, e in intervals)


def _intersection_span(
    a: list[tuple[float, float]], b: list[tuple[float, float]]
) -> float:
    i = j = 0
    total = 0.0
    aa, bb = _merge_union(a), _merge_union(b)
    while i < len(aa) and j < len(bb):
        s = max(aa[i][0], bb[j][0])
        e = min(aa[i][1], bb[j][1])
        if e > s:
            total += e - s
        if aa[i][1] < bb[j][1]:
            i += 1
        else:
            j += 1
    return total


def check_transcript(hyp: dict[str, Any], baseline: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    part_end = _part_end(baseline, 1e9)
    hyp_segs = _segments(hyp)
    base_segs = _segments(baseline)

    starts = [float(s["start"]) for s in hyp_segs]
    findings.append(
        {
            "id": "T1_time_order",
            "status": "PASS" if starts == sorted(starts) else "FAIL",
            "detail": "ok" if starts == sorted(starts) else "hyp segments not sorted",
        }
    )

    overlaps = sum(
        1
        for a, b in zip(hyp_segs, hyp_segs[1:], strict=False)
        if float(a["end"]) - float(b["start"]) > 0.25
    )
    findings.append(
        {
            "id": "T2_overlap",
            "status": "PASS" if overlaps == 0 else "WARN",
            "detail": f"overlaps>0.25s={overlaps}",
        }
    )

    max_end = max((float(s["end"]) for s in hyp_segs), default=0.0)
    findings.append(
        {
            "id": "T3_inside_part",
            "status": "PASS" if max_end <= part_end + 1.0 else "FAIL",
            "detail": f"max_end={max_end:.3f} part_end={part_end:.3f}",
        }
    )

    hyp_text = " ".join((s.get("text") or "").strip() for s in hyp_segs)
    base_text = baseline.get("text_concat") or " ".join(
        (s.get("text") or "").strip() for s in base_segs
    )
    hw, bw = _words(hyp_text), _words(base_text)
    if not bw:
        cov = 1.0
    else:
        bag = set(hw)
        cov = sum(1 for w in bw if w in bag) / len(bw)
    set_h, set_b = set(hw), set(bw)
    jacc = (len(set_h & set_b) / len(set_h | set_b)) if (set_h or set_b) else 1.0
    findings.append(
        {
            "id": "T4_text_coverage",
            "status": "PASS" if cov >= 0.85 else ("WARN" if cov >= 0.70 else "FAIL"),
            "detail": (
                f"baseline_word_coverage={cov:.3f} jaccard={jacc:.3f} "
                f"hyp_words={len(hw)} base_words={len(bw)}"
            ),
        }
    )

    ratio = (len(hw) / len(bw)) if bw else 1.0
    findings.append(
        {
            "id": "T5_length_ratio",
            "status": "PASS" if 0.75 <= ratio <= 1.35 else "WARN",
            "detail": f"hyp/base word ratio={ratio:.3f}",
        }
    )
    return findings


def check_chapters(
    hyp: dict[str, Any],
    baseline: dict[str, Any],
    *,
    part_end: float,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    hyp_ch = _chapters(hyp)
    base_ch = _chapters(baseline)

    if not hyp_ch:
        findings.append({"id": "C0_nonempty", "status": "FAIL", "detail": "no chapters"})
        return findings
    findings.append(
        {
            "id": "C0_nonempty",
            "status": "PASS",
            "detail": f"hyp_n={len(hyp_ch)} baseline_n={len(base_ch)}",
        }
    )

    starts = [float(c["start"]) for c in hyp_ch]
    findings.append(
        {
            "id": "C1_time_order",
            "status": "PASS" if starts == sorted(starts) else "FAIL",
            "detail": "ok" if starts == sorted(starts) else "not sorted by start",
        }
    )

    overlap = sum(
        1
        for a, b in zip(hyp_ch, hyp_ch[1:], strict=False)
        if float(a["end"]) - float(b["start"]) > 0.25
    )
    findings.append(
        {
            "id": "C2_no_overlap",
            "status": "PASS" if overlap == 0 else "FAIL",
            "detail": f"overlaps={overlap}",
        }
    )

    max_end = max(float(c["end"]) for c in hyp_ch)
    findings.append(
        {
            "id": "C3_inside_part",
            "status": "PASS" if max_end <= part_end + 1.0 else "FAIL",
            "detail": f"max_end={max_end:.3f} part_end={part_end:.3f}",
        }
    )

    hyp_iv = _intervals(hyp_ch)
    base_iv = _intervals(base_ch)
    inter = _intersection_span(hyp_iv, base_iv)
    base_span = _span(_merge_union(base_iv)) or 1e-9
    hyp_span = _span(_merge_union(hyp_iv)) or 1e-9
    recall = inter / base_span  # baseline speech timeline covered by hyp chapters
    precision = inter / hyp_span
    findings.append(
        {
            "id": "C4_timeline_vs_baseline",
            "status": (
                "PASS"
                if recall >= 0.80 and precision >= 0.80
                else ("WARN" if recall >= 0.60 and precision >= 0.60 else "FAIL")
            ),
            "detail": (
                f"recall={recall:.3f} precision={precision:.3f} "
                f"inter={inter:.1f}s base={base_span:.1f}s hyp={hyp_span:.1f}s"
            ),
        }
    )

    if base_ch:
        ratio = len(hyp_ch) / len(base_ch)
        findings.append(
            {
                "id": "C5_count_vs_baseline",
                "status": "PASS" if 0.5 <= ratio <= 2.0 else "WARN",
                "detail": f"hyp_n/base_n={ratio:.2f} ({len(hyp_ch)}/{len(base_ch)})",
            }
        )
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hyp-transcript", type=Path, required=True)
    ap.add_argument("--hyp-chapters", type=Path, required=True)
    ap.add_argument(
        "--baseline-transcript",
        type=Path,
        default=Path("eval/d5_ttft_split/baseline_part01_transcript_window.json"),
    )
    ap.add_argument(
        "--baseline-chapters",
        type=Path,
        default=Path("eval/d5_ttft_split/baseline_part01_chapters_window.json"),
    )
    ap.add_argument("--out-json", type=Path, required=True)
    args = ap.parse_args()

    base_t = _load(args.baseline_transcript)
    base_c = _load(args.baseline_chapters)
    part_end = _part_end(base_t) or _part_end(base_c)

    findings = check_transcript(_load(args.hyp_transcript), base_t)
    findings.extend(
        check_chapters(_load(args.hyp_chapters), base_c, part_end=part_end)
    )

    fails = sum(1 for f in findings if f["status"] == "FAIL")
    warns = sum(1 for f in findings if f["status"] == "WARN")
    report = {
        "schema_version": "1",
        "verdict": "FAIL" if fails else ("WARN" if warns else "PASS"),
        "fail_count": fails,
        "warn_count": warns,
        "part_end_sec": part_end,
        "findings": findings,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
