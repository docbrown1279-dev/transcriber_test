# 3c sources — two files

Agents read **only** these:

| File | What |
|---|---|
| `transcript.md` | Full meeting: GigaAM v3, **gold spliced** into four eval windows (same as 3b hybrid). One utterance per line with its clock. |
| `chapters.json` | Twelve **D** (Jina) chapter clocks from stage 2b, plus `gold_windows`. No titles. |

Rebuild (local; needs hybrid in `.trash`/`data/3b_data`, or `eval/` + ASR JSON). Cloud: files are already here — do not rebuild, do not read `eval/`.

```bash
python scripts/stage3c_pack.py
python scripts/stage3c_pack.py --slice   # optional, writes gitignored `_slices/`
```

Do not use `data/3b_data/` as extract input. No C. Pipeline: [`docs/prompts/stage3c.md`](../../docs/prompts/stage3c.md).
