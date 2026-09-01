# Local smoke — Qwen3-8B Q5_K_M

- model: `Qwen3-8B-Q5_K_M.gguf` (`Qwen/Qwen3-8B-GGUF`), llama-cpp-python 0.3.35, 4 threads, CPU. Install: 1 попытка.
- extract D00 (`n_ctx=8192`): parse_ok=true, wall load+extract ≈ 204 с, 7 пунктов. Assemble на 8192 упал: prompt+max_tokens=9720.
- assemble Gemini `insights_d` (`n_ctx=16384`, не локальный D00): parse_ok=true, 1455 с, peak RSS 13186 MiB. Секции Кратко/Решения/Дальше/Открыто/По времени есть; `### D00`…`D07` (8/12, обрезано по max_tokens).
- `insights_d/` и `report.md` не менялись (sha256 как до прогона). NVIDIA/Gemini не вызывались.

## D00 vs Gemini

- Локальный title: «Подключение к сетям» (7 пунктов, все `fact`).
- Gemini title: «Канализация, ливневка, проект» (10 пунктов: action/fact/question).
- У 8B нет kind `action` и `question`; паркинг и ливнёвка есть, УДС превращён в утверждение.
- Цель дыма — разбор markdown, не качество. 14B не запускался.
