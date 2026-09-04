# Итог этапов 1f и 1f2

Этапы закрыты. Полный файл этапа 2 не пересчитывать. Дальше — словарь после ASR, не новый bakeoff VAD/эмбеддеров.

Прогоны: ветки `cursor/stage1f-onnx-diarization`, `cursor/stage1f2-vad-embed`, `cursor/stage1f2-gigaam`. Таблицы: [`notes.md`](notes.md), текст TEN/FSMN: [`asr_notes.md`](asr_notes.md).

## Стек демки (2 vCPU / 8 ГиБ)

- **Речь:** Silero VAD ONNX как основной. **TEN-VAD только в дырах Silero** (хвост `test_voice` 75–83 с pyannote и Silero почти молчат; TEN дал связный кусок про техусловия / проектирование). Не замена Silero на TEN целиком.
- **Спикеры:** WeSpeaker ResNet34-LM ONNX (~25 МБ, ~285 МиБ RSS). Самый лёгкий из трёх. На 4 eval-клипах WeSpeaker / ERes2Net-base / TitaNet-small дали **один и тот же** счётчик **2 / 3 / 2 / 2** и DER одного порядка (0,276 / 0,264 / 0,271). Два других **можно** подставить вместо WeSpeaker — на этой выборке разницы нет; в демке не тащим.
- **ASR:** GigaAM `v3_rnnt` (нужен CPU-torch, это движок модели, не pyannote). Linear `volume=` если RMS < −30 dBFS.
- **FSMN:** не в стеке. Хвост ловит слабее TEN, RAM больше.
- **sherpa full / pyannote 3.1:** не для демки. 3.1 остаётся эталоном меток 1e и разметкой полного файла этапа 2.

TEN: Apache-2.0 **с Agora non-compete** — нельзя Deploy как конкурент offerings Agora. Для внутренней демки прогон ок; в продукт — смотреть лицензию.

Пороги VAD в 1f2 не крутили (TEN `threshold=0.5`). Имеет смысл только постобработка как у Silero (`min_speech` ~200 мс), чтобы отрезать крошки вроде «такой» / «поколение».

## Что смотрели

| Слой | Кто | Зачем |
|---|---|---|
| VAD | Silero, TEN, FSMN | дыры vs pyannote, не max IoU |
| эмбеддер | WeSpeaker, ERes2Net-base, TitaNet-small | одни Silero-куски, кластер 1f без re-tune |
| ASR на масках | GigaAM на TEN и FSMN | слова в 0–10 с и 75–83 с `test_voice` |

Silero выигрывает старт 0–10 с (~8,4 с речи vs 0,03 с у pyannote). TEN выигрывает хвост 75–83 с (~5,9 с vs 0,09 с у Silero). Скорость трёх VAD один порядок (0,8–1,6 с / 4 клипа). Узкое место — GigaAM (~30 с), не VAD.

## Не делаем

Не пересчитывать `results/asr/2/`. Не подставлять ECAPA. Не гонять sherpa как fallback на весь файл. Не объявлять C или D единственным TOC.
