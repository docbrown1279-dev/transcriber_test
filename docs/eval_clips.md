# Eval-клипы (~1–1.5 мин)

Четыре куска одной записи (`data/fixtures/meeting_sample.m4a` = `docs/Голос 002.m4a`). Один уже был (`test_voice`); три новых вырезаны в том же стиле: AAC 44.1 kHz mono.

Каталог для агентов (без текста): [`eval_example/clips.json`](../eval_example/clips.json).  
Черновики реплик (локально, не в git): `eval/test_*.json`. Облачным агентам папку `eval/` не отдавать.

| Клип | Файл | На полной записи | Зачем |
|---|---|---|---|
| `test_voice` | `data/test_voice.m4a` | 00:00–01:23 | Уже gold. A громкий / B тихий. pyannote 1d начинает речь только с ~11 с. |
| `test_apartments` | `data/test_apartments.m4a` | 09:30–10:55 | Квартиры (WhisperX → English) + «ретранслятор» вместо staff-цикла. |
| `test_transformers` | `data/test_transformers.m4a` | 14:35–16:00 | 9-й/8-й корпус, трансформаторы; WhisperX chopsticks. |
| `test_ninth` | `data/test_ninth.m4a` | 20:45–22:10 | Четвёртый спикер (D) про выдачу 9-го корпуса. |

Нарезка:

```bash
ffmpeg -i "docs/Голос 002.m4a" -ss 570 -t 85 -ac 1 -ar 44100 -c:a aac -b:a 64k data/test_apartments.m4a
ffmpeg -i "docs/Голос 002.m4a" -ss 875 -t 85 -ac 1 -ar 44100 -c:a aac -b:a 64k data/test_transformers.m4a
ffmpeg -i "docs/Голос 002.m4a" -ss 1245 -t 85 -ac 1 -ar 44100 -c:a aac -b:a 64k data/test_ninth.m4a
```

## Стабильные метки (не id моделей)

| Gold | Кто | WhisperX 1b | pyannote 1d |
|---|---|---|---|
| A | громче (~−25 dBFS) | SPEAKER_01 | SPEAKER_04 |
| B | тихий основной | SPEAKER_03 | SPEAKER_01 |
| C | квартиры / мощность | SPEAKER_02 | SPEAKER_02 |
| D | 9-й корпус | SPEAKER_00 | SPEAKER_00 |

Пятый id у pyannote 1d (`SPEAKER_03`, ~7 с крошек) — не «неразмеченное WhisperX». Неразмеченные 9 сегментов WhisperX (~29 с) часто лежат в **дырах** pyannote (например ~04:48–05:20), а не в отдельном спикере. Диаризацию 1d делал **pyannote 3.1 до ASR**; Podlodka/GigaAM только писали текст на уже нарезанные turns.

## Черновик текста

Склеен из medium, GigaAM v2 (до retry), Podlodka-turbo (до retry) и изолированного 1c `large-v3`. Поля `uncertain` / `text_source` в JSON — где модели разошлись. Послушать и поправить `text`/`speaker`/`start`/`end`; потом `status: human_gold`.

Retry `large-v3` из 1d **не** подмешивался: на коротких срезах он писал «Субтитры сделал DimaTorzok».

## Следующий аудио-прогон — 1f (облако)

Ветка: `cursor/stage1f-onnx-diarization`. Промпт: [`docs/prompts/stage1f_diarization.md`](prompts/stage1f_diarization.md). Те же 4 файла. Эталон меток (в git): [`results/reports/1f/baseline/pyannote31/`](../results/reports/1f/baseline/pyannote31/). Сначала сравнение turns скриптом, потом GigaAM v3 на новых стыках.

1e закрыт: [`docs/prompts/stage1e_eval_clips.md`](prompts/stage1e_eval_clips.md).

GigaAM v2 на полном файле: **81 с на 415 срезах** (~24.5 мин аудио, RTF ≈ 0.055) — только ASR, без 13 мин pyannote. На коротких клипах это правдоподобно и для v3.
