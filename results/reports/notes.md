# Отчёты

Разложены по подэтапам. Корневые `notes.md` / `research_report.json` больше не накапливают все стадии в одном файле.

| Папка | Что внутри |
|---|---|
| [`1a/`](1a/notes.md) | faster-whisper **medium**, ffmpeg afftdn, E5-чанкинг, саммари |
| [`1b/`](1b/notes.md) | WhisperX **large-v3** + pyannote, Qwen3-8B meaning check, RMS, denoise |
| [`1c/`](1c/notes.md) | изолированные клипы WhisperX / fw large / Qwen-Omni |
| [`1d/`](1d/notes.md) | GigaAM v2 RNNT + Podlodka-turbo, pyannote отдельно, retry `large-v3` по словарю |
| [`1e/`](1e/notes.md) | четыре ASR на eval-клипах, pyannote 3.1, бенч 25 с, WER/CER, гипотезы на каскад |
| [`2/`](2/notes.md) | полное совещание GigaAM v3, соседний чанкинг ≤3, Qwen не запускался (чанков 95/63/48) |

Канонические JSON: `results/reports/1a/` … `1e/`. Этап 2: `results/reports/2/` когда появится прогон.  
Рабочая ветка: `cursor/stage1e-four-asr-be20`. План: [`docs/research_plan.md`](../../docs/research_plan.md), промпт: [`docs/prompts/stage2_chunk_titles.md`](../../docs/prompts/stage2_chunk_titles.md).  
ASR-дампы: `results/asr/1a|1b|1c|1d|1e/` (gitignored).  
Eval-клипы: [`docs/eval_clips.md`](../../docs/eval_clips.md).
