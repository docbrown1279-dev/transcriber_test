#!/usr/bin/env python3
"""WER/CER for Stage 1e hypotheses vs local gold (eval/, gitignored).

Corpus metrics concatenate time-sorted segments.
Per-gold metrics concatenate all overlapping hypothesis turns.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = ROOT / "eval"
HYP_ROOT = ROOT / "results/asr/1e/eval_clips"

CLIPS = ("test_voice", "test_apartments", "test_transformers", "test_ninth")
MODELS = (
    "gigaam_v3",
    "gigaam_v3_ungained",
    "podlodka_turbo",
    "faster_whisper_large_v3",
    "podlodka_large_v3_ru",
)
MIN_OVERLAP = 0.15
ERROR_FLAG = 2  # more than this many word errors → inspect


def norm_text(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> list[str]:
    return [t for t in norm_text(s).split() if t]


def chars(s: str) -> list[str]:
    return list(norm_text(s))


def word_ops(ref: list[str], hyp: list[str]) -> tuple[int, int, int, int]:
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


def edit_distance(ref: list[str], hyp: list[str]) -> int:
    n, m = len(ref), len(hyp)
    prev = list(range(m + 1))
    for i, ca in enumerate(ref, 1):
        cur = [i] + [0] * m
        for j, cb in enumerate(hyp, 1):
            if ca == cb:
                cur[j] = prev[j - 1]
            else:
                cur[j] = 1 + min(prev[j - 1], prev[j], cur[j - 1])
        prev = cur
    return prev[m]


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


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
                "uncertain": bool(s.get("uncertain")),
            }
        )
    return out


def latinish(text: str) -> bool:
    return bool(re.search(r"[a-zA-Z]{4,}", text or ""))


def best_window_ops(ref: list[str], hyp: list[str]) -> tuple[int, int, int, int]:
    """Word ops against the best hyp span, so a long pyannote turn is not all insertions."""
    if not ref:
        return (0, 0, 0, len(hyp))
    if not hyp:
        return (0, 0, len(ref), 0)
    best = word_ops(ref, hyp)
    best_err = best[1] + best[2] + best[3]
    n = len(ref)
    w_lo = max(1, n - 4)
    w_hi = min(len(hyp), n + 10)
    for w in range(w_lo, w_hi + 1):
        for start in range(0, len(hyp) - w + 1):
            ops = word_ops(ref, hyp[start : start + w])
            err = ops[1] + ops[2] + ops[3]
            if err < best_err:
                best_err = err
                best = ops
            if err == 0:
                return best
    return best


def score_pair(gold: list[dict], hyp: list[dict]) -> dict:
    gold_sorted = sorted(gold, key=lambda s: (s["start"], s["end"]))
    hyp_sorted = sorted(hyp, key=lambda s: (s["start"], s["end"]))
    gold_toks = tokens(" ".join(s["text"] for s in gold_sorted))
    hyp_toks = tokens(" ".join(s["text"] for s in hyp_sorted))
    gold_chars = chars(" ".join(s["text"] for s in gold_sorted))
    hyp_chars = chars(" ".join(s["text"] for s in hyp_sorted))
    m, s, d, i = word_ops(gold_toks, hyp_toks)
    errors = s + d + i
    corpus_wer = errors / len(gold_toks) if gold_toks else 0.0
    corpus_cer = (
        edit_distance(gold_chars, hyp_chars) / len(gold_chars) if gold_chars else 0.0
    )

    phrases = []
    cov_m = cov_s = cov_d = cov_i = 0
    cov_gold_words = 0
    cov_gold_chars = 0
    cov_char_edits = 0
    missed_words = 0
    for g in gold_sorted:
        gtok = tokens(g["text"])
        if not gtok:
            continue
        overlapping = [
            h
            for h in hyp_sorted
            if overlap(g["start"], g["end"], h["start"], h["end"]) >= MIN_OVERLAP
        ]
        hyp_text = " ".join(h["text"] for h in overlapping)
        htok = tokens(hyp_text)
        if not overlapping:
            missed_words += len(gtok)
            phrases.append(
                {
                    "gold_id": g["id"],
                    "start": round(g["start"], 2),
                    "end": round(g["end"], 2),
                    "gold_speaker": g["speaker"],
                    "uncertain": g["uncertain"],
                    "status": "missed",
                    "gold_words": len(gtok),
                    "errors": len(gtok),
                    "S": 0,
                    "D": len(gtok),
                    "I": 0,
                    "wer": 1.0,
                    "cer": 1.0,
                    "gold": g["text"].strip(),
                    "hyp": "",
                    "latin_in_hyp": False,
                }
            )
            continue
        pm, ps, pd, pi = best_window_ops(gtok, htok)
        perr = ps + pd + pi
        gch = chars(g["text"])
        hch = chars(hyp_text)
        cer = edit_distance(gch, hch) / len(gch) if gch else 0.0
        cov_m += pm
        cov_s += ps
        cov_d += pd
        cov_i += pi
        cov_gold_words += len(gtok)
        cov_gold_chars += len(gch)
        cov_char_edits += edit_distance(gch, hch)
        status = "ok"
        if perr > ERROR_FLAG:
            status = "high_error"
        phrases.append(
            {
                "gold_id": g["id"],
                "start": round(g["start"], 2),
                "end": round(g["end"], 2),
                "gold_speaker": g["speaker"],
                "uncertain": g["uncertain"],
                "status": status,
                "gold_words": len(gtok),
                "errors": perr,
                "S": ps,
                "D": pd,
                "I": pi,
                "wer": round(perr / len(gtok), 3) if gtok else 0.0,
                "cer": round(cer, 3),
                "gold": g["text"].strip(),
                "hyp": hyp_text.strip(),
                "latin_in_hyp": latinish(hyp_text),
            }
        )

    covered_wer = (
        (cov_s + cov_d + cov_i) / cov_gold_words if cov_gold_words else None
    )
    covered_cer = cov_char_edits / cov_gold_chars if cov_gold_chars else None
    gold_n = len(gold_toks)
    cer_edits = edit_distance(gold_chars, hyp_chars)
    return {
        "gold_words": gold_n,
        "gold_chars": len(gold_chars),
        "hyp_words": len(hyp_toks),
        "corpus_wer": round(corpus_wer, 4),
        "corpus_cer": round(corpus_cer, 4),
        "corpus_cer_edits": cer_edits,
        "covered_wer": None if covered_wer is None else round(covered_wer, 4),
        "covered_cer": None if covered_cer is None else round(covered_cer, 4),
        "S": s,
        "D": d,
        "I": i,
        "missed_gold_words": missed_words,
        "missed_word_share": round(missed_words / gold_n, 4) if gold_n else 0.0,
        "phrases": phrases,
    }


def main() -> None:
    report: dict = {"min_overlap_sec": MIN_OVERLAP, "error_flag_gt": ERROR_FLAG, "clips": {}, "models": {}}
    for clip in CLIPS:
        gold = load_segments(GOLD_DIR / f"{clip}.json")
        report["clips"][clip] = {
            "gold_segments": len(gold),
            "gold_words": sum(len(tokens(s["text"])) for s in gold),
        }
    for model in MODELS:
        model_row: dict = {"per_clip": {}, "macro": {}}
        wers = []
        cers = []
        cwers = []
        ccers = []
        flagged = []
        latin_segs = 0
        hyp_segs = 0
        for clip in CLIPS:
            hyp_path = HYP_ROOT / model / f"{clip}.json"
            gold = load_segments(GOLD_DIR / f"{clip}.json")
            hyp = load_segments(hyp_path)
            hyp_segs += len(hyp)
            latin_segs += sum(1 for h in hyp if latinish(h["text"]))
            scored = score_pair(gold, hyp)
            phrases = scored.pop("phrases")
            model_row["per_clip"][clip] = scored
            wers.append(scored["corpus_wer"])
            cers.append(scored["corpus_cer"])
            if scored["covered_wer"] is not None:
                cwers.append(scored["covered_wer"])
            if scored["covered_cer"] is not None:
                ccers.append(scored["covered_cer"])
            for p in phrases:
                if p["status"] in {"high_error", "missed"} or p["latin_in_hyp"]:
                    flagged.append({"clip": clip, **p})
        micro_w = micro_e = micro_cden = micro_cedit = 0
        for clip in CLIPS:
            c = model_row["per_clip"][clip]
            micro_w += c["gold_words"]
            micro_e += c["S"] + c["D"] + c["I"]
            micro_cden += c["gold_chars"]
            micro_cedit += c["corpus_cer_edits"]
        model_row["macro"] = {
            "corpus_wer": round(sum(wers) / len(wers), 4),
            "corpus_cer": round(sum(cers) / len(cers), 4),
            "covered_wer": round(sum(cwers) / len(cwers), 4) if cwers else None,
            "covered_cer": round(sum(ccers) / len(ccers), 4) if ccers else None,
        }
        model_row["micro"] = {
            "corpus_wer": round(micro_e / micro_w, 4) if micro_w else 0.0,
            "corpus_cer": round(micro_cedit / micro_cden, 4) if micro_cden else 0.0,
            "gold_words": micro_w,
            "errors": micro_e,
            "latin_hyp_segments": latin_segs,
            "hyp_segments": hyp_segs,
        }
        model_row["flagged"] = flagged
        report["models"][model] = model_row

    out = ROOT / "results/reports/1e/wer_cer.json"
    public = {
        "min_overlap_sec": MIN_OVERLAP,
        "error_flag_gt": ERROR_FLAG,
        "notes": "Phrase texts live in gitignored eval/1e_wer_review.json (gold). Numeric scores only here.",
        "clips": report["clips"],
        "models": {},
    }
    for model in MODELS:
        row = report["models"][model]
        public["models"][model] = {
            "macro": row["macro"],
            "micro": row["micro"],
            "per_clip": {
                k: {kk: vv for kk, vv in v.items() if kk != "phrases"}
                for k, v in row["per_clip"].items()
            },
            "flagged_counts": {
                "missed": sum(1 for p in row["flagged"] if p["status"] == "missed"),
                "high_error": sum(1 for p in row["flagged"] if p["status"] == "high_error"),
                "latin": sum(1 for p in row["flagged"] if p.get("latin_in_hyp")),
            },
        }
    out.write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
    review = ROOT / "eval/1e_wer_review.json"
    review.write_text(
        json.dumps(
            {
                "models": {
                    m: {"flagged": report["models"][m]["flagged"]} for m in MODELS
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"{'model':<28} {'µWER':>7} {'µCER':>7} {'macWER':>7} {'macCER':>7} "
        f"{'spanWER':>7} {'latin':>6}"
    )
    for model in MODELS:
        mac = report["models"][model]["macro"]
        mic = report["models"][model]["micro"]
        print(
            f"{model:<28} {mic['corpus_wer']:7.3f} {mic['corpus_cer']:7.3f} "
            f"{mac['corpus_wer']:7.3f} {mac['corpus_cer']:7.3f} "
            f"{mac['covered_wer']:7.3f} {mic['latin_hyp_segments']:6d}"
        )
    print("\nPer clip corpus WER / CER")
    header = f"{'clip':<20}" + "".join(f"{m[:12]:>13}" for m in MODELS)
    print(header)
    for clip in CLIPS:
        row = f"{clip:<20}"
        for model in MODELS:
            c = report["models"][model]["per_clip"][clip]
            row += f"{c['corpus_wer']:.2f}/{c['corpus_cer']:.2f}".rjust(13)
        print(row)
    print(f"\nwrote {out}")
    print(f"wrote {review}")


if __name__ == "__main__":
    main()
