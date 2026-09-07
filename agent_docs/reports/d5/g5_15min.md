# D5 Phase 2 — G5 hardware gate (15 min)

Date: 2026-09-07  
Audio: `/bench/voice_002_15min.m4a` (~900 s slice from voice_002)  
Limits: `--cpus=2 --memory=8g`  
Mode: `toc_mode=b` (`--mode b`)  
Harness: `python /app/scripts/bench_d5.py`

## Command

```bash
HOST_SECRETS="$PWD/var/secrets/transcriber.env"
docker run --rm --cpus=2 --memory=8g \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v "$HOST_SECRETS:/run/secrets/transcriber.env:ro" \
  -v "$PWD/var/bench/d5:/bench:ro" \
  -v "$PWD/agent_docs/reports/d5:/out" \
  -v transcriber-hf-cache:/home/app/.cache \
  -v transcriber-var:/var/transcriber \
  transcriber:runtime \
  python /app/scripts/bench_d5.py \
    --audio /bench/voice_002_15min.m4a \
    --mode b \
    --out /out/g5_15min.json
```

- **Exit code:** 0 (`G5_EXIT=0`)
- **OOMKill:** no (container completed and removed via `--rm`; JSON written)
- **Machine wall (host):** ~788 s docker elapsed

## Results (from `g5_15min.json`)

| Metric | Value |
|---|---|
| `total_wall_sec` | **784.664** (~13.1 min for 15 min audio) |
| `peak_rss_mb` | **2183.9** (~2.13 GiB) |
| chapters / titles | 9 |
| until | titles |

### Per-stage wall (artifact `runtime_sec`)

| Stage | wall_sec | peak_rss_mb |
|---|---:|---:|
| normalize | 1.311 | null |
| vad | 4.255 | null |
| diarize | 402.013 | null |
| asr | 370.528 | null |
| chunk | 57.21 | null |
| titles | 57.21 | null |

Process-level peak RSS is recorded once after `run_job` (`RUSAGE_SELF`). Per-stage RSS is not instrumented by the harness (null) — noted as WARN under G5.2 completeness, not a hard fail.

## Cold vs warm cache `[D5-G5-06]`

- **Cold / first downloads observed** in this run: Hugging Face fetches for Wespeaker ONNX and `cointegrated/rubert-tiny2` (progress bars in `g5_bench_stdout.log`).
- Volumes `transcriber-hf-cache` and `transcriber-var` persist weights for warmer subsequent runs.
- Measured `total_wall_sec` **includes** cold download time; warm re-run would be lower (not executed in this gate).

## Mode control

- Primary gate: **mode b** (default / plan).
- Optional mode **a** control run: **not** executed this session (time).

## Wall-time judgement `[D5-G5-03]`

~13 min wall for 15 min audio under 2 CPU / 8 GiB (with cold HF downloads) is acceptable for the demo gate. **No** recommendation to lower `audio.max_minutes` to 10 based on this run alone.

## Security

Secret value scrub of `g5_bench_stdout.log`: **none** leaked. Excerpt without HF progress noise: `g5_bench_stdout_excerpt.log`.
