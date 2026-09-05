
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
    def complete(self, prompt: str, *, max_tokens: int, temperature: float) -> LlmResponse: ...

class Exporter(Protocol):
    name: str
    def export(self, report: ReportArtifact, dest: Path) -> Path: ...
```

`LlmResponse` carries `text`, `provider`, `model`, `prompt_id`, `tokens_in`, `tokens_out`,
`runtime_sec`, so every artifact can record provenance without the caller knowing the provider.

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
| `llm` | `gemini` | demo, dev | implemented — the only provider used in the cloud |
| `llm` | `local_llama` | dev, prod | implemented at stage D3 (llama.cpp, Qwen3-8B Q5), local runs only |
| `llm` | `openai_compat` | dev, prod | stub — no key is provisioned for the cloud (`QWEN_API_KEY` stays local) |
| `export` | `json`, `markdown` | demo, dev, prod | implemented |
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

## 5. Prompts

Prompts live in `src/transcriber/llm/prompts/{prompt_id}.md` and are addressed by `prompt_id`
recorded in artifacts. Frozen ids for the demo:

| `prompt_id` | Purpose | Origin |
|---|---|---|
| `title_p1_v1` | chapter title + points in one call, `<= 10` words, noun phrase | stage 3, prompt P1 |
| `extract_v1` | key_points / actions / open_questions / asr_notes with `src` | stage 3c extract |
| `report_v1` | meeting summary + 5–12 key moments from merged insights, one call | stage 3b/3c report |

Changing a prompt means a new `prompt_id`, never an in-place edit of a frozen one, so artifacts
stay traceable. Prompts must not contain gold answers or examples taken from `eval/`.

The same `prompt_id` must run against both `gemini` (cloud gate) and `local_llama` (local human
gate) without edits — provider-specific wording lives in the client, not in the prompt file.

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
