# 3b sources

Rebuild:

```bash
python scripts/asr_json_to_md.py --gold
```

`--gold` is local (`eval/`). Cloud agents use files that are already here; do not read `eval/`.

| File / folder | Give to the extractor? |
|---|---|
| `hybrid_asr_gold.md` | **no** — full meeting (GigaAM + gold in 4 windows). Self-check only |
| `full_asr.md` | no — same meeting, ASR only |
| `chunks_d/D00.md` … `D11.md` | **yes** — only stack (Jina / 2b D) |
| `chunks_d/_manifest.json` | clocks from 2b JSON |
| `chunks_d/_unassigned.md` | lines outside D intervals |

Pipeline: [`docs/prompts/stage3b.md`](../../docs/prompts/stage3b.md).
