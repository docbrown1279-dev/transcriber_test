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

### Proposed Stage 1b packages

| Area | Packages | Notes |
|---|---|---|
| ASR | `whisperx` (preferred), else `faster-whisper` | large-v3 |
| Diarization | WhisperX built-in / `pyannote.audio` | Gated; needs `HF_TOKEN` + license accept on Hub |
| Metrics | `pymorphy3`, `pymorphy3-dicts-ru` | Telemetry only |
| Denoise | DeepFilterNet, RNNoise | Only if meaning check fails; **not** ffmpeg afftdn |
| Meaning LLM | `llama-cpp-python` + Qwen3-8B GGUF | Q5_K_M preferred |

Install only what the current stack needs. Do not install embedding/summary extras in 1b.

Suggested starter (WhisperX path):

```text
whisperx
pymorphy3
pymorphy3-dicts-ru
llama-cpp-python
```

Optional: write a `requirements-stage1.txt` with pinned versions after a successful run (for reproducibility).

## Models (download on demand)

| Model | Used for | Size (order of magnitude) |
|---|---|---|
| Whisper `large-v3` (WhisperX / faster-whisper) | ASR | ~3 GB |
| `pyannote/speaker-diarization-3.1` | Speakers | ~hundreds of MB; **gated** |
| Qwen3-8B Instruct GGUF Q5_K_M | Meaning check | ~5–6 GB |
| DeepFilterNet / RNNoise weights | Denoise if needed | hundreds of MB |

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

### API usage policy (Stage 1b)

1. **No cloud ASR.** Do not upload audio.
2. Meaning check is **Qwen3-8B local**. Gemini/NVIDIA only if that model cannot run: **≤1** text-only clip review.
3. Never hardcode or print keys.

If `HF_TOKEN` is missing, diarization will likely fail — document `failure_kind: auth` and still try WhisperX/fw without speakers, then stop that branch.

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

### Cloud Agent network access

Repository files cannot change the Cloud Agent egress policy. Before starting a
new agent, configure **Cursor Dashboard → Cloud Agents → Security → Network
access**. For this isolated research environment, prefer **Allow all** during
Stage 1 if available. Otherwise use `Default + allowlist` with:

```text
# Hugging Face Hub, LFS and Xet
huggingface.co
*.huggingface.co
hf.co
*.hf.co
*.xethub.hf.co

# Python and PyTorch packages
pypi.org
files.pythonhosted.org
download.pytorch.org

# Official OpenAI Whisper checkpoints (non-HF fallback)
openaipublic.azureedge.net

# GitHub source/releases
github.com
api.github.com
raw.githubusercontent.com
codeload.github.com
objects.githubusercontent.com
github-releases.githubusercontent.com

# Local LLM runtimes/models
ollama.com
*.ollama.com
*.ollama.ai

# Optional text-only API fallback
generativelanguage.googleapis.com
integrate.api.nvidia.com
api.nvcf.nvidia.com

# Ubuntu system packages
archive.ubuntu.com
security.ubuntu.com
```

Apply policy changes by creating a **new Cloud Agent run**. Secrets such as
`HF_TOKEN` do not bypass DNS, TLS, or egress restrictions.

### ASR download fallback order

1. `faster-whisper medium` from the public Hugging Face repository.
2. If Hugging Face fails at DNS/TLS before HTTP, do not try another model on the
   same host. Use one local `openai-whisper medium` attempt; its official
   checkpoint comes from `openaipublic.azureedge.net`.
3. Do not use unofficial model mirrors and do not upload audio to an API.
4. If both transports fail (or the official CPU run is impractical), report the
   blocker and finish a partial report.
