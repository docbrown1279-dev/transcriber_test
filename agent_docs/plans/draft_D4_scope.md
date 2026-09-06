# Черновик этапа D4 — веб-интерфейс демки (Фаза A → B)

**Статус:** CLOSED (merged main `8371a79`); next → D4.1 perf  
**Инструкции:** [`../instructions/coder_D4.md`](../instructions/coder_D4.md), [`../instructions/tester_D4.md`](../instructions/tester_D4.md)  
**Предшественник:** D3 HUMAN_GATE PASS; diarization 0.85 → ~5 speakers (chapters/report **не** пересобираем).  
**Стратегия:** локальная демка без cloud handoff. HTML-stubs уже есть → wiring к пайплайну.  

---

## 1. Было в ТЗ / архитектуре vs делаем

| Было (узкое demo) | Делаем в D4 |
|---|---|
| upload → progress → **одна** страница протокола | upload → progress → **оглавление глав** → страница главы |
| `allow_editing` / `allow_player` false | true: примитивный edit + простой плеер |
| только файл | файл + **заглушка** парсера ссылок |

---

## 2. Поток UI

```
/  upload: файл | URL stub
  → warn+trim если duration > audio.max_minutes
  → /jobs/{id} progress (polling)
  → /jobs/{id}/result     оглавление + словарь/саммари stubs + плеер
  → /jobs/{id}/chapters/{cid}  текст + edit + плеер
```

Stubs: `/stubs/upload`, `/stubs/result`, `/stubs/chapter`.

---

## 3. Принятые решения

| Тема | Решение |
|---|---|
| Где | **Локально**, без cloud handoff |
| IP/day limit | **Не действует на localhost** (127.0.0.1 / ::1); на внешние IP — да |
| Concurrent jobs | По-прежнему лимит (в т.ч. на localhost) |
| Browser E2E | **Без Playwright** |
| Backend E2E | Module smoke «похоже на правду» (см. tester_D4) — v0 каркас, человек дополнит |
| `audio.max_minutes` | 30; длиннее → warn + trim |
| voice_002 D2/D3 | Не пересобираем |

---

## 4. Не делать

- Playwright, cloud handoff, PDF, real YouTube/Yandex fetch, force-push `main`.
- Пересборка chapters/insights/report voice_002.
