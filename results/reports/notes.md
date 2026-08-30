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
| [`2b/`](2b/conclusions.md) | этап 2b **закрыт**: рабочие C (14) и D (12); победителя нет |
| [`3/`](3/notes.md) | этап 3: P1/P2 на D, P1 на C; победитель промпта P1 |

Канонические JSON: `results/reports/1a/` … `1e/`, `2/`. Прогон 2b: ветка `cursor/stage2b-four-hypotheses-4305`.
План: [`docs/research_plan.md`](../../docs/research_plan.md), итог 2b: [`2b/conclusions.md`](2b/conclusions.md), промпт 3: [`docs/prompts/stage3_llm.md`](../../docs/prompts/stage3_llm.md).
ASR-дампы: `results/asr/1a|1b|1c|1d|1e/` (gitignored).  
Eval-клипы: [`docs/eval_clips.md`](../../docs/eval_clips.md).
