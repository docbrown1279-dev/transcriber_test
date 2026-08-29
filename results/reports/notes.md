# Notes — Stage 1 (Researcher)

Дата прогона: 2026-08-28. Хост: 4× CPU Xeon, 16 GB RAM, без GPU, без swap. Фикстура: `data/fixtures/meeting_sample.m4a` (~24.5 мин, AAC mono → `data/processed/meeting_sample_16k.wav`).

## Окружение и зависимости

Установлено в `.venv` (после явного green light):

- `faster-whisper==1.2.1`, `pymorphy3==2.0.6`, `pymorphy3-dicts-ru`
- `huggingface_hub`, `sentence-transformers==6.0.0`
- `deepfilternet==0.5.6` (без torch — неработоспособен)
- `google-generativeai==0.8.6` (API fallback)

Системное уже было: `ffmpeg`, `cmake`, `build-essential`.

Секреты (наличие, без значений): `hugging_face` (смаплен в `HF_TOKEN`), `GEMINI_API_KEY`, `NVIDIA_API_KEY`. NVIDIA API недоступен по сети (SSL EOF на `integrate.api.nvidia.com`).

## Критический блокер: egress

Cloud egress **не** включает Hugging Face / OpenAI Whisper CDN / PyTorch wheels host:

| Хост | Результат |
|---|---|
| `huggingface.co` | SSL EOF / connect fail |
| `openaipublic.azureedge.net` | SSL fail |
| `download.pytorch.org` | fail |
| `pypi.org` / `*.googleapis.com` / `github.com` | OK |

Запрошен allowlist для `huggingface.co` через environment setup actions. Без этого **локальный Whisper-стек в этой VM не запускается**.

## ASR

1. `faster-whisper medium` — FAIL (Hub)
2. `faster-whisper large-v3` — FAIL (Hub)
3. Альтернатива Azure `.pt` — FAIL (CDN)
4. Fallback: `gemini-3.5-transcribe` по чанкам 480 с — **SUCCESS**
   - `rw_ratio=0.9397` (≥0.9)
   - human-like sample_check=`ok` (3 фрагмента)
   - OOV≈12 (морфология pymorphy3)
   - артефакты: `results/asr/gemini_transcribe.{json,txt}`, `..._quality.json`
   - ~159 с wall time на весь файл

Лимит 3 попытки на семейство faster-whisper исчерпан сетевыми фейлами, не качеством модели.

## Denoise (отдельный A/B)

Синтетический шум: pink noise + mix на 180 с excerpt.

| Условие | chars | token_recall к clean | вывод |
|---|---:|---:|---|
| clean | 2639 | 1.0 | база |
| noisy | 2112 | 0.472 | деградация |
| ffmpeg afftdn+HP | 1373 | 0.391 | **хуже** noisy |
| ffmpeg anlmdn+HP | 2131 | 0.489 | чуть лучше noisy |

Рекомендация: **не** использовать агрессивный `afftdn`; мягкий `anlmdn` — опционально. DeepFilterNet/RNNoise — skipped (нет torch/весов).

ASR для A/B — тот же Gemini (локальный Whisper недоступен); сравнение относительно clean-текста excerpt.

## Chunking

- Локальный E5-small — FAIL (HF).
- Gemini `text` embeddings `gemini-embedding-001`:
  - thr=0.7 → 0 разрывов (mean_sim≈0.911)
  - thr=0.88 (≈ mean−σ) → **20 чанков**, spot-check границ ок
- Вывод: для «гладких» эмбеддингов Gemini фиксированный 0.7 из плана слишком низкий; лучше адаптивный порог.

## LLM summary

- Ollama/Qwen локально — нет runtime/весов.
- Gemini 2.5 Flash — SUCCESS (~29 с), осмысленный протокол (саммари / решения / действия / вопросы), `hallucination_flag=false`.
- API-вызовы зафиксированы по назначению (ASR чанки, embeddings, 1 summary). Ключи не логировались.

## API usage log (без секретов)

| Provider | Model | Purpose | Approx |
|---|---|---|---|
| Gemini | gemini-3.5-transcribe | full meeting ASR | ~4 чанка × ~160 с total |
| Gemini | gemini-3.5-transcribe | denoise A/B ×4 excerpt | ~120 с total |
| Gemini | gemini-embedding-001 | semantic chunking | 2 прогона (~25–28 с) |
| Gemini | gemini-2.5-flash | meeting summary | 1 вызов ~29 с |
| NVIDIA | — | — | недоступен (egress) |

## Скрипты

- `scripts/env.sh` — venv + map `hugging_face`→`HF_TOKEN`
- `scripts/asr_transcribe.py` — faster-whisper
- `scripts/asr_quality.py` — rw_ratio / OOV / sample check
- `scripts/asr_gemini_fallback.py` — API ASR
- `scripts/denoise_prepare.sh` — noisy + ffmpeg denoise
- `scripts/semantic_chunking.py` — cosine breaks
- `scripts/llm_summary.py` — Ollama try → Gemini summary

## Следующий шаг для «настоящего» локального Stage 1

1. Добавить egress: `huggingface.co`, `*.huggingface.co`, `cdn-lfs.huggingface.co`, `hf.co`, `cas-bridge.xethub.hf.co` (+ опционально `openaipublic.azureedge.net`, `download.pytorch.org`, Ollama registry).
2. Повторить ASR на `faster-whisper medium` int8 CPU на той же фикстуре.
3. Сравнить WER/качество Gemini vs Whisper на одних фрагментах.
4. Подтянуть Qwen2.5-7B GGUF и закрыть LLM-блок локально.


## Reprobe Hugging Face allowlist (2026-08-29)

Пользователь сообщил, что HF добавлен в allowlist. Повторная проверка **в этом же поде**:

| Проверка | Результат |
|---|---|
| DNS `huggingface.co` | OK (IPv4 CloudFront) |
| DNS `cdn-lfs.huggingface.co` | **FAIL** (no address) |
| HTTP anon `api/models/.../faster-whisper-medium` | **NETWORK_TLS** SSL EOF |
| HTTP с токеном (тот же URL) | **NETWORK_TLS** SSL EOF (идентично) |
| `environment-info` egress list | **`huggingface.co` отсутствует** |

**Вывод:** это не проблема `HF_TOKEN`. Публичные репозитории Whisper недоступны из‑за сетевого TLS/egress. На этом ретрае Gemini ASR **не** вызывался.

Нужно: чтобы allowlist реально применился к агенту (часто нужен **новый** cloud agent / rebuild после изменения egress), плюс CDN: `cdn-lfs.huggingface.co` / `*.huggingface.co`.
