# Черновик этапа D4.1 — производительность / конвейер (Фаза A→B)

**Статус:** CLOSED (merged main; toc_mode=b default)  
**Предшественник:** D4 UI на `main`.  
**Следующий:** D5 Docker + `--cpus=2 --memory=8g` (после выбора победителя A/B).  
**Инструкции:** [`../instructions/tester_D4_1.md`](../instructions/tester_D4_1.md), [`../instructions/coder_D4_1.md`](../instructions/coder_D4_1.md).

---

## 1. Вердикт по схеме «ASR → склейка → LLM, пока ждём API — следующий ASR»

**Жизнеспособна** как вариант B, с условиями:

1. **Диаризация сейчас на весь файл** (VAD→WeSpeaker до ASR). «Фрагмент ASR» = очередной slice/turn после готовых `turns.json`, не стрим сырого аудио. Это ок для демо-теста.
2. **Packing C не закрывает главу без следующего куска.** Сначала pack по спикерам (gap/слова), потом cosine merge с соседом. Хвост всегда provisional: закрываем главу только когда merge решил *не* склеивать с новым unit (или EOS / cap длительности). «Склейка всегда ждёт следующий кусок» — верно.
3. **Во время самого ASR-инференса** на 2 ядрах — ничего параллельно (как предложено). Rubert не крутить *внутри* forward GigaAM.
4. **Окно между slice:** быстро pack+embed нового unit → если глава closed → fire async title API → сразу следующий ASR, пока API в полёте. HTTP почти не ест CPU/RAM.
5. **Пик RAM:** GigaAM (~1,6 ГиБ) остаётся загруженным между slice + краткий rubert. На 8 ГБ нужно **измерить**, не гадать. Если OOM — unload не нужен между slice (дорого), но rubert держать лёгким / encode в том же процессе аккуратно.
6. **Батч titles (вариант A)** vs **title-as-ready ∥ ASR (вариант B):** разный UX (время до первой главы) и разный total wall. Оба гоняем.
7. **Insights + summary** — отдельный хвост после TOC; стрим ответа API — плюс к UX, не обязателен в первом замере.
8. **UI-стрим глав во время транскрибации** — после того как B докажет выигрыш по wall/TTFT.

Research: rubert на полную встречу ~2 с — сам по себе не тормоз; выигрыш B = **перекрытие LLM wait с ASR**, не «ускорить эмбеддинги».

---

## 2. Два варианта для A/B

| id | Схема | Суть |
|---|---|---|
| **A** | Sequential + batch titles | normalize→VAD→diar→ASR(all)→unload→chunk(C)→**один/few** LLM titles→(позже) insights/report |
| **B** | Slice pipeline | VAD→diar→ **loop:** ASR slice → incremental pack/embed → commit chapter? → async title → next slice (ASR exclusive on 2 cores) → flush EOS → insights/report отдельно |

Общее: `onnx_threads`/OMP/torch = 2; insights/summary не в критическом пути первого сравнения (замерить отдельно или одним хвостом после titles).

---

## 3. Порядок работ

1. **Замер baseline** текущего кода (по сути близко к A без batch) — **без** cgroup-лимитов, полный или 10–15 мин срез.
2. Coder: harness таймингов + реализация A (batch) и B (incremental + overlap).
3. Повторный замер A vs B на том же клипе.
4. D5: победитель под `--cpus=2 --memory=8g`.

---

## 4. Не делать в D4.1

- Docker / cgroup (D5).
- Смена ASR / pyannote / Jina.
- Обязательный UI-стрим (только если B выбран и останется время).
- Force-push `main`.
