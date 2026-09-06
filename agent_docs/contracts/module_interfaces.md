
# Contract: module interfaces (ports) and stub policy

Draft, Phase A. Every swappable component is a `Protocol` in `src/transcriber/<area>/base.py`
and is instantiated by a registry keyed with the config value from `config/{profile}.yaml`.
Pipeline code depends on the protocol only — never on a concrete class and never on the profile
name.

## 1. Ports

```python
class AudioNormalizer(Protocol):
    def normalize(self, source: Path, dest: Path, cfg: AudioConfig) -> AudioArtifact: ...

class VoiceActivityDetector(Protocol):
    name: str
    def detect(self, wav: Path, cfg: VadConfig) -> SpeechArtifact: ...

class Diarizer(Protocol):
    name: str
    def diarize(self, wav: Path, speech: SpeechArtifact, cfg: DiarizationConfig) -> TurnsArtifact: ...

class AsrEngine(Protocol):
    name: str
    def transcribe(self, wav: Path, turns: TurnsArtifact, cfg: AsrConfig) -> TranscriptArtifact: ...

class TermSuggester(Protocol):
    name: str
    def suggest(self, transcript: TranscriptArtifact, cfg: CorrectionConfig) -> SuggestionsArtifact: ...

class EmbeddingBackend(Protocol):
    name: str
    def encode(self, texts: Sequence[str]) -> np.ndarray: ...

class Chunker(Protocol):
    name: str
    def chunk(self, transcript: TranscriptArtifact, embedder: EmbeddingBackend,
              cfg: ChunkingConfig) -> ChaptersArtifact: ...

class LlmClient(Protocol):
    name: str
    def complete(
        self,
        prompt: str,
        *,
        prompt_id: str,
        max_tokens: int | None,
        temperature: float | None,
        json_schema: dict | None,
        extra: dict[str, object] | None = None,
    ) -> LlmResponse: ...

class Exporter(Protocol):
    name: str
    def export(self, report: ReportArtifact, dest: Path) -> Path: ...
```

`LlmResponse` carries `text`, `provider`, `model`, `prompt_id`, `tokens_in`, `tokens_out`,
`runtime_sec`, so every artifact can record provenance without the caller knowing the provider.

Clients are a thin transport. They do not choose prompt files. `json_schema` is loaded from
`llm.tasks.*.schema`. `temperature`/`max_tokens` of `None` are omitted from the API call.
Factory: `make_client` from `llm.backends[llm.backend]` (`base_url` included). Unique
client keys come from that backend’s `extra_config` (or `null`). Layout:
`agent_docs/plans/draft_llm_wrapper.md`.

## 2. Registry

```python
REGISTRY: dict[str, dict[str, Callable[[], object]]]  # area -> component key -> factory
```

- `build(area, key)` raises `UnknownComponentError` for an unregistered key (typo in config).
- Components not available in the active profile raise `ComponentUnavailableError` with
  `component`, `profile` and a `hint` naming the profile that enables them.
- The registry is the contract tested in D0: for every area the expected keys exist and every
  `prod`-only key raises `ComponentUnavailableError` — not `NotImplementedError`, not a silent
  fallback to a different component.

## 3. Components by area

| Area | Key | Profile | Status in demo |
|---|---|---|---|
| `vad` | `silero` | demo, dev, prod | implemented |
| `vad` | `ten_fallback` | dev, prod | implemented, disabled by default (Agora non-compete clause) |
| `vad` | `disabled` | dev | implemented (pass-through single region) |
| `diarization` | `wespeaker_onnx` | demo, dev, prod | implemented |
| `diarization` | `pyannote31` | dev, prod | stub |
| `asr` | `gigaam_v3_rnnt` | demo, dev, prod | implemented |
| `asr` | `gigaam_e2e_rnnt` | dev | stub |
| `correction` | `dictionary_suggest` | demo, dev, prod | implemented, empty base dictionary |
| `correction` | `domain_dictionaries` | prod | stub |
| `embeddings` | `rubert_tiny2` | demo, dev, prod | implemented |
| `embeddings` | `bge_small_onnx` | dev, prod | stub |
| `embeddings` | `jina_v3` | dev, prod | stub |
| `chunking` | `packing_c` | demo, dev, prod | implemented |
| `chunking` | `late_chunking_jina` | dev, prod | stub |
| `chunking` | `hybrid_c_then_d` | dev | stub |
| `llm` | `gemini` | demo, dev, prod | implemented — default `llm.backend` for demo/cloud |
| `llm` | `openai_compat` | demo, dev, prod | implemented at D3 — NVIDIA/Qwen API (`api_key_env` + `base_url` on the backend) |
| `llm` | `local_llama` | dev, prod | stub until `llm.mode: local` is enabled (not demo D3) |
| `export` | `json`, `markdown` | demo, dev, prod | implemented at D3 (`report.json` + `report.md` renderer; no LLM) |
| `export` | `pdf` | prod | stub |

## 4. Pipeline steps

```python
class PipelineStep(Protocol):
    stage: str                      # "normalize" | "vad" | … | "report"
    produces: str                   # artifact filename
    requires: tuple[str, ...]       # artifact filenames
    def run(self, ctx: JobContext, cfg: AppConfig) -> Path: ...
```

Rules:

- A step is skipped when `produces` already exists and is valid — this makes a job resumable
  without re-running ASR, and lets D2–D4 run on fixture artifacts.
- Steps emit `StageEvent(stage, status, pct, message)` through `ctx.events`; the web layer only
  reads events, it never calls a step directly.
- Heavy runtimes are isolated: the ASR step runs in a subprocess so CPU torch memory is released
  when the stage ends. VAD and diarization (ONNX, no torch) may share the worker process.

## 5. Prompts and schemas

Copied from `agent_docs/contracts/llm/` into the package:

```text
src/transcriber/llm/prompts/<purpose>/<version>.md
src/transcriber/llm/schemas/<name>.json
```

`config/base_llm.yaml` points at those paths (`llm.tasks.chapter_titles`,
`llm.tasks.meeting_insights.extract` / `report`). Artifacts record
the prompt path (or a stable id derived from it, e.g. `meeting_insights/v1_extract`). D3
extract/report use `{{placeholders}}`; leftover braces after render are an error.

Frozen demo files:

| Path | Purpose | Origin |
|---|---|---|
| `prompts/chapter_titles/v1.md` | chapter title, `<= 10` words | stage 3 P1 (`title_p1_v1`) |
| `prompts/meeting_insights/v1_extract.md` | per-chapter extract | stage 3c |
| `prompts/meeting_insights/v1_report.md` | one-shot report | stage 3b/3c |
| `schemas/chapter_title.json` | title object | D2 Gemini schema |
| `schemas/chapter_extract.json` | extract object | D3 |
| `schemas/meeting_report.json` | report object | D3 |

Change a prompt by adding a new versioned file and switching the yaml path. Do not edit a frozen
file in place. Prompts contain no gold / `eval/` examples. The same prompt file runs on every
API backend. The model never emits `start` / `end` / speaker.

## 5.1 `base_llm` (config, not code)

One file `config/base_llm.yaml` (example: `agent_docs/contracts/llm/base_llm.yaml`). No per-model
preset files. `llm.mode` is `api` or `local` (`local` unused in demo). `llm.backend` selects
`gemini` | `nvidia` | `qwen`. Each backend has `base_url` (`null` for native Gemini). Unique
client-only keys: `extra_config` on the backend or `null`. Tasks have no `extra_config`.

## 6. Quality checks as a library

`src/transcriber/quality/` exposes the gate logic used by both tests and CLI:

```python
def russian_word_ratio(segments: Sequence[Segment]) -> RatioResult: ...
def chapter_metrics(chapters: ChaptersArtifact, audio_sec: float) -> ChapterMetrics: ...
def clock_gate(insights: InsightsArtifact, chapters: ChaptersArtifact) -> ClockGateResult: ...
def check_report(report: ReportArtifact, insights: InsightsArtifact) -> CheckReport: ...
```

Gates are code, not one-off scripts inside a cloud run: `python -m transcriber.quality check-…`
must reproduce the same verdict locally.
