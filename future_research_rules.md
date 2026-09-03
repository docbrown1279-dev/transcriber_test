# Research layout v1 (утверждено)

**Scope:** оркестрация **исследования в Cursor Cloud** (`cloud_in` → Cloud Agent → `cloud_out`).  
**Не это:** общий planner разработки приложения — отдельный агент/правила.

Два актора: **оркестратор** (локально, `.cursor/`) и **облачный исследователь** (ветка handoff, `cloud_in/` → `cloud_out/`).

---

## Лимиты Cloud Agent (для планирования этапов)

По [докам Cursor](https://cursor.com/docs/cloud-agent) **нет публичного hard-limit по минутам** на один run. Управление — **spend limit** (доллары) и ручной/API stop. Long-running — отдельный режим (не для multi-repo). На практике планировать так:

- один handoff = **одна цель + один PR/ветка**, проверяемый артефакт в `cloud_out/`;
- длинный пайплайн = **несколько коротких этапов** с human gate между ними;
- тяжёлые прогоны (ASR/LLM) — в environment snapshot, не «один агент на всё приложение».

---

## Git vs не-git

| В git | В `.gitignore` |
|---|---|
| `scripts/` | `data/` — всё сырьё, включая gold |
| `progress/` | `prompts/` — архив черновиков промптов |
| `cloud_in/`, `cloud_out/` — **обмен между ветками** | `results/` — артефакты по этапам |
| `docs/` (опционально; стабильное ТЗ) | `.cursor/` — оркестратор, субагенты, rules |

**Ignore = версии через копии/бэкап, не через git.**

Исходники в `data/` между этапами **не переписываем** — только копии (`data/snapshots/{stage}/` при необходимости).

---

## Дерево

```
repo/
├── docs/                    # стабильное ТЗ (редко меняется)
├── progress/
│   ├── plan.md              # машина состояний: этапы, CURRENT, frozen stack
│   └── log.md               # handoff / pull / closed (коротко)
├── scripts/                 # общие runners, pack, check (eval-логика ok)
│
├── cloud_in/                # ★ in git — посылка в облако (перезапись каждый handoff)
│   ├── HANDOFF.md
│   ├── prompt.md            # один промпт текущего этапа
│   ├── inputs/              # только нужное сейчас
│   └── agent/               # роль облака (rules/skills стабильные)
│       ├── AGENTS.md
│       └── rules.md
│
├── cloud_out/               # ★ in git — ответ облака (агент коммитит сюда)
│
├── data/                    # ignore — сырьё, eval, snapshots
├── prompts/                 # ignore — архив промптов оркестратора
├── results/                 # ignore — по этапам после разборки out
│   └── {stage}/
│       ├── report.md
│       ├── llm/
│       └── manifest.json
│
└── .cursor/                 # ignore — оркестратор RESEARCH (не product planner)
    ├── rules/               # research-layout, research-plan, cloud-handoff, cloud-ingest
    ├── skills/cloud-agent-setup/
    └── agents/research-orchestrator.md
```

`cloud_in/` и `cloud_out/` — **без подпапок этапов**. Плоский обменник.

---

## Handoff (новый этап)

1. **Архив:** промпт из `cloud_in/prompt.md` → `prompts/{stage}_{date}.md`
2. **Очистка:** удалить лишнее из `cloud_in/`, `cloud_out/`
3. **Pack:** новый `cloud_in/prompt.md` + `cloud_in/inputs/` из `data/` (копии)
4. **`cloud_in/agent/`** — не менять каждый раз (skills/rules ссылаются на текущий `prompt.md`)
5. Обновить `progress/plan.md` (CURRENT = этап)
6. Commit + push ветки handoff

---

## Pull (облако вернулось)

1. Pull ветки → `cloud_out/` заполнен
2. **Разложить:**
   - отчёты, llm, md → `results/{stage}/`
   - принятые runners → `scripts/` (commit)
   - тяжёлое / архив → `data/` или удалить
3. **Progress:** `progress/log.md` + статус в `plan.md`
4. **Очистить** `cloud_in/`, `cloud_out/` (после переноса)
5. Commit `progress/` (+ `scripts/` если было) на dev

---

## Promote to main (утверждено по смыслу)

Цель `main`: **основные решения исследования** + **gold для локальной проверки**. Не тащим модели, полные исходники и исследовательский код — приложение собираем уже по новой архитектуре.

### В `main`

| Что | Зачем |
|---|---|
| `docs/research_plan.md` (можно ужать до «frozen stack») | план + зафиксированный выбор |
| Общий отчёт / conclusions: `results/reports/notes.md` + `*/conclusions.md` + итоговые `notes.md` закрытых этапов | **какой стек выбран** (ASR, VAD, chunking, LLM) и почему |
| `eval/` (gold клипы / эталоны) | локальная и product-проверка; **в `cloud_in/` не кладём** |
| `docs/eval_clips.md`, `docs/eval_protocol.md` | как пользоваться gold |

Опционально позже: один короткий `docs/stack.md` («только решения, 1 страница»), если plan раздут.

### Не в `main` (или не в первый promote)

| Что | Почему |
|---|---|
| `models/`, `.gguf` | вес / лицензии — ставим по инструкции |
| `data/raw`, полные ASR dumps, `results/llm/**/raw/` | шум и объём |
| Исследовательские `scripts/stage*`, ветки этапов | код MVP пишем заново по правилам; runners — по мере нужды |
| `.cursor/` research-оркестратор | локальный |
| `cloud_in/`, `cloud_out/` | обменник, не продукт |
| `data/3c_data/transcript.md` со spliced gold | дубль эталона в «рабочем» виде — не нужен в freeze |

### Gold vs облако

Gold **может лежать в git на `main`**. Cloud Agent, клонирующий ветку от `main`, *технически* может открыть `eval/`. Защита мягкая, но достаточная при дисциплине:

1. в `cloud_in/` gold **никогда** не копируем;
2. в `cloud_in/agent/` — запрет читать `eval/`;
3. handoff-промпт не ссылается на эталонные ответы.

Жёстче (если понадобится): отдельный private repo / ветка только для человека — сейчас не усложняем.

### Поток promote

1. Ветка `promote/research-freeze`.  
2. Снять `eval/` из ignore (или точечный `git add -f`), закоммитить план + отчёты решений + gold.  
3. Без `.env`, без моделей, без сырых llm/asr.  
4. PR → `main`. Дальше product planner / автономная сборка опираются на **решения + gold**, не на 3c insights dump.

---

## Роли

| Актор | Где инструкции | Меняется каждый этап |
|---|---|---|
| Оркестратор research | `.cursor/agents/research-orchestrator.md` + rules/skill | нет |
| Облачный исследователь | `cloud_in/agent/` (пишет оркестратор) | только `prompt.md` + `inputs/` |
| Product planner | отдельно (не эти rules) | — |

Облако: читать `cloud_in/`, писать `cloud_out/`. `progress/plan.md` — только узнать CURRENT; остальные этапы не трогать.

---

## Eval

`data/eval/` — ignore, версии копиями. В `cloud_in/inputs/` только pack без меток gold. Review локально → `results/{stage}/review.md`.

---

## Оркестратор: rules / skill / subagent

Все `.cursor/rules|skills|agents` ниже — **только Cursor Cloud research**, не общий planner.

| Артефакт | Когда |
|---|---|
| `research-layout` (alwaysOn) | всегда: карта папок, stop-list |
| `research-plan` | новый этап, критерии, черновик промпта |
| `cloud-handoff` | pack `cloud_in/`, push |
| `cloud-ingest` | pull `cloud_out/`, sort |
| skill `cloud-agent-setup` | перед первым handoff / смена env |
| agent `research-orchestrator` | цикл plan → setup → handoff → ingest |

Правила для **облака** оркестратор кладёт в `cloud_in/agent/` при handoff.

---

## Ещё не сделано

- Шаблон `cloud_in/agent/` (AGENTS.md + rules.md: запрет `eval/`)
- Promote-ветка: plan + reports + `eval/` → PR в `main` (без моделей/кода этапов)
- Product planner: MVP из freeze
- Заготовки `progress/plan.md` / `log.md`
