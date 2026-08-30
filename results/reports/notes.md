# Отчёты

Разложены по подэтапам. Корневые `notes.md` / `research_report.json` больше не накапливают все стадии в одном файле.

| Папка | Что внутри |
|---|---|
| [`1a/`](1a/notes.md) | faster-whisper **medium**, ffmpeg afftdn, E5-чанкинг, саммари |
| [`1b/`](1b/notes.md) | WhisperX **large-v3** + pyannote, Qwen3-8B meaning check, RMS, denoise |
| [`1c/`](1c/notes.md) | изолированные клипы WhisperX / fw large / Qwen-Omni |
| [`1d/`](1d/notes.md) | GigaAM v2 RNNT + Podlodka-turbo, pyannote отдельно, retry `large-v3` по словарю |
| [`1e/`](1e/notes.md) | четыре ASR на eval-клипах, pyannote 3.1, бенч 25 с, WER/CER, гипотезы на каскад |
| [`2/`](2/notes.md) | этап 2: полное совещание, tiny2, заголовки Qwen, оглавление |
| [`2b/`](2b/notes.md) | этап 2b: A 62 / B 43 / C 14 / D skipped (einops); победителя нет |

Канонические JSON: `results/reports/1a/` … `1e/`, `2/`. Этап 2b: `results/reports/2b/` когда появится прогон.
Рабочая ветка: `cursor/stage1e-four-asr-be20`. План: [`docs/research_plan.md`](../../docs/research_plan.md), промпт 2b: [`docs/prompts/stage2b_chunking.md`](../../docs/prompts/stage2b_chunking.md).
ASR-дампы: `results/asr/1a|1b|1c|1d|1e/` (gitignored).  
Eval-клипы: [`docs/eval_clips.md`](../../docs/eval_clips.md).
