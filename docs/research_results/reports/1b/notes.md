# Наблюдения Stage 1b

### Возобновление и gate HF

- Все артефакты Stage 1a сохранены. `faster-whisper medium` использован только как исторический baseline и не засчитан как успех Stage 1b.
- До установок и ASR подтверждено наличие `HF_TOKEN` или `HUGGING_FACE_HUB_TOKEN`; значение не читалось и не выводилось.
- Аутентифицированные HTTP GET с редиректами дали 200 для `pyannote/speaker-diarization-3.1/config.yaml`, `pyannote/segmentation-3.0/config.yaml`, `pyannote/speaker-diarization-community-1/README.md` и `Systran/faster-whisper-large-v3/config.json`.
- Санитизированное доказательство: `results/asr/hf_access_preflight.json`. В нём только коды, хосты и `token_present=true`; заголовков Authorization и токена нет.

### Среда и установки

- Хост: 4 логических CPU, 15 GiB RAM, без swap и GPU; свободного диска перед моделями — 238 GiB.
- Python 3.12.3, ffmpeg 6.1.1.
- Установки с первой попытки: `whisperx==3.8.6`, `pyannote-audio==4.0.7`, `faster-whisper==1.2.1`, `torch==2.8.0`, `llama-cpp-python==0.3.35`, `DeepFilterNet==0.5.6`, `pyrnnoise==0.4.3`, `audiolab==0.5.2`.
- Локально загружен официальный `Qwen/Qwen3-8B-GGUF`, файл `Qwen3-8B-Q5_K_M.gguf` (5,85 GB). Модель и WAV-файлы находятся в игнорируемых каталогах и не добавляются в git.
- `DeepFilterNet` требует старые `numpy<2` и `packaging<24`, а текущий WhisperX требует `numpy>=2.1`. Для denoise зависимости временно понижались, после обработки восстановлены `numpy==2.5.2` и `packaging==26.3`. WhisperX импортируется; `pip check` ожидаемо продолжает показывать только конфликт неактивного DeepFilterNet.

### Loudnorm

- Выполнен ровно один проход: `loudnorm=I=-16:TP=-1.5:LRA=11`.
- Выход: `data/processed/meeting_sample_loudnorm.wav`, mono PCM s16le, 16 кГц, 1468,66 с.
- Компрессор, `afftdn`, highpass и другие ffmpeg-фильтры не применялись.

### WhisperX large-v3 + pyannote

- Конфигурация: `large-v3`, CPU `int8`, 4 потока, batch 4, язык `ru`, WhisperX alignment, `pyannote/speaker-diarization-community-1`.
- Результат: 143 сегмента, 1486 выровненных слов, 4 спикера и 9 сегментов без метки. Время всего прогона около 1204 с.
- Артефакты: `results/asr/whisperx_large_v3_loudnorm/meeting_sample_loudnorm.{json,txt}`.
- Технически ASR и diarization завершились без crash/OOM, поэтому fallback на отдельный faster-whisper + pyannote и whisper.cpp не запускался.

### Проверка смысла Qwen3-8B

- Использован локальный `Qwen3-8B-Q5_K_M.gguf` через llama.cpp, seed 20260829.
- Выбрано по 3 случайных фрагмента для каждого из 4 спикеров, всего 12.
- Первый результат: 2 связных и 10 несвязных; общий вердикт `incoherent`. Время 165,905 с.
- Текст содержит случайные английские, корейские и другие вставки, технически невозможные сочетания и обрывки. Словарный `rw_ratio` не вычислялся и не использовался как pass.
- Артефакт: `results/asr/qwen3_8b_meaning_check.json`.

### RMS исходных фрагментов до loudnorm

- Для тех же 12 таймкодов из первого Qwen-теста исходный M4A декодирован в mono float PCM 16 кГц. Посчитан RMS dBFS по всему интервалу без noise/silence gating.
- Средний RMS по трём фрагментам: `SPEAKER_00 = -29,411 dBFS`, `SPEAKER_01 = -27,789 dBFS`, `SPEAKER_02 = -30,143 dBFS`, `SPEAKER_03 = -42,001 dBFS`.
- `SPEAKER_03` действительно на 11,9–14,2 dB тише остальных и имеет 0/3 связных фрагментов. Для него гипотеза о проблеме тихой речи выглядит правдоподобно.
- Но самый громкий `SPEAKER_01` также имеет 0/3 связных фрагментов, а единственный лучше распознанный `SPEAKER_00` (2/3) тише `SPEAKER_01`. Поэтому одна громкость не объясняет общий провал.
- Средний RMS двух связных фрагментов: `-30,127 dBFS`; десяти несвязных: `-32,778 dBFS`, разница `+2,651 dB`. Point-biserial correlation на уровне фрагментов — только `0,167`; корреляция среднего RMS спикера с долей связных — `0,299`.
- Вывод: гипотеза подтверждается частично только для очень тихого `SPEAKER_03`, но общая связь слабая. Нужно отдельно измерять SNR/noise floor, реверберацию и перекрытия речи. Выборка мала: 12 фрагментов, только 2 положительных, оба одного спикера.
- Артефакт: `results/asr/sampled_fragment_rms.json`.

### DeepFilterNet3

- После плохой проверки смысла выполнен default-проход DeepFilterNet3 на loudnorm WAV. Время denoise — 29,16 с.
- Повторный WhisperX с той же конфигурацией дал 112 сегментов, 975 выровненных слов и 4 спикера.
- Qwen3-8B на 12 новых случайных фрагментах дал 0 связных и 12 несвязных, общий вердикт `incoherent`; время 184,546 с.
- Покрытие речи явно упало (1486 → 975 слов), поэтому по стоп-правилу библиотеки параметрические пресеты и speaker-only pass не запускались.
- Артефакты: `results/asr/whisperx_large_v3_deepfilter_default/meeting_sample_loudnorm_DeepFilterNet3.{json,txt}`, `results/asr/qwen3_8b_deepfilter_default_meaning_check.json`, `results/denoise/deepfilternet_default.log`.

### RNNoise

- `pyrnnoise==0.4.3` проверен в default-конфигурации.
- Начальный CLI-вызов упал: `audiolab.Info` больше не имеет поля `rate`.
- Первый повтор через совместимый wrapper дошёл до `Reader.rate` и упал на таком же переименовании.
- Второй и последний повтор с alias `Reader.rate → sample_rate` упал глубже: текущий `audiolab.Graph` не принимает устаревший аргумент `rate`.
- Начальная попытка плюс два повтора исчерпаны. WAV не создан, ASR не повторялся. Вторую библиотеку и всё закрытое denoise-дерево остановлено.

### Итог Stage 1b

- Критерий успеха не достигнут: диаризация на 4 спикера технически работает, но Qwen3-8B отверг смысл большинства фрагментов.
- DeepFilterNet3 ухудшил и смысл, и покрытие. RNNoise не запустился из-за несовместимости версий.
- Чанкинг и саммари не запускались. Gemini/NVIDIA в Stage 1b не вызывались; аудио не передавалось API.
- Закрытое дерево исчерпано. Нужен отдельный человеческий выбор: совместимая сборка RNNoise либо работа с качеством источника. Текущий стек нельзя рекомендовать для MVP.

