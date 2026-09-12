# G5.T TTFT hardware gate — 15′ voice_002

| Field | Value |
|-------|-------|
| Verdict | **PASS** (TTFT / RSS / OOM) |
| Host | `vladimir` (linux) |
| Date | 2026-09-12 |
| Image | `transcriber:runtime` id `9c17d078fc5d` (rebuilt for TTFT src) |
| Cold/warm | **Warm** HF/WeSpeaker cache (`transcriber-hf-cache` volume) |
| Profile | `demo` (`ttft_split: true`) |
| Audio | `/bench/voice_002_15min.m4a` (900 s) |
| Job dir | `var/bench/d5/ttft_split_g5` |
| JSON | `agent_docs/reports/d5_ttft_split/g5_ttft_15min.json` |

## Exact Docker command

```bash
HOST_SECRETS="/work/speech_rec_test/var/secrets/transcriber.env"
docker run --rm \
  --name d5_ttft_g5_bench \
  --cpus=2 --memory=8g \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -e TRANSCRIBER_PROFILE=demo \
  -v "$HOST_SECRETS:/run/secrets/transcriber.env:ro" \
  -v "$PWD/var/bench/d5:/bench:ro" \
  -v "$PWD/agent_docs/reports/d5_ttft_split:/out" \
  -v "$PWD/var/bench/d5/ttft_split_g5:/job" \
  -v transcriber-hf-cache:/home/app/.cache \
  -v transcriber-var:/var/transcriber \
  transcriber:runtime \
  python /app/scripts/bench_d5.py \
    --audio /bench/voice_002_15min.m4a \
    --mode b \
    --profile demo \
    --out /out/g5_ttft_15min.json \
    --job-dir /job
```

## Metrics

| Metric | Value | Gate |
|--------|-------|------|
| `ttft_first_chapter_sec` | **169.177** | ≤ 300 → PASS |
| `total_wall_sec` | 555.905 | complete → PASS |
| `peak_rss_mb` | 3688.5 (~3.60 GiB) | < 7 GiB → PASS |
| OOMKill | none | PASS |
| part01 `duration_sec` | 229.264 | ≤ 300 → PASS |
| n_parts | 4 | (product pause-cut; ref uses 3) |
| early_ready wall (log) | 169.2 s, 4 chapters | titles LLM started **after** publish |

## Notes

- File gain: `gain_db=1.657 capped=True max_gain_db=2.000` (file_max_db path).
- Titles did not block TTFT: `ttft early_ready` logged before chapter_titles LLM calls.
- Stage `diarize` wall_sec=0 in JSON is an artifact quirk of the split path (per-part diarization); wall is reflected in total / ASR / chunk.
