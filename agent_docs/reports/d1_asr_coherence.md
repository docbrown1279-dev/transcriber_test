# D1 ASR coherence — VAD fragmentation diagnosis + N2 tune

Branch: `cursor/d1-asr-coherence`. Baseline hyp: `results/d1_dual/` (not overwritten). New hyp: `results/d1_coherence/`.

## Why it fragments (N0 = dual-path)

Dual-path fixed **coverage** (`dynaudnorm` on `vad_input` → speech_sec 138→826) but created **crumbs**.

| layer | n | median dur | notes |
|---|---:|---:|---|
| Silero regions | 689 | 0.80 s | 411 &lt;1 s; 228 &lt;0.5 s |
| Turns / ASR | 347 | 2.02 s | 170 &lt;2 s; 132 segs ≤3 words |

Root cause chain:

1. **C3 dynaudnorm** (eval/d1/4) lifts quiet speech → Silero fires on short bursts. Research 1f2 never retuned Silero for phrase length (`min_speech`~200 ms was for *dropping* crumbs, not glueing).
2. **Silero split logic** ends a region after `min_silence_ms=200` below `neg_threshold`. Breath / micro-pauses ≈0.3–1.0 s become hard cuts.
3. **Gaps between regions** median **0.64 s**. With `vad_premerge_gap_sec=0.3` only **123/688** gaps glue; **404** would glue at 0.8 s.
4. **Turn merge** `same_speaker_gap=0.3` + `absorb=1.0` leaves **62** same-speaker adjacent pairs in (0.3, 0.8] unmerged. ASR `max_segment_seconds=25` does not re-glue — segments ≈ turns.

Offline simulation (same `speech.json` / `turns.json`, no re-ASR):

| knobs | n turns | median | &lt;2 s |
|---|---:|---:|---:|
| N0 (0.3 / absorb 1.0) | ~347 | 2.0 s | 170 |
| premerge islands @0.8 only | 285 | 2.0 s | 139 |
| re-merge turns gap0.6 absorb2.0 | 196 | 4.8 s | 0 |

## Prior research settings (do not re-open stack)

| source | relevant finding |
|---|---|
| `docs/research_results/reports/1f2/conclusions.md` | Silero primary; thresholds **not** tuned; only post `min_speech`~200 ms |
| `agent_docs/reports/d1_silero_tune.md` | B1/B2 threshold lower → marginal rescue cover; **does not** fix holes |
| `agent_docs/reports/d1_vad_compressor.md` | **C3 dynaudnorm** best cover; tradeoff = denser crumbs |
| `agent_docs/reports/d1_dual_full.md` | dual-path accepted for coverage; higher hole *count* expected from crumbs |

Threshold knob alone is the wrong lever for coherence. Merge/premerge (+ optional softer C1 later) is the right one.

## Applied config (N2)

In `config/base.yaml` (vs N0 dual-path):

| key | N0 | N2 |
|---|---:|---:|
| `vad.min_speech_ms` | 200 | **400** |
| `diarization.merge.vad_premerge_gap_sec` | 0.3 | **0.8** |
| `diarization.merge.same_speaker_gap_sec` | 0.3 | **0.6** |
| `diarization.merge.absorb_turn_shorter_than_sec` | 1.0 | **2.0** |

Unchanged: Silero 0.5/0.35, `min_silence_ms=200`, dual-path dynaudnorm, per-turn ASR gain.

Deferred: N3 (C1 acompressor instead of dynaudnorm), H3 gain/`min_asr_sec`, H4 GigaAM decode knobs.

## Run

```bash
.venv/bin/python -m transcriber run \
  -j results/d1_coherence \
  -a cloud_in/inputs/audio/voice_002.m4a \
  -u correction_suggest
```

## Results (full `voice_002`, N2 run)

| metric | d1_dual (N0) | d1_coherence (N2) | Δ |
|---|---:|---:|---|
| VAD regions | 689 | **537** | −152 |
| speech_sec | 826 | 783 | −43 (min_speech 400 drops crumbs) |
| turns / ASR segs | 347 | **216** | −131 |
| median turn dur | 2.0 s | **4.2 s** | +2.2 s |
| turns &lt;2 s | 170 | **18** | |
| turns ≥4 s / ≥6 s | 62 / 27 | **114 / 68** | |
| segs ≤3 words | 132 | **23** | −109 |
| median words / seg | 5 | **8** | |
| text chars (approx) | 11587 | **12804** | + |
| speaker_count | 16 | 13 | |
| holes (count) | 273 | 167 | fewer inter-turn gaps |
| ASR runtime_sec | 151 | 129 | fewer slices |

### Readability (human spot-check, start of file)

N0 split «связь» / «правильные» / canalization crumbs → N2 joins opening into longer phrases; canalization/parking still slightly cut but neighbors read as sentences. Absorb=2.0 can pull a short neighbor across speakers (watch `156–162` vs dual SPEAKER_02 crumb) — acceptable for demos, revisit if speaker purity matters more than phrase length.

### Verdict

**H1+H2 work.** Coherence acceptance (median ~4–6 s, far fewer ≤3-word stubs) met without changing ASR engine or dual-path idea. Next only if needed: N3 (C1 vs C3 preprocess) if speech_sec −43 hurts rescue windows; H3 if long slices still garble.
