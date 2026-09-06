# Тикет: D4 — гейт формата на загрузке + покрытие контейнеров

**Статус:** OPEN (backlog)  
**Приоритет:** не блокирует текущее демо. Сейчас txt отсекается ffprobe на POST `/jobs`; риск — контейнер, который probe «проглатывает», а падает уже на normalize/ASR.

---

## Контекст

Python stdlib **не декодирует mp3**. Рабочий путь — `ffmpeg`/`ffprobe`.

Уже сделано в D4:

- sniff `format_name`, не писать `.bin`;
- probe/trim не роняют процесс 500; во фронт — общая ошибка, детали в логе;
- txt / мусор без медиа: ffprobe падает сразу на загрузке.

Не сделано: **явный ingest-gate** «есть ли вообще аудиотрек», до `queue.submit`. Иначе теоретически можно полчаса крутить ASR и упасть на битом/беззвучном контейнере.

---

## Цель

На `POST /jobs`, **до постановки в очередь** (секунды, не минуты):

1. Файл — медиа с **хотя бы одним audio stream**.
2. Кодек из белого списка (mp3/aac/pcm/flac/opus/vorbis/…).
3. `duration > 0`.
4. Опционально: декод **первых 1–2 с** (`ffmpeg -t 2 -f null -`), без полного транскода.
5. Отказ сразу, задача не создаётся / каталог снимается. В лог — format/codec/ffprobe. Во фронт — коротко: «Не удалось прочитать аудиофайл.» (не traceback).

Не декодировать весь файл. Не ждать ASR.

---

## Как реализовать (когда откроем)

Один хелпер, например `transcriber.audio.ingest_gate.accept(path) -> GateResult`.

```text
ffprobe -v error -show_streams -select_streams a -of json FILE
```

- нет streams → reject  
- `codec_type != audio` / пустой `codec_name` → reject  
- `codec_name` не в allowlist → reject (тикет на расширение списка)  
- `duration` отсутствует или `<= 0` → reject  

Дополнительно (если probe ок, но хотим поймать битый payload):

```text
ffmpeg -v error -t 2 -i FILE -f null -
```

exit ≠ 0 или stderr про decode → reject.

Magic-bytes (ID3, `ftyp`, `RIFF`, `OggS`) — дешёвый pre-check, **не** замена probe: расширение врёт.

Тесты: mp3/m4a/wav ok; txt/json/пустой/без audio stream → reject без воркера.

---

## Когда открывать

Отдельный прогон:

- матрица контейнеров (mp3, ogg, flac, aac, webm, wav, m4a);
- файл без расширения;
- txt и контейнер без аудиотрека;
- битый заголовок.

Не тащить декодер mp3 в Python, пока ffmpeg справляется.
