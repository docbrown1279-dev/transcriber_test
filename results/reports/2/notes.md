# Этап 2 — полное совещание, соседний чанкинг, таймназвания

## Среда

- CPU: 4 vCPU, RAM: 15 GiB, GPU нет.
- Длительность `data/fixtures/meeting_sample.m4a`: 1468,662 с (PCM 44,1 кГц mono после декода).
- Версии: `pyannote.audio 4.0.7`, `gigaam 0.2.0` (git `salute-developers/GigaAM`, на PyPI только 0.1.0), `torch 2.13.0+cpu`, `torchaudio 2.11.0+cpu`, `sentence-transformers 6.0.0`, `transformers 5.16.1`.
- `gigaam==0.2.0` с PyPI не существует (попытка 1). Попытка 2: установка из git — успешно.
- `torchcodec` в этом venv не грузится (`libnvrtc.so.13` / `libtorchcodec_image.so`). Исходный m4a для pyannote декодирован ffmpeg в PCM в памяти: без loudnorm, gain, denoise, VAD.
- Секреты не печатались. Gemini/NVIDIA не вызывались. Аудио в API не отправлялось.

## HF gate

Токен присутствовал. GET:

- `pyannote/speaker-diarization-3.1` `config.yaml` → HTTP 200
- `pyannote/segmentation-3.0` `config.yaml` → HTTP 200

Доказательство: `results/asr/2/hf_gate.json`.

## ASR

Диаризация `pyannote/speaker-diarization-3.1` на исходном файле: 769,26 с, 368 raw turns, 4 спикера.

Merge в таблице: тот же спикер, gap ≤ 0,3 с → `[min, max]`; turn &lt; 1 с поглощён соседом. Итого 177 строк.

Последняя raw-строка вылезала за конец файла (pyannote edge padding, как в 1d). Концы обрезаны до 1468,662 с. Дыры ≥ 0,5 с не извлекались (99 интервалов, включая старт `[0, 9.970)`).

Extract: `ffmpeg -ss START -to END` из оригинала, 16 кГц mono PCM. При расхождении длительности — точный seek, затем только pad/trim округления ffmpeg. Linear `volume=` если RMS &lt; −30 dBFS к −23, cap +18 dB, peak ≤ −1 dBFS. 138 строк с gain, 39 без. Без loudnorm, компрессора, denoise и склейки extract.

GigaAM **`v3_rnnt` только**, CPU, `fp16_encoder=False`. Строки &gt; 25 с резались по оси времени (5 таких, максимум 52,9 с). Пустой выход оставлен `""` (4 сегмента). 183 сегмента гипотезы (177 строк + 6 кусков после 25 с). Wall 160,91 с, попытка 1, без retry. Латиницы в токенах длины ≥ 3 нет. Кириллических токенов 2591.

Артефакты: `results/asr/2/gigaam_v3_rnnt/meeting_sample.json` + `.txt`. Полный текст в notes не копируется.

Выборочно: начало про канализацию/экспертизу; середина про отсутствие желания и изучение работ; конец — прощание. Связная русская речь совещания, не бред.

## Чанкинг

Эмбеддер только `cointegrated/rubert-tiny2` (одна установка). Единица = целые реплики одного спикера; внутри реплики резали только если &gt; ~80 слов. Merge только соседей; новый чанк при gap &gt; 90 с. В эмбеддинг — только текст.

| Попытка | unit_size (слова) | threshold | num_chunks | embed_runtime_sec | cosine accepted min / med / max | n_accepted |
|---|---|---:|---:|---:|---|---:|
| 1 | 20–50 | 0,80 | 95 | 0,267 | 0,811 / 0,833 / 0,939 | 6 |
| 2 | 40–80 | 0,70 | 63 | 0,297 | 0,708 / 0,754 / 0,939 | 24 |
| 3 | 60–120 | 0,65 | 48 | 0,337 | 0,654 / 0,755 / 0,939 | 31 |

Ни одна попытка не попала в 5–30. Четвёртую схему не запускали. Qwen не запускали.

Много коротких единиц (от 2 слов): соседние реплики часто разных спикеров, их нельзя склеить на этапе packing. Порог 0,80 почти не склеивает соседей (6 принятых merge). Даже 0,65 оставляет 48 чанков.

`chunks.json` — попытка 3 как ближайшая к диапазону, **без** `title`. Логи: `results/chunking/2/attempt_{1,2,3}.json`, `_summary.json`.

## Таймназвания

Пропущены: нет попытки с 5–30 чанками. `results/llm/2/titles.json` не создавался.

## Вне скоупа (не делалось)

Denoise, Whisper, Podlodka, WhisperX, GigaAM CTC/e2e/v2, дыры, eval gold, Gemini, NVIDIA, саммари встречи, четвёртая схема чанкинга.
