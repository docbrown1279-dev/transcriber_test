# Структура конфигов + вынос порогов (черновик на утверждение)

**Статус:** APPROVED — коммит планов, ветка `cursor/d1-silero-tune`, тюнер Silero.  
**Связано:** [`draft_d1_speech_recovery.md`](draft_d1_speech_recovery.md), контракт [`config_profiles.md`](../contracts/config_profiles.md), ТЗ [`docs/dev_specs.md`](../../docs/dev_specs.md) §1–§5.

---

## 1. Принципы

1. **Нет магических порогов в `src/`** — любое число, которое влияет на качество/поведение, читается из конфига (уже правило контракта; Silero сейчас нарушает).
2. **Профиль** (`demo` / `dev` / `prod`) — оверлей поверх общего base, не три полные копии.
3. **Частота правок:** то, что крутят часто (LLM, пороги VAD), — отдельные файлы/секции; runtime-лимиты не смешивать с ML.
4. **Секреты** только имена env (`api_key_env`), не значения.
5. **Константы движка модели** (не тюнятся) можно оставить в коде с комментарием — см. §4.
6. **Merge при загрузке**, не «сгенерировать три толстых yaml и коммитить их» — иначе base и копии разъедутся.

---

## 1b. Как делают в проде (и что не путать с uv)

**uv** — менеджер пакетов/venv. Библиотек «управления app-конфигами» у него нет. У нас в зависимостях уже есть нужный стек: **PyYAML + Pydantic (+ `pydantic-settings`)**.

Типичные прод-паттерны:

| Паттерн | Суть | Когда |
|---|---|---|
| **Base + profile overlay** | `base.yaml` ← deep-merge `profiles/demo.yaml` | Наш случай: 90% ключей общие, отличаются engines/limits/UI/LLM |
| **Env overrides** | `ASR__DEVICE=cuda` / `APP_PROFILE=demo` поверх yaml | Деплой, секреты, одноразовый тюнинг без правки файла |
| **Compose (Hydra/OmegaConf)** | Много маленьких конфигов + CLI overrides | Тяжелые ML-эксперименты; для демо-сервиса часто overkill |
| **Dynaconf** | YAML+env+vault в одной либе | Ок, но новая зависимость; при pydantic уже избыточно |
| **Скрипт «сшить в один файл»** | CI пишет `demo.generated.yaml` | Только как **debug dump**; source of truth — слои |

Рекомендация для проекта: **layered YAML + deep-merge в `load_config` + финальная валидация `AppConfig`**. Опционально позже: `pydantic-settings` для env-override поверх merge. Отдельный скрипт `scripts/render_config.py` — печатает итоговый yaml для человека (не коммитить результат как основной конфиг).

---

## 2. Как часто меняется (по назначению)

| Домен | Примеры ключей | Как часто | Комментарий |
|---|---|---|---|
| **Speech / ASR-цепь** | VAD thresholds, gain, merge gaps, cluster threshold, `max_segment_seconds`, `device` cpu/cuda | **часто на D1** (сейчас), потом редко | Качество «кто говорил / что сказали» |
| **Чанкинг** | `similarity_threshold`, `packing_max_gap_sec`, цели длины глав | **часто на D2**, потом средне | Не трогать при тюне VAD |
| **Сеть / лимиты / UI** | `requests_per_ip_per_day`, TTL, `max_concurrent_jobs`, UI flags | **редко** | Продуктовые/хостовые ограничения |
| **LLM** | model, temperature, prompts, max_calls, timeout | **очень часто на D3+** | Отдельный файл пресетов |
| **App / железо** | `storage_root`, `onnx_threads`, sample_rate | **редко** | Раз на деплой |

### Инвентарь на сейчас (leaf-ключи в yaml)

По `config/demo.yaml` + 3 новых VAD. «Speech = 36» — это **сумма уже разных секций**, не один плоский список:

| Секция сейчас | N | Комментарий |
|---|---:|---|
| `audio` | 8 | из них 2 — лимиты файла (скорее runtime) |
| `vad` | 6 (после выноса) | ок |
| `diarization` | 11 | на грани; лучше вложенность |
| `asr` | 4 | ок |
| `correction` | 7 | ок |
| **сумма** | **~36** | |

**Цель: 10–15 на читаемый блок** — не дробить файлы, а **вложить** и чуть переложить лимиты.

#### Предлагаемая нарезка speech (логические блоки)

```yaml
# --- input / loudness (≤10) ---
audio:
  sample_rate: 16000
  channels: 1
  gain:                         # было 4 плоских gain_*
    rms_threshold_dbfs: -30.0
    target_dbfs: -23.0
    max_db: 18.0
    peak_ceiling_dbfs: -1.0
# max_minutes / max_file_size_mb → в limits (runtime), не speech

# --- vad (≤10) ---
vad:
  engine: silero
  threshold: 0.5
  neg_threshold: 0.35
  min_speech_ms: 200
  min_silence_ms: 200
  fallback: disabled            # disabled | ten_fallback | fsmn_fallback

# --- diarization: двигатель (≤5) ---
diarization:
  engine: wespeaker_onnx
  device: cpu                   # cpu | cuda
  onnx_threads: 2
  merge:                        # склейка реплик (≤5)
    same_speaker_gap_sec: 0.3
    absorb_turn_shorter_than_sec: 1.0
    min_hole_sec: 0.5
    vad_premerge_gap_sec: 0.3
  embed:                        # окна эмбеддинга + кластер (≤5)
    min_sec: 0.4
    window_sec: 1.5
    step_sec: 0.75
    cluster_distance_threshold: 0.80

# --- asr (≤5) ---
asr:
  engine: gigaam_v3_rnnt
  device: cpu
  max_segment_seconds: 25
  subprocess: true

# --- correction (≤10) ---
correction:
  enabled: true
  mode: suggest_only
  base_ru_dictionary: true
  domain_dictionary: false
  levenshtein_auto_replace: false
  manual_review: false
  min_confidence: 0.6
```

Итого по блокам после нарезки:

| Блок | ≈N | Влезает в 10–15? |
|---|---:|---|
| `audio` (+ nested `gain`) | 6 | да |
| `vad` | 6 | да |
| `diarization` (engine) | 3 | да |
| `diarization.merge` | 4 | да |
| `diarization.embed` | 4 | да |
| `asr` | 4 | да |
| `correction` | 7 | да |
| `limits` (+ бывшие max_minutes/size) | runtime | не speech |

Schema: вложенные модели Pydantic (`GainConfig`, `DiarizationMergeConfig`, `DiarizationEmbedConfig`) — или плоские ключи с точками в yaml через вложенные dict. Обратная совместимость на один релиз не обязательна (демо ещё не в проде): лучше сразу чистая вложенность.

CPU|GPU: только `asr.device` / `diarization.device` (+ позже `llm` threads) — не отдельный раздел.

**Вывод по файлам (без лишней нарезки base):**

```text
config/base.yaml                 # audio/vad/diarization/asr/correction + chunking + runtime defaults
config/profiles/{demo,dev,prod}.yaml
config/llm/{gemini,local_qwen}.yaml   # к D3
```

Дробить `base` на speech.yaml/chunking.yaml **не нужно** при ~60 ключах, если внутри yaml есть ясные подразделы.

---

## 3. Раскладка файлов (целевая)

Сейчас: три почти одинаковых монолита `config/{demo,dev,prod}.yaml` (дубли порогов gain/VAD/chunking).

### Рекомендуемая схема (сразу в ветке тюна — вместо трёх копий)

```text
config/
  base.yaml                 # общее: speech-пороги, chunking defaults, sample_rate, …
  profiles/
    demo.yaml               # только отличия demo
    dev.yaml                # только отличия dev
    prod.yaml               # только отличия prod
  # позже (D3), без ломки merge:
  # llm/
  #   gemini.yaml
  #   local_qwen.yaml
```

**Алгоритм `load_config(profile)`:**

1. Прочитать `config/base.yaml`.
2. Deep-merge `config/profiles/{profile}.yaml` (вложенные dict сливаются, скаляры/списки профиля побеждают).
3. Выставить/проверить `app.profile == profile`.
4. Опционально: env overrides (`pydantic-settings` или явный префикс) — секреты и one-off.
5. `AppConfig.model_validate(merged)` — как сейчас, `extra=forbid`.

Это и есть «скрипт, который берёт общий конфиг и дописывает куски режима» — только он живёт **в loader при старте**, а не генерирует три файла в git.

**Что в `base.yaml` (глобальное, редко отличается между профилями):**

- `audio.sample_rate`, `channels`, все `gain_*`
- `vad.threshold|neg_threshold|min_speech_ms|min_silence_ms` (+ дефолт `engine: silero`)
- `diarization` merge/embed пороги (gap, absorb, cluster, windows)
- `asr.max_segment_seconds`, `subprocess` (engine можно оставить в base = gigaam, device — в профиле)
- `chunking.*` исследовательские дефолты (similarity 0.70, packing gap, chapter targets)
- `correction.min_confidence` и флаги «базового» поведения, если одинаковы

**Что в `profiles/*.yaml` (отличается по ТЗ §5):**

| Ключ / зона | demo | dev | prod |
|---|---|---|---|
| `audio.max_minutes` / size | 15 / 250 | null | 120 / 2000 |
| `vad.fallback` | disabled | ten_fallback (позже fsmn) | disabled или fsmn |
| `diarization.engine` | wespeaker_onnx | pyannote31 / любой | pyannote или onnx |
| `diarization.device` / threads | cpu / 2 | гибко | по железу |
| `chunking.late_chunking` | off | можно on | optional |
| `llm.*` | gemini api | local_llama | local_llama |
| `limits.*` | жёсткие | null | умеренные |
| `ui.*` | jinja demo | api_only | interactive |
| `correction.domain_dictionary` / manual_review | false / false | … / true | true / true |
| `app.log_level` | INFO | DEBUG | INFO |

**LLM-файл отдельно** — к D3: `config/llm/gemini.yaml` подмешивается после profile *или* профиль только ссылает `llm: !include …` / ключ `llm_preset: gemini`. До D3 достаточно держать блок `llm:` внутри profile overlay (он и так почти весь разный).

### Фаза B (позже, по доменам внутри base)

Если `base.yaml` раздуется — разрезать на include-слои *до* профиля:

```text
config/
  base/
    speech.yaml
    chunking.yaml
    runtime_defaults.yaml   # только то, что реально общее
  profiles/…
```

Merge: `speech → chunking → runtime_defaults → profiles/{p}`. Не обязательно в первой итерации.

---

## 4. Полный список ключей

### 4.1 Уже в YAML (ок, не трогать смысл)

**runtime:** `app.*`, `limits.*`, `ui.*`  
**speech:** `audio.*` (вкл. gain), `vad.engine|min_speech_ms|fallback`, `diarization.*`, `asr.*`, `correction.*`  
**chunking:** все текущие  
**llm:** все текущие  

### 4.2 Добавить сейчас (hardcoded → config) — обязательный список ветки

| Ключ | Дефолт (как сейчас в коде) | Секция | Зачем |
|---|---|---|---|
| `vad.threshold` | `0.5` | speech | вход в речь Silero |
| `vad.neg_threshold` | `0.35` | speech | выход из речи |
| `vad.min_silence_ms` | `200` | speech | конец сегмента по тишине |
| `vad.fallback_engine` | зеркало/уточнение `fallback` | speech | опционально: оставить одно поле `fallback: disabled\|ten_fallback\|fsmn_fallback` |

`min_speech_ms` уже есть.

Опционально сразу (чтобы не возвращаться):

| Ключ | Дефолт | Зачем |
|---|---|---|
| `vad.min_hole_sec_for_fallback` | = `diarization.min_hole_sec` или `0.5` | когда звать fallback (когда появится) |
| `quality.ru_ratio_min` | `0.90` | G1 сейчас литерал в `quality/checks.py` |
| `quality.latin_chars_max` | `0` | G1 |
| `quality.hole_sec_warn` / `empty_segments_warn` | как в checks | warn-пороги отчёта |

Quality можно отложить до отдельного крошечного PR, если не хотите раздувать ветку тюна — **но Silero-три ключа обязательны**.

### 4.3 Не выносить в YAML (константы движка)

| Что | Почему |
|---|---|
| Silero ONNX `chunk_size=512` | требование модели / окна, не тюнится |
| HF repo id модели по умолчанию | можно позже `vad.model_path` если нужно офлайн-зеркало; не порог |
| Имена артефактов (`normalized.wav`) | контракт пайплайна, не конфиг качества |

### 4.4 Позже (не в этой ветке, но в списке «полный»)

| Когда | Ключи / файлы |
|---|---|
| D2 | late_chunking окна 240/60 если включат; пороги плотности warn |
| D3 | **`config/*/llm.yaml` + каталог промптов**; `max_tokens` / stop — когда появятся в коде |
| Fallback VAD | `fsmn_fallback` в реестре demo/prod; пороги TEN/FSMN в той же секции `vad` или `vad.fallback_params` |
| Gain per-turn | `asr.per_turn_gain: true` + те же `audio.gain_*` на extract |

---

## 5. Целевой фрагмент `vad` (после фикса)

```yaml
# --- speech ---
vad:
  engine: silero
  threshold: 0.5              # was hardcoded
  neg_threshold: 0.35         # was hardcoded
  min_speech_ms: 200
  min_silence_ms: 200         # was hardcoded
  fallback: disabled          # disabled | ten_fallback | fsmn_fallback (fsmn — коммерция)
```

Сетка тюна B0–B2 из recovery-плана = только эти четыре числа (+ regression).

---

## 6. Объём работ в ветке `cursor/d1-silero-tune`

1. **Config layers:** `config/base.yaml` + `config/profiles/{demo,dev,prod}.yaml`; deep-merge в `load_config`; удалить/заменить три монолита; обновить `config_profiles.md` + тесты loader.  
2. **Config fix:** недостающие `vad.threshold|neg_threshold|min_silence_ms`; silero читает cfg; unit «ключ из yaml доходит».  
3. **Silero tune:** runner/заметки `eval/d1/4/` по recovery-плану (rescue → regression).  
4. **Не в этой ветке:** реализация TEN/FSMN fallback; отдельный `config/llm/*.yaml` (заложить контрактом); генерация «толстых» yaml в git.

Коммит на main перед веткой: `research_plan.md` (FSMN) + этот план + recovery-план — по ✅ списка ниже.

---

## 7. Чеклист на утверждение

Прошу ✅ / правки по пунктам:

1. **Домены:** speech / chunking / llm / runtime — ок?  
2. **Слои:** `base.yaml` + `profiles/{demo,dev,prod}.yaml`, merge **при загрузке** (не коммитить склеенные копии)?  
3. **Debug:** опциональный `scripts/render_config.py` печатает итог — ок?  
4. **Обязательный вынос:** `threshold`, `neg_threshold`, `min_silence_ms`.  
5. **Quality G1 в конфиг** — в этой ветке или отложить?  
6. **`fallback: fsmn_fallback`** как допустимое значение в схеме уже сейчас (реализация — позже) — ок?  
7. После ✅ — коммит планов + `research_plan`, ветка, реализация.  
8. **Новых зависимостей не добавляем** (uv не про конфиги; хватает PyYAML + Pydantic / settings) — ок?
