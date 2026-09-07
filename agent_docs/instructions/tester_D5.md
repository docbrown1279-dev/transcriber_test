# Tester instructions — stage D5 (Docker + G5 hardware, **local**)

Status precondition: `agent_docs/progress/stage_D5.md` contains `READY_FOR_TEST` (after Coder).  
You may prepare the 15‑min audio trim **before** READY_FOR_TEST.

Plan: [`../plans/draft_D5_scope.md`](../plans/draft_D5_scope.md).  
Contract: [`../contracts/docker_runtime.md`](../contracts/docker_runtime.md).  
Coder: [`coder_D5.md`](coder_D5.md).  
Gates: G5.* in [`../contracts/quality_gates.md`](../contracts/quality_gates.md).

**Local only.** No cloud handoff. **No GitHub Actions** (D5.1).

Write scope: `tests/` only if a tiny fix is required for container paths (prefer Coder env hooks); reports under `agent_docs/reports/d5/`.  
Do not edit `src/` to greenwash failures — file bugs for @Coder.  
Never commit real secret files.

## Phase 0 — prep (can start now)

1. Confirm Docker works: `docker version`.
2. Ensure build inputs exist on disk: `data/test_voice.m4a`, `models/` Silero ONNX (gitignored OK for local).
3. Trim **15‑minute** slice from `data/voice_002` audio (do not mutate original):

```bash
mkdir -p var/bench/d5
# adapt source path to whatever voice_002 media exists locally
ffmpeg -y -i data/voice_002/<source>.m4a -t 900 -c copy var/bench/d5/voice_002_15min.m4a
```

4. Prepare a **host-only** secrets file (outside git), same keys as the repo secrets example template (`JOB_IP_SALT`, demo LLM key, optional `HF_TOKEN`).

## Phase 1 — image build + in-container tests (after READY_FOR_TEST)

| ID | Check |
|---|---|
| `[D5-BUILD-01]` | `docker build --target runtime -t transcriber:runtime .` exit 0 |
| `[D5-BUILD-02]` | `docker build --target test -t transcriber:test .` exit 0 |
| `[D5-CTX-01]` | Image/test container sees `/app/data/test_voice.m4a` |
| `[D5-TEST-01]` | Unit tests green inside container (exclude or mark slow if needed — document) |
| `[D5-TEST-02]` | Soft regression on `test_voice` runs inside container (WARN allowed unless `REGRESSION_STRICT=1`) |
| `[D5-SEC-01]` | Run with secrets **volume** or `--env-file`; confirm `/healthz` / titles path can see key **names** present; no secret values in `docker logs` |
| `[D5-HEALTH-01]` | `runtime` container: `GET /healthz` → 200 with required env |

Example shape (adapt to Coder’s final flags):

```bash
docker build --target test -t transcriber:test .
docker run --rm \
  --cpus=2 --memory=8g \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v "$HOST_SECRETS:/run/secrets/transcriber.env:ro" \
  -v "$PWD/agent_docs/reports/d5:/out" \
  -e REGRESSION_REPORT_PATH=/out/regression_test_voice.md \
  transcriber:test
```

Record exact command + exit codes in the report.

Also run host-side sanity if useful: `uv run pytest tests/ -v` — not a substitute for `[D5-TEST-*]`.

## Phase 2 — G5 hardware gate (15 min, cgroup limits)

| ID | Check | Maps to |
|---|---|---|
| `[D5-G5-01]` | Job completes under `--cpus=2 --memory=8g` on 15‑min slice; **no OOMKill** | G5.1 |
| `[D5-G5-02]` | Per-stage wall + peak RSS written (`*.json` + md) | G5.2 |
| `[D5-G5-03]` | Total wall reported; if unacceptable → recommend `audio.max_minutes=10` | G5.3 |
| `[D5-G5-04]` | Peak RSS web+ASR `< 7 GiB` | G5.4 |
| `[D5-G5-05]` | Mode `toc_mode=b` (default); optional one `a` control run noted | plan |
| `[D5-G5-06]` | Cold vs warm cache noted (first download vs measured run) | plan |

Suggested run (adapt paths):

```bash
docker run --rm \
  --cpus=2 --memory=8g \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v "$HOST_SECRETS:/run/secrets/transcriber.env:ro" \
  -v "$PWD/var/bench/d5:/bench:ro" \
  -v "$PWD/agent_docs/reports/d5:/out" \
  -v transcriber-hf-cache:/home/app/.cache \
  transcriber:runtime \
  <bench command producing /out/g5_15min.json>
```

If Coder ships bench as `uv run python scripts/bench_d5.py …`, use that as container command override.

## Report layout

```
agent_docs/reports/d5/
  build_test.md          # Phase 1 commands + pytest summary
  g5_15min.md            # narrative
  g5_15min.json          # harness timings
  gate_D5.md             # PASS / PASS_WITH_WARNINGS / FAIL + G5 checklist
```

## Gate verdict

- **PASS:** build+in-container tests OK; G5.1–G5.4 satisfied; reports present.
- **PASS_WITH_WARNINGS:** completes but wall too high → recommend 10 min; or soft regression WARN only.
- **FAIL:** OOM, build broken, healthz fails with secrets mounted, or peak RSS ≥ 7 GiB.

Append result to `agent_docs/progress/stage_D5.md` and one line to `agent_docs/progress/log.md`.

## Out of scope

- Authoring `.github/workflows/*` (D5.1).
- Publishing image to a registry (optional note only).
- Browser Playwright E2E.
