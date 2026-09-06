# Manuals (инструкции для человека)

| Документ | О чём |
|---|---|
| [`cloud_flow.md`](cloud_flow.md) | Облачный цикл: `/cloud_push`, `/cloud_pull`, скрипты `scripts/cloud_*.sh` |
| [`manual_testing.md`](manual_testing.md) | Ручная проверка / smoke по этапам; **демо UI (D4)** |
| [`configuration_guide.md`](configuration_guide.md) | Профили `demo`/`dev`/`prod` в YAML, секреты в `.env`, UI-лимиты |
| [`llm.md`](llm.md) | LLM: `base_llm.yaml`, бэкенды, промпты; кнопка саммари в UI |

## Сопровождение

При изменении облачного цикла, каталогов обмена или ролей агента — обновлять `cloud_flow.md` в том же изменении, что и скрипты/`cloud_in/agent/`.  
При смене CLI, smoke-критериев этапа, потока веб-демки или exit criteria — `manual_testing.md`.  
При смене выбора профиля / раскладки `config/*.yaml` / `ui.*` — `configuration_guide.md`.  
При смене LLM-бэкендов, промптов, схем или лимита вызовов саммари — `llm.md`.
