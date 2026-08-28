# Environment — Stage 1

On **unattended Stage 1** runs the agent may install these without further human approval. Prefer the starter set; record exact versions in `results/reports/notes.md`.

## System packages (typical Ubuntu)

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg build-essential git
```

Optional for whisper.cpp / llama.cpp builds: `cmake`, `pkg-config`.

## Python (3.10+ recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
```

### Proposed Stage 1 packages

| Area | Packages | Notes |
|---|---|---|
| ASR | `faster-whisper` | Primary ASR |
| Metrics | `pymorphy3`, `pymorphy3-dicts-ru` | Russian word ratio / morphology |
| Audio I/O | already via ffmpeg + faster-whisper | Keep extras minimal |
| Embeddings | `sentence-transformers` | Pull BGE-M3 / E5 when needed |
| Denoise | DeepFilterNet / RNNoise as researched | Install only the tools you actually run |
| LLM | Ollama **or** llama.cpp | Prefer one runtime first |

Suggested starter `pip` line:

```text
faster-whisper
pymorphy3
pymorphy3-dicts-ru
sentence-transformers
```

Optional: write a `requirements-stage1.txt` with pinned versions after a successful run (for reproducibility).

## Models (download on demand)

| Model | Used for | Size (order of magnitude) |
|---|---|---|
| Whisper `medium` / `large-v3` | ASR | ~1.5–3 GB |
| BGE-M3 or E5 (small/base) | Chunking | hundreds of MB–GB |
| Qwen2.5-7B-Instruct (GGUF Q4/Q5) | Summary | ~4–5 GB quantized |

Ensure free disk before download. Cache under standard HF / Ollama paths; note paths in `notes.md`.

### Hugging Face auth

Use the project HF token when Hub downloads need auth or hit anonymous rate limits:

```bash
export HF_TOKEN="…"   # or HUGGING_FACE_HUB_TOKEN
# huggingface-cli login --token "$HF_TOKEN"   # optional
```

In Python, `huggingface_hub` picks up `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` automatically. Do not write the token into scripts or git.

## Credentials & APIs

Provide secrets via environment / Cursor cloud secrets — **never** commit them.

| Variable (preferred) | Also accepted | Purpose |
|---|---|---|
| `HF_TOKEN` | `HUGGING_FACE_HUB_TOKEN` | Download models from Hugging Face |
| `GEMINI_API_KEY` | `GOOGLE_API_KEY` | Google Gemini API |
| `NVIDIA_API_KEY` | — | NVIDIA API / NIM |

### API usage policy

1. **Local first** for ASR, denoise, embeddings, and summary.
2. **Gemini / NVIDIA** only as fallback when local cannot finish with acceptable quality or would take too long.
3. Respect **daily quotas** — few short calls; cache results; avoid retries loops against paid/limited APIs.
4. Scripts may call these APIs via env vars; never hardcode keys; never print keys in logs or reports.

If a required env var is missing, ask the human or mark that path `skipped` in the report.

## Layout

```
data/fixtures/     # input samples (meeting_sample.m4a)
data/raw/          # additional raw audio
data/processed/    # denoised / converted wav
results/asr/       # transcripts + timestamps
results/denoise/   # denoise A/B artifacts
results/chunking/  # chunk boundaries / titles
results/llm/       # summaries
results/reports/   # research_report.json, notes.md
scripts/           # helper scripts created during research
```

## Cloud agent notes

- Prefer writing scripts into the repo so the next agent can reuse them.
- Large models may exceed default disk — check `df -h` first.
- If network/model download is blocked, document blockers in `notes.md` and mark blocks `skipped`.
