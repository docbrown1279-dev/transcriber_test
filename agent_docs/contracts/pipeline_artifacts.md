
# Contract: pipeline artifacts

Draft, Phase A. Every pipeline step reads and writes JSON inside the job directory
`{storage_root}/jobs/{job_id}/`. Timestamps are seconds (float, 3 decimals) relative to the
start of the uploaded file. Artifact schemas are the single source of truth shared by
`@Coder`, `@Tester` and the quality gates.

Common rules:

- All artifacts carry `schema_version` (`"1"` for the demo) and `job_id`.
- LLM never emits or edits time values. Chapter and insight times are copied from ASR segments.
- An empty ASR result is a valid value (`text: ""`), not an error. A missing interval is a *hole*
  and is recorded separately.
- No user text is written to application logs; artifacts are the only place transcript text lives.

## 1. `audio.json`

```json
{
  "schema_version": "1", "job_id": "…",
  "source": {"filename": "meeting.m4a", "size_bytes": 23993730, "duration_sec": 1468.602},
  "normalized": {"path": "normalized.wav", "sample_rate": 16000, "channels": 1},
  "loudness": {"rms_dbfs": -33.4, "peak_dbfs": -6.1, "gain_db": 10.4, "gain_applied": true},
  "runtime_sec": 4.2
}
```

`gain_db` follows research stage 1e: `0` when `rms_dbfs >= gain_rms_threshold_dbfs`, otherwise
`min(target_dbfs - rms_dbfs, max_gain_db)`, additionally clamped so `peak_dbfs + gain_db <= -1`.
Linear `volume=` only — no dynamic filters, no denoise.

## 2. `speech.json` (VAD)

```json
{
  "schema_version": "1", "job_id": "…",
  "detector": "silero", "fallback_used": false,
  "regions": [{"start": 0.000, "end": 9.970}],
  "speech_sec": 812.4, "runtime_sec": 11.8
}
```

`fallback_used` is `true` only when the optional TEN fallback filled holes of the primary VAD;
the artifact must then list `fallback_regions` separately so the origin of every region is known.

## 3. `turns.json` (diarization + merge)

```json
{
  "schema_version": "1", "job_id": "…",
  "diarizer": "wespeaker_onnx", "speaker_count": 4,
  "turns": [{"id": "t0001", "start": 9.970, "end": 24.140, "speaker": "SPEAKER_00"}],
  "holes": [{"start": 0.000, "end": 9.970}],
  "merge": {"same_speaker_gap_sec": 0.3, "absorb_shorter_than_sec": 1.0},
  "runtime_sec": 63.1
}
```

Merge order is fixed: join neighbouring same-speaker turns with gap `<= same_speaker_gap_sec`
using `min(start)`/`max(end)`, then absorb turns shorter than `absorb_shorter_than_sec` into the
nearest neighbour, preferring the same speaker on a tie. Holes `>= 0.5 s` are recorded, never
silently dropped.

## 4. `transcript.json` (ASR)

```json
{
  "schema_version": "1", "job_id": "…",
  "engine": "gigaam_v3_rnnt", "language": "ru",
  "segments": [
    {"id": "s0001", "turn_id": "t0001", "start": 9.970, "end": 24.140,
     "speaker": "SPEAKER_00", "text": "…", "gain_db": 10.4, "empty": false}
  ],
  "holes": [{"start": 0.000, "end": 9.970}],
  "max_segment_sec": 25,
  "runtime_sec": 78.9
}
```

Segments longer than `max_segment_sec` are split on the time axis only and each part is
re-extracted from the source audio. `id` values are stable and are the only handle later stages
use to reference text (`source_ids`).

## 5. `quality.json` (gate G1 output)

```json
{
  "schema_version": "1", "job_id": "…",
  "russian_word_ratio": 0.953, "total_words": 2841, "latin_chars_in_segments": 0,
  "empty_segments": 2, "hole_sec_total": 41.7,
  "oov_words": ["касторография"],
  "verdict": "pass", "checks": [{"id": "G1.1", "status": "pass", "value": 0.953, "threshold": 0.9}]
}
```

## 6. `suggestions.json` (dictionary, demo = suggestions only)

```json
{
  "schema_version": "1", "job_id": "…",
  "dictionaries": [], "applied": false,
  "suggestions": [
    {"segment_id": "s0042", "span": [12, 26], "found": "касторография",
     "suggested": "квартирография", "confidence": 0.71, "start": 512.3, "end": 514.9}
  ]
}
```

The demo never rewrites `transcript.json`. `applied` stays `false` in profile `demo`; the field
exists so `prod` manual review can flip it.

## 7. `chapters.json` (chunking + titles)

```json
{
  "schema_version": "1", "job_id": "…",
  "chunker": "packing_c", "embedding_model": "rubert_tiny2", "similarity_threshold": 0.70,
  "chapters": [
    {"id": "C00", "start": 9.970, "end": 118.730, "source_ids": ["s0001", "s0002"],
     "speakers": ["SPEAKER_00", "SPEAKER_01"], "title": "Подключение канализации через паркинг",
     "duration_sec": 108.76}
  ],
  "metrics": {"chapters_per_minute": 0.57, "short_chapters": 1, "long_chapters": 2},
  "runtime_sec": 214.0
}
```

`start` is the `start` of the first referenced segment, `end` is the `end` of the last one —
copied, never recomputed by a model. `title` is produced by the P1 prompt, `<= 10` words, must not
start with a stamp phrase (see `quality_gates.md`).

## 8. `insights.json` (per-chapter extract)

```json
{
  "schema_version": "1", "job_id": "…",
  "provider": "gemini", "model": "gemini-2.5-flash", "prompt_id": "extract_v1",
  "chapters": [
    {"id": "C00", "start": 9.970, "end": 118.730,
     "key_points": [{"text": "Подключение канализации ведут через паркинг",
                     "src": [{"segment_id": "s0003", "start": 41.2, "end": 47.8,
                              "speaker": "SPEAKER_00"}]}],
     "actions": [], "open_questions": [], "asr_notes": []}
  ],
  "llm_calls": 12, "runtime_sec": 25.4
}
```

`key_points`: 2–6 concrete statements (decision, number, condition, agreement) or an empty list.
`actions` and `open_questions` only when present in the text, otherwise `[]`. `asr_notes` are
observations about probable ASR errors and never modify `transcript.json`. Every `src` entry must
reference an existing `segment_id` of the same chapter.

## 9. `report.json` + `report.md`

```json
{
  "schema_version": "1", "job_id": "…",
  "summary": "…",
  "key_moments": [{"text": "…", "start": 41.2, "end": 47.8, "speaker": "SPEAKER_00",
                   "chapter_id": "C00"}],
  "speakers": [{"id": "SPEAKER_00", "label": null, "speech_sec": 412.7}],
  "chapters": [{"id": "C00", "title": "…", "start": 9.970, "end": 118.730}],
  "provider": "gemini", "model": "gemini-2.5-flash", "llm_calls": 1,
  "draft_warning": true, "runtime_sec": 17.2
}
```

`key_moments` holds 5–12 items; each `start`/`end` must be present in `insights.json` `src` or in
`chapters.json` (clock-gate). `speakers[].label` stays `null` in the demo — no name guessing.
`draft_warning` is always `true` in the demo and drives the UI wording ("черновик протокола"),
per the stage 3c conclusion that 8B/Flash insights need human proofreading.
`report.md` is a rendering of the same data — never an independent LLM answer.

## 10. `job.json` (progress and lifecycle)

```json
{
  "schema_version": "1", "job_id": "…", "created_at": "…", "expires_at": "…",
  "client_ip_hash": "…", "state": "running",
  "stages": [{"stage": "asr", "status": "done", "pct": 100, "runtime_sec": 78.9,
              "message": null}],
  "error": null
}
```

`state`: `queued | running | done | failed | expired`. `client_ip_hash` is a salted hash, never
the raw address. `expires_at = created_at + result_ttl_hours`; the TTL sweeper deletes the whole
job directory including the uploaded file.
