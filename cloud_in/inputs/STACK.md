# Frozen notes for D5.TTFT-diar (research pack)

| Layer | Use | Do not use |
|---|---|---|
| Diarization | WeSpeaker ONNX, settings from `config/base.yaml` `diarization.embed` | pyannote, sherpa bakeoff |
| VAD | existing Silero path if diarize requires speech mask | reinvent VAD |
| ASR / LLM / chunking | off | any |
| Jina / packing D | off | any |

Baseline embed (today): `window_sec=1.5`, `step_sec=0.75`, `cluster_distance_threshold=0.85`.
