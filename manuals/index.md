# Manuals (инструкции для человека)

| Документ | О чём |
|---|---|
| [`cloud_flow.md`](cloud_flow.md) | Облачный цикл: `/cloud_push`, `/cloud_pull`, скрипты `scripts/cloud_*.sh` |
| [`manual_testing.md`](manual_testing.md) | Ручная проверка / smoke по этапам (D0…) |
| [`configuration_guide.md`](configuration_guide.md) | Настройка YAML: профили `demo`/`dev`/`prod`, `APP_PROFILE`, секреты |

## Сопровождение

При изменении облачного цикла, каталогов обмена или ролей агента — обновлять `cloud_flow.md` в том же изменении, что и скрипты/`cloud_in/agent/`.  
При смене CLI, smoke-критериев этапа или exit criteria — `manual_testing.md`.  
При смене выбора профиля / раскладки `config/*.yaml` — `configuration_guide.md`.
