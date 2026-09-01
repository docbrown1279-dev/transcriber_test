# 3c sources — two files

Agents read **only** these:

| File | What |
|---|---|
| `transcript.md` | Full-meeting ASR (GigaAM v3). One utterance per line with its clock. |
| `chapters.json` | Twelve **D** (Jina) chapter clocks from stage 2b. No titles. |

Rebuild (needs gitignored `results/asr/2/…/meeting_sample.json` **or** an existing `transcript.md`):

```bash
python scripts/stage3c_pack.py
python scripts/stage3c_pack.py --slice   # optional, writes gitignored `_slices/`
```

Do not use `data/3b_data/` (archive / `.trash`). No C. No gold. Pipeline: [`docs/prompts/stage3c.md`](../../docs/prompts/stage3c.md).
