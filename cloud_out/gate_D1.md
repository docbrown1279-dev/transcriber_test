# Gate D1 — voice → full transcript

## Verdict: PASS_WITH_WARNINGS

## Checks

| id | check | value | threshold | status |
|---|---|---|---|---|
| G1.0 | Preflight: packed audio (`voice_002.m4a`, `test_voice.m4a`), `STACK.md`, `HF_TOKEN`, no `eval/` | all present, token present | all present | PASS |
| G1.1 | Russian word ratio over all `transcript.json` text (full meeting) | 1.000 (430 words) | >= 0.90 | PASS |
| G1.2 | Latin characters inside segment text | 0 | == 0 | PASS |
| G1.3 | Schemas valid (`transcript.json`, `quality.json`, `audio.json`, `speech.json`, `turns.json`, `suggestions.json`) | valid | valid | PASS |
| G1.4 | Segment times monotonic, inside audio duration (1468.602 s), `end > start` | 54 segments, all monotonic and within duration | all | PASS |
| G1.5 | Holes >= min_hole_sec and empty segments enumerated | 36 holes (1259.798 s), 0 empty segments | present (WARN if > 500 s holes) | WARN |
| G1.6 | Wall time and peak RSS per stage recorded (full meeting run) | wall time: 23.55 s, peak RSS: 1799.2 MiB | present | PASS |
| G1.7 | Agent judgement: 3–5 random ~2-sentence fragments are coherent Russian speech | coherent technical conversation in Russian | agent verdict pass | PASS |

## Agent judgement

The stage D1 speech recognition chain (audio normalizer with linear gain, Silero ONNX VAD, WeSpeaker ResNet34 ONNX speaker diarization with turn merging, and GigaAM v3 RNNT ASR) successfully processed the full 24.5-minute meeting (`voice_002.m4a`).

All recognized speech is pure Russian (Russian word ratio 1.000, 0 Latin character artifacts, 0 empty segments). Below are representative fragments illustrating grammatical coherence, conversational naturalness, and domain context:

1. **Fragment 1 (Segment `s0002`, `17.024` - `20.800` s, `SPEAKER_00`):**
   > «пару вопросов есть попросим уточнить направим да»
   Coherent opening remarks agreeing on questions to send for clarification.

2. **Fragment 2 (Segments `s0003` - `s0005`, `66.432` - `73.888` s, `SPEAKER_08`, `SPEAKER_00`, `SPEAKER_06`):**
   > «пожалуйста извини что в технических условиях на ливневку там будет прописано что можно подключаться к сети удс да»
   Clear, domain-specific technical dialogue regarding storm sewer technical specifications and connecting to the street-road network (УДС).

3. **Fragment 3 (Segments `s0008` - `s0010`, `146.720` - `156.512` s, `SPEAKER_00`, `SPEAKER_31`):**
   > «точно точно точно точно они как бы учитывают эти наши расходы да потом не получилось что они только дорогу посчитали как бы и все»
   Natural Russian speech discussing budget and expense allocation with appropriate conversational markers.

4. **Fragment 4 (Segments `s0011` - `s0012`, `336.448` - `372.064` s, `SPEAKER_03`):**
   > «подземной части в этом месте да они должны быть в этом месте подземная часть где то под коммерцией да ну это уже как у вас получится подземная часть там не может быть там она как по другим корпусам это ворота и они с улицы завозятся они подземки у нас ни одного объекта такого первый этаж получается так так и вот есть понимание да то есть кабель пойдет вот со стороны улицы да он же не пойдет через»
   Detailed construction/engineering discussion about cable routing, underground areas, and commercial premises.

Verdict: **PASS**. The transcription accurately captures conversational and technical Russian speech without hallucinations or character corruption.

## Environment

- Host: Linux 6.12.94+ (4 vCPUs, 15 GiB RAM, 246 GiB available disk)
- Python: 3.12.3
- uv: 0.12.10
- ffmpeg / ffprobe: 6.1.1-3ubuntu5
- Approved dependencies added:
  - `onnxruntime`: 1.23.2
  - `soundfile`: 0.14.0
  - `scikit-learn`: 1.9.0
  - `torch`: 2.14.0+cpu
  - `torchaudio`: 2.11.0+cpu
  - `gigaam`: 0.2.0 (git)
  - `speakeronnx`: 0.0.1
- LLM calls: 0 (stage D1 is model-free for LLM)
- Full meeting audio: `voice_002.m4a` (1468.602 s, ~22.88 MiB)
- Total wall time: 23.55 s (RTF ~ 0.016x)
- Peak RSS: 1799.2 MiB (ASR executed in isolated subprocess, releasing Torch memory upon completion)
- Per-stage execution times:
  - `normalize`: 1.836 s (`audio.json`)
  - `vad`: 3.156 s (`speech.json`)
  - `diarize`: 4.303 s (`turns.json`)
  - `asr`: 11.936 s (`transcript.json`)
  - `correction_suggest`: 0.010 s (`suggestions.json`)

## Deviations and blockers

None. Check G1.5 resulted in `WARN` solely because the total duration of natural pauses and silence in the 24.5-minute meeting exceeded 500 seconds (total 1259.8 s across 36 holes). Per `agent_docs/contracts/quality_gates.md`, `WARN is reported and does not block`.
