# Stage D5 — Docker + demo hardware gate

## 2026-09-07 — Planner
- STATUS: PLAN_DRAFT
- Plan: `agent_docs/plans/draft_D5_scope.md`
- Predecessor: D4.1 CLOSED (`toc_mode=b`)
- Focus: reproducible image; G5 under `--cpus=2 --memory=8g` on 15 min slice
- Compose: not required for gate (optional convenience only)
- Build context: src, config, models, pyproject+lock, tests (CI stage), bench script; ignore data/eval/var/docs/agent_docs/…
- Next: user ✅ → Phase B (`coder_D5.md`, `tester_D5.md`)

## 2026-09-07 — Planner (rev2)
- STATUS: PLAN_DRAFT
- Keep `data/test_voice.m4a` in build context (regression); ignore rest of `data/`
- Secrets: volume / host env-file only (never COPY into layers)
- In-container tests: Dockerfile target `test` → pytest
- GitHub Actions deferred to **D5.1**
- Await ✅ → Phase B

## 2026-09-07 — Planner (Phase B)
- STATUS: INSTRUCTIONS_READY
- Instructions: `agent_docs/instructions/coder_D5.md`, `tester_D5.md`
- Contract: `agent_docs/contracts/docker_runtime.md`
- Manual: `manuals/docker.md`
- Next: @Coder Dockerfile + .dockerignore + TRANSCRIBER_DOTENV; then @Tester in-container pytest + G5

## 2026-09-07 — Coder
- STATUS: READY_FOR_TEST
- Files:
  - `Dockerfile` (multi-stage: builder → builder-test → runtime + test)
  - `.dockerignore` (`data/**` + `!data/test_voice.m4a`; secrets/caches/agent_docs ignored)
  - `src/transcriber/config/loader.py` (`TRANSCRIBER_DOTENV`, `TRANSCRIBER_STORAGE_ROOT`)
  - `scripts/bench_d5.py` (G5 full-pipeline bench; reuse `bench_d4_1.py` for titles-only)
  - `manuals/docker.md` (mount/report/bench commands)
- Verified:
  - `uv run ruff check src/` → pass
  - `uv run mypy src/transcriber/config/loader.py` → pass (full `mypy src/` has pre-existing `titles.py` errors, untouched)
  - `uv run bandit -r src/transcriber/config/loader.py -ll` → pass
  - smoke: `TRANSCRIBER_DOTENV` + `TRANSCRIBER_STORAGE_ROOT` OK
  - `docker build` **not run**: Docker client present, daemon socket `/var/run/docker.sock` missing on this host
- Regression report path: default still `agent_docs/reports/regression_test_voice.md` in tests/. Image creates writable `/app/agent_docs/reports`. Prefer mount `-v "$PWD/agent_docs/reports:/app/agent_docs/reports"`. Optional: Tester adds `REGRESSION_REPORT_PATH` env read in `tests/regression/…` (Coder cannot edit `tests/`).
- Build / run (for Tester):

```bash
docker build --target runtime -t transcriber:runtime .
docker build --target test -t transcriber:test .

# secrets: copy from .env.example template only; never bake into image
HOST_SECRETS=/path/to/secrets.env   # JOB_IP_SALT + demo LLM key

docker run --rm -p 8000:8000 \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v "$HOST_SECRETS:/run/secrets/transcriber.env:ro" \
  -v transcriber-var:/var/transcriber \
  -v transcriber-hf-cache:/home/app/.cache \
  transcriber:runtime
# GET http://127.0.0.1:8000/healthz

docker run --rm --cpus=2 --memory=8g \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v "$HOST_SECRETS:/run/secrets/transcriber.env:ro" \
  -v "$PWD/agent_docs/reports:/app/agent_docs/reports" \
  -v "$PWD/agent_docs/reports/d5:/out" \
  transcriber:test

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

- Next: @Tester `agent_docs/instructions/tester_D5.md`

## 2026-09-07 — Tester (Phase 0 prep)
- STATUS: PHASE0_DONE — waiting for Coder READY_FOR_TEST
- Docker: Client+Server 29.7.2 OK
- Inputs: `data/test_voice.m4a` present; `models/silero_vad.onnx` present
- Audio source: `data/voice 002.m4a` (space in name; `data/voice_002/` is transcript-only)
- Trim: `var/bench/d5/voice_002_15min.m4a` (~900 s, ffmpeg -c copy)
- Host secrets: `var/secrets/transcriber.env` (gitignored); key names present: JOB_IP_SALT, HF_TOKEN, GEMINI_API_KEY, NVIDIA_API_KEY, QWEN_API_KEY (values not logged)
- Note: Dockerfile / .dockerignore not yet on disk — Phase 1–2 blocked until READY_FOR_TEST

## 2026-09-07 — Tester restart
- Previous tester stuck PHASE0_DONE waiting; no Phase1 progress
- Relaunched Tester for build + G5 (docker.sock requires non-sandbox)

## 2026-09-07 — Tester (Phase 1–2)
- STATUS: TEST_PASS
- Phase 1: runtime+test images build OK; CTX test_voice present; pytest final 84 passed / 3 skipped; healthz 200 with secrets mount; no secret values in logs
- Test fixes (container path/env only): `tests/unit/test_health.py`, `tests/unit/test_llm_config.py` — then rebuilt `transcriber:test`
- Phase 2 G5: `bench_d5.py --mode b` on 15min slice under `--cpus=2 --memory=8g` → exit 0; wall 784.7s; peak_rss 2183.9 MB; no OOM
- Reports: `agent_docs/reports/d5/{build_test.md,g5_15min.md,g5_15min.json,gate_D5.md}`
- Verdict: PASS (stage RSS null WARN only; mode a control not run)

## 2026-09-07 — Planner
- STATUS: TEST_PASS — await HUMAN_GATE
- Gate: `agent_docs/reports/d5/gate_D5.md` PASS (G5.1–G5.4)
- Headline: 15 min @ 2CPU/8g → wall ~785s, peak RSS ~2.13 GiB, no OOM; in-container pytest 84 passed
- Next: human sign-off → merge; then D5.1 (GitHub Actions)

## 2026-09-10 — Planner (D5.TTFT-diar research)
- STATUS: HANDOFF
- Branch: `cursor/d5-ttft-diar`
- Pack: `cloud_in/` clips 01–03 + apartments/ninth wav; no gold; research AGENTS
- Local gold: `eval/d5_diar/gold/clip0{1,2,3}.json` human_ok (A/B/C/D legend)
- Out of cloud: H0 warmup, S2 split+anchor prod, Jina

## 2026-09-10 — Cloud (D5.diar-spectral research)
- STATUS: REPORT
- Branch: `cursor/d5-diar-spectral`
- No production src/config edits; no PR
- M1 spectral+eigengap: clip01 [42,45] is a non-top1 cluster (41.3s / 15.3s); apartments 3 ids 0 crumbs; ninth loses the ~3.8s third id that AHC 0.85 keeps
- M2 block-hybrid oversplits; M2_local ≈ AHC 0.85; M3 collapses clip01 to 1 id
- Timing: first-process model_load 2.089s; repeat 0.184s; 5min embed pass1/pass2 11.596 / 11.567s (366 windows); cluster ≪ 0.3s
- Artifacts: `cloud_out/{report.md,results.json,run_meta.json,timelines/,scratch/}`
