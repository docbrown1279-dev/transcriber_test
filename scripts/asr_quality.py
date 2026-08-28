#!/usr/bin/env python3
"""Russian word-ratio and OOV heuristics for ASR transcripts."""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)?", re.UNICODE)
CYR_RE = re.compile(r"[А-Яа-яЁё]")


def tokenize(text: str) -> list[str]:
    return WORD_RE.findall(text)


def is_mostly_cyrillic(word: str) -> bool:
    letters = [c for c in word if c.isalpha()]
    if not letters:
        return False
    cyr = sum(1 for c in letters if CYR_RE.match(c))
    return cyr / len(letters) >= 0.5


def morph_known(word: str, morph) -> bool:
    parses = morph.parse(word)
    if not parses:
        return False
    # Unknown / rare tags often still parse; treat score==0 and tag.UNKN as OOV-ish
    best = parses[0]
    tag = str(best.tag)
    if "UNKN" in tag:
        return False
    return True


def pick_fragments(text: str, n: int = 3) -> list[str]:
    # Split into sentence-ish chunks
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    parts = [p.strip() for p in parts if len(p.strip()) > 20]
    if len(parts) < 2:
        # fallback: fixed windows
        words = text.split()
        if len(words) < 12:
            return [text] if text else []
        frags = []
        for i in range(0, len(words) - 10, max(10, len(words) // (n + 1))):
            frags.append(" ".join(words[i : i + 18]))
        parts = frags
    if not parts:
        return []
    k = min(n, len(parts))
    # Prefer middle-ish samples for stability
    idxs = sorted(random.sample(range(len(parts)), k=k))
    out = []
    for i in idxs:
        # try to take ~2 sentences
        chunk = parts[i]
        if i + 1 < len(parts):
            chunk = chunk + " " + parts[i + 1]
        out.append(chunk)
    return out


def judge_fragments(fragments: list[str]) -> tuple[str, list[dict]]:
    """Heuristic human-like check: nonsense Russian-looking word salad fails."""
    notes = []
    bad = 0
    for frag in fragments:
        words = tokenize(frag)
        if not words:
            bad += 1
            notes.append({"fragment": frag[:200], "verdict": "bad", "reason": "empty"})
            continue
        # Repeated single tokens, extreme short unique vocab, or Latin soup
        uniq = set(w.lower() for w in words)
        cyr_ratio = sum(1 for w in words if is_mostly_cyrillic(w)) / len(words)
        rep = max(words.count(w) for w in words) / len(words)
        reasons = []
        if cyr_ratio < 0.7:
            reasons.append(f"low_cyr={cyr_ratio:.2f}")
        if len(uniq) <= max(3, len(words) // 8) and len(words) > 15:
            reasons.append("low_vocab_diversity")
        if rep > 0.35 and len(words) > 12:
            reasons.append(f"high_repetition={rep:.2f}")
        # Whisper failure modes: music lyrics loops / language switches
        lower = frag.lower()
        if any(x in lower for x in ("字幕", "thank you for watching", "subscribe")):
            reasons.append("boilerplate")
        verdict = "bad" if reasons else "ok"
        if verdict == "bad":
            bad += 1
        notes.append({"fragment": frag[:400], "verdict": verdict, "reasons": reasons})
    sample_check = "bad" if bad >= max(1, (len(fragments) + 1) // 2) else "ok"
    if not fragments:
        sample_check = "bad"
    return sample_check, notes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", required=True, help="ASR JSON or plain text")
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    import pymorphy3

    random.seed(args.seed)
    path = Path(args.transcript)
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(raw)
        text = data.get("text") or " ".join(s.get("text", "") for s in data.get("segments", []))
    else:
        text = raw

    morph = pymorphy3.MorphAnalyzer()
    words = tokenize(text)
    cyr_words = [w for w in words if is_mostly_cyrillic(w)]
    rw_ratio = (len(cyr_words) / len(words)) if words else 0.0

    oov = []
    for w in cyr_words:
        if not morph_known(w, morph):
            oov.append(w)
    # unique, preserve order, cap
    seen = set()
    oov_unique = []
    for w in oov:
        key = w.lower()
        if key not in seen:
            seen.add(key)
            oov_unique.append(w)
        if len(oov_unique) >= 200:
            break

    fragments = pick_fragments(text, n=3)
    sample_check, fragment_notes = judge_fragments(fragments)
    gate_pass = rw_ratio >= 0.9 and sample_check == "ok"

    result = {
        "source": str(path),
        "word_count": len(words),
        "cyr_word_count": len(cyr_words),
        "rw_ratio": round(rw_ratio, 4),
        "oo_words": oov_unique,
        "oov_count": len(oov_unique),
        "sample_check": sample_check,
        "fragments": fragment_notes,
        "gate_pass": gate_pass,
        "status": "success" if gate_pass else "fail",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("rw_ratio", "sample_check", "gate_pass", "oov_count", "status")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
