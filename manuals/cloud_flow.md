# Облачный цикл разработки (product)

Кратко: человек проверяет инструкции и результат; всё остальное — Cursor-команды или скрипты.

```text
проверил инструкции
      ↓
/cloud_push   (или ./scripts/cloud_handoff.sh)
      ↓
Cloud Agent на ветке из вывода + вставка PASTE-блока
      ↓
/cloud_pull   (сначала отчёты; код только если gate PASS)
      ↓
draft PR → ручной шлюз → merge
```

## Cursor-команды (предпочтительно)

В чате Agent: `/cloud_push` или `/cloud_pull` (файлы `.cursor/commands/`).  
Команда говорит локальному агенту **сразу** выполнить скрипт, без вопросов «закоммитить?».

| Команда | Что делает |
|---|---|
| `/cloud_push` | `cloud_status` → при OK commit/push → печатает **ветку** и PASTE для Cloud Agent |
| `/cloud_pull` | сначала `cloud_out` → отчёты; при Verdict PASS/PASS_WITH_WARNINGS — checkout всего кода + draft PR |

Промпт этапа **свой на каждый этап**: это всегда актуальный `cloud_in/prompt.md` (D0 ≠ D1 ≠ D2). Ветка тоже своя (`cursor/demo-d0-…`, `cursor/demo-d1-…`, …) — её пишет `/cloud_push`.

Ограничение Cursor: hook `permission: allow` сейчас **не** снимает системный диалог Shell надёжно. Команды убирают вопросы агента; если IDE всё же спросит доступ к git/network — подтвердите один раз (или включите auto-run для терминала в настройках).

## Allowlist терминала (не «папка», а префиксы команд)

В Cursor **нет** правила «разрешить всё из `scripts/`». Есть allowlist **префиксов команд** в `permissions.json` / Settings → Agents → Command Allowlist.

| Как | Пример | Смысл |
|---|---|---|
| Префикс команды | `./scripts/cloud_pull.sh` | любая строка, **начинающаяся** с этого |
| База + glob аргументов | `npm:install*` | `npm install …` |
| Широкий префикс | `git` | весь `git …` (осторожно) |

В репозитории: [`.cursor/permissions.json`](../.cursor/permissions.json) — префиксы наших `cloud_*.sh` + подсказки `autoRun`.

**Важно сейчас:**

1. Run Mode: **Allowlist** (или Auto-review) — Settings → Agents → Approvals & Execution.  
2. Project-level `terminalAllowlist` в части сборок Cursor **не подхватывается** (баг); надёжно продублировать те же строки в `~/.cursor/permissions.json`.  
3. У вас в `~/.cursor/permissions.json` уже свой список (pptx skill) — файл **заменяет** in-app allowlist целиком для terminal, поэтому cloud-префиксы нужно **добавить туда же**, не надеяться только на IDE UI.

Пример дописать в `~/.cursor/permissions.json` → `terminalAllowlist`:

```json
"./scripts/cloud_status.sh",
"./scripts/cloud_handoff.sh",
"./scripts/cloud_pull.sh",
"./scripts/cloud_ingest.sh",
"./scripts/cloud_pr.sh",
"./scripts/cloud_cleanup.sh"
```

После правки — полный перезапуск Cursor.

## Роли каталогов

| Каталог | Кто пишет | Что это |
|---|---|---|
| `cloud_in/` | локальный planner / handoff | задание этапа + входные файлы |
| `src/`, `config/`, `tests/` | облачный агент | код продукта |
| `cloud_out/` | облачный агент | отчёт прогона (gate, meta, BLOCKED) |
| `agent_docs/reports/` | `cloud_pull` / ingest | постоянная копия отчётов после pull |
| `docs/` | локально (часто в ignore) | ТЗ / research — облаку не нужно |

`cloud_out` по смыслу — отчёты (`cloud_reports`). Имя обменника оставляем.

## Делает ли агент PR?

**Нет.** Облачный агент только:

1. реализует этап;
2. пишет `cloud_out/gate_*.md` и `run_meta.json`;
3. коммитит и **пушит ветку** `cursor/demo-d{N}-…`.

Draft PR открывает `/cloud_pull` (через `scripts/cloud_pr.sh`) или вручную `./scripts/cloud_pr.sh`.

## Что проверяет человек (только это)

1. **До отправки:** инструкции этапа и посылка (`cloud_in/prompt.md`, список Inputs).
2. **После возврата:** `agent_docs/reports/{stage}/gate_*.md` и diff/PR — ручной шлюз качества.

---

## Команды CLI (то же без slash)

Все скрипты из корня репозитория. Нужны: `git`, `bash`; для PR — `gh`.

```bash
./scripts/cloud_status.sh
./scripts/cloud_handoff.sh              # push + PASTE
./scripts/cloud_handoff.sh --dry-run
./scripts/cloud_pull.sh                 # reports → code if PASS
./scripts/cloud_pull.sh --reports-only
./scripts/cloud_pull.sh --force-code    # редко
./scripts/cloud_pr.sh
./scripts/cloud_cleanup.sh              # после merge
```

Старый `./scripts/cloud_ingest.sh` тянет ветку целиком; для обычного цикла предпочтителен `cloud_pull.sh`.

## Чеклист одного этапа

```bash
# 0) человек прочитал инструкции + cloud_in/prompt.md
/cloud_push
# → Cloud Agent на напечатанной ветке, вставить PASTE
# 1) дождаться push от облака
/cloud_pull
# 2) человек: gate + PR → merge
```

## Типовые сбои

| Симптом | Что сделать |
|---|---|
| `cloud_status` FAIL | допаковать `cloud_in/inputs/`, не пушить |
| `NO_REPORTS` | облако ещё не закончило — подождать, снова `/cloud_pull` |
| `FAIL` / `BLOCKED` без кода | так задумано; править промпт/посылку, новый push |
| системный Ask на Shell | подтвердить git/network; hooks `allow` в Cursor пока ненадёжны |
| нет `gh` | поставить в `~/.local/bin` (без sudo) или через apt; затем `gh auth login -h github.com -p ssh -w` (код — в терминале, не на сайте) |

## [UPDATED] После merge D0

Этап D0 влит в `main` (PR #16). Локальный smoke каркаса: [`manual_testing.md`](manual_testing.md) § Stage D0. Профили YAML: [`configuration_guide.md`](configuration_guide.md).

## Сопровождение

Меняя цикл — обновлять этот файл, `scripts/cloud_*.sh` и `.cursor/commands/cloud_{push,pull}.md`.
