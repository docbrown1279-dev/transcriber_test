# 1f baseline (tracked)

Copied from local Stage 1e `results/asr/eval_clips/` (gitignored). Not human gold.

- `pyannote31/` — merged turns, clock = eval clip (0 = start of `data/test_*.m4a`)
- `gigaam_v3_on_pyannote/` — GigaAM v3 text on those same cuts

Cloud agents: compare new ONNX turns to `pyannote31/` with `scripts/stage1f_compare_turns.py`. Do not re-run pyannote 3.1. Do not read `eval/`.
