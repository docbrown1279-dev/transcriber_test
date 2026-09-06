# D4.1 Phase 0 — baseline unconstrained (10 min voice_002)

**Branch:** `cursor/demo-d4-1-perf`  
**When:** 2026-09-06  
**Audio:** first 600 s of `data/voice 002.m4a` → `var/bench/d4_1/voice_002_10min.m4a` (original untouched)  
**Job:** `var/bench/d4_1/job_baseline_10min`  
**Profile:** `demo` (LLM = qwen-plus)  
**Host:** ~16 CPU, ~27 GiB RAM; **no** Docker cgroup limits  
**Until:** `titles`

## Stages (`runtime_sec` in artifacts)

| Stage | wall (artifact) | Notes |
|---|---:|---|
| normalize | 1.6 s | ffmpeg + gain |
| vad (Silero) | 3.1 s | speech_sec ≈ 503 / 600 |
| diarize (WeSpeaker) | 77.6 s | 4 speakers, 84 turns |
| asr (GigaAM) | 56.3 s | 86 segs, 1 empty; RTF ≈ 0.094 |
| correction_suggest | ~0 | empty dict |
| chunk (packing_c + rubert) | **5.876 s** (offline remeasure) | 6 chapters |
| titles (qwen, 1 call/chapter) | **~15 s** | 6 calls sequential |

### Chunk caveat
First chunk pass logged **~190 s** because sandboxed/DNS retries hit HuggingFace for `rubert-tiny2` (model already cached).  
**Offline remeasure** (`HF_HUB_OFFLINE=1`): chapters `runtime_sec` = **5.876 s**, peak RSS ≈ **547.2 MiB** (`job_chunk_remeasure`). First-load ST cold start included.

### Peak RSS
Long speech→titles attempt (`time_baseline_10min.txt`): **Maximum RSS ≈ 1693 MiB** (~1.65 GiB) — consistent with GigaAM research (~1.6 GiB).  
Titles-only resume: ~60 MiB (API client).

### End-to-end (approx, unconstrained)
- Speech chain (normalize…asr) ≈ **1.6+3.1+77.6+56.3 ≈ 139 s** (~2.3 min) on this host  
- Titles: **6 LLM calls / 6 chapters**, ~2–3 s each, **~15 s** total  
- **Total useful wall** (speech + true chunk + titles) ≈ **160 s** (~2.7 min): speech ≈139 s + chunk 5.876 s + titles ~15 s  
- Inflated wall on first full attempt (~5.5 min) includes HF DNS retries — **not** representative

## Chapters (6) — several topics as expected

| id | range (s) | dur (s) | title |
|---|---|---:|---|
| C00 | 0.9–156.4 | 155.6 | Подключение к ливневой канализации УДС |
| C01 | 156.4–186.3 | 29.8 | Учет площади застройки и озеленения |
| C02 | 188.0–211.2 | 23.2 | Проверка решений разработчиков |
| C03 | 211.9–363.0 | 151.0 | Ландшафтная концепция и размещение светильников |
| C04 | 365.2–530.1 | 164.9 | Подключение кабеля и распределение нагрузки |
| C05 | 531.1–600.0 | 68.9 | Расчет нагрузки на квартиру |

## Phase 0 conclusions (for A/B)

1. On 10 min: **ASR is fast** (~56 s); **diarization** is the heavier local stage here (~78 s).  
2. **Titles are 1×N calls** — clear win for batch (A) or overlap with ASR (B).  
3. Rubert itself is not the story once offline; do not trust the 190 s chunk figure.  
4. Peak RAM ~**1.65 GiB** during ASR path — fits 8 GiB server with headroom if nothing else huge is loaded.

## Next
Phase 1 after Coder A/B: same `voice_002_10min.m4a`, compare total wall + TTFT + RSS.
