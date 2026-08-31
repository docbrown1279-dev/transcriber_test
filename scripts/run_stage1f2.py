#!/usr/bin/env python3
"""Stage 1f2: three VADs, then three ONNX embedders on frozen Silero cuts.

Clustering is imported unchanged from run_stage1f.py. Threads default to 2
to approximate the 2 vCPU / 8 GiB demo box. Do not overwrite results/asr/1f/.
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")

import argparse
import gc
import json
import resource
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_stage1f import (  # noqa: E402
    SileroVadOnnx,
    assemble_turns,
    cluster_embeddings,
    speech_timestamps,
    windows_for_segment,
)
from run_stage1e import holes, merge_turns, run as run_cmd  # noqa: E402

CLIPS = [
    ("test_voice", ROOT / "data/test_voice.m4a", 83.0),
    ("test_apartments", ROOT / "data/test_apartments.m4a", 85.0),
    ("test_transformers", ROOT / "data/test_transformers.m4a", 85.0),
    ("test_ninth", ROOT / "data/test_ninth.m4a", 85.0),
]
OUT = ROOT / "results" / "asr" / "1f2"
REPORTS = ROOT / "results" / "reports" / "1f2"
EXTRACTS = OUT / "_extracts"
MODELS = ROOT / "models"
BASE_TURNS = ROOT / "results/reports/1f/baseline/pyannote31"
NUM_THREADS = 2
FRAME = 0.01
GAP_MERGE_SEC = 0.3
SILERO_VAD_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
)
ERES2NET_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
)
TITANET_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-recongition-models/nemo_en_titanet_small.onnx"
)
VOICE_WINDOWS = [(0.0, 10.0), (75.0, 83.0)]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def peak_rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)


def torch_loaded() -> bool:
    return "torch" in sys.modules


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "stage1f2-research"})
    with urllib.request.urlopen(request, timeout=180) as response, tmp.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    tmp.replace(dest)
    return dest


def require_clips_and_baseline() -> None:
    missing = [str(path.relative_to(ROOT)) for _, path, _ in CLIPS if not path.is_file()]
    if missing:
        write_json(REPORTS / "failure.json", {"failure_kind": "missing_fixture", "missing": missing})
        raise SystemExit(f"failure_kind: missing_fixture ({missing})")
    if not BASE_TURNS.is_dir():
        write_json(
            REPORTS / "failure.json",
            {"failure_kind": "missing_baseline", "turns": str(BASE_TURNS)},
        )
        raise SystemExit("failure_kind: missing_baseline")
    for clip_id, _, _ in CLIPS:
        if not (BASE_TURNS / f"{clip_id}.json").is_file():
            write_json(
                REPORTS / "failure.json",
                {"failure_kind": "missing_baseline", "clip": clip_id},
            )
            raise SystemExit(f"failure_kind: missing_baseline ({clip_id} turns)")


def wav16k(source: Path, destination: Path) -> np.ndarray:
    import soundfile as sf

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not (destination.is_file() and destination.stat().st_size > 0):
        run_cmd(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ]
        )
    audio, rate = sf.read(destination, dtype="float32")
    if rate != 16000:
        raise RuntimeError(f"expected 16 kHz, got {rate} for {destination}")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio.astype(np.float32)


def prepare_wavs() -> dict[str, tuple[np.ndarray, Path]]:
    prepared: dict[str, tuple[np.ndarray, Path]] = {}
    for clip_id, audio, _duration in CLIPS:
        dest = EXTRACTS / "16k" / f"{clip_id}.16k.wav"
        prepared[clip_id] = (wav16k(audio, dest), dest)
    return prepared


def merge_speech_gaps(regions: list[dict[str, float]], gap: float = GAP_MERGE_SEC) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for region in sorted(regions, key=lambda item: (item["start"], item["end"])):
        start = float(region["start"])
        end = float(region["end"])
        if end <= start:
            continue
        if rows and start - rows[-1]["end"] <= gap + 1e-9:
            rows[-1]["end"] = max(rows[-1]["end"], end)
        else:
            rows.append({"start": start, "end": end})
    return [{"start": round(row["start"], 6), "end": round(row["end"], 6)} for row in rows]


def as_speech_turns(regions: list[dict[str, float]]) -> list[dict[str, Any]]:
    return [
        {"start": row["start"], "end": row["end"], "speaker": "SPEECH"}
        for row in regions
        if row["end"] > row["start"]
    ]


def pyannote_regions(clip_id: str) -> list[dict[str, float]]:
    payload = json.loads((BASE_TURNS / f"{clip_id}.json").read_text(encoding="utf-8"))
    return merge_speech_gaps(
        [{"start": float(row["start"]), "end": float(row["end"])} for row in payload["merged_turns"]]
    )


def speech_mask(regions: list[dict[str, float]], duration: float) -> np.ndarray:
    n = int(round(duration / FRAME))
    out = np.zeros(n, dtype=bool)
    for row in regions:
        a = max(0, int(row["start"] / FRAME))
        b = min(n, int(row["end"] / FRAME))
        if b > a:
            out[a:b] = True
    return out


def iou(a: np.ndarray, b: np.ndarray) -> float | None:
    inter = int(np.logical_and(a, b).sum())
    union = int(np.logical_or(a, b).sum())
    if union == 0:
        return None
    return round(inter / union, 4)


def seconds(mask: np.ndarray) -> float:
    return round(float(mask.sum()) * FRAME, 3)


def exclusive_seconds(this: np.ndarray, others: list[np.ndarray]) -> float:
    if not others:
        return seconds(this)
    other_any = others[0].copy()
    for mask in others[1:]:
        other_any = np.logical_or(other_any, mask)
    return seconds(np.logical_and(this, np.logical_not(other_any)))


def window_cover(regions: list[dict[str, float]], start: float, end: float) -> dict[str, Any]:
    intervals = []
    covered = 0.0
    for row in regions:
        a = max(float(row["start"]), start)
        b = min(float(row["end"]), end)
        if b > a:
            intervals.append({"start": round(a, 6), "end": round(b, 6)})
            covered += b - a
    return {
        "speech_sec": round(covered, 3),
        "covered": covered > 0,
        "intervals": intervals,
    }


def write_vad_clip(
    vad_id: str,
    clip_id: str,
    audio: Path,
    duration: float,
    regions: list[dict[str, float]],
    *,
    model: str,
    provider: str,
    runtime_sec: float,
    extra: dict[str, Any] | None = None,
) -> None:
    turns = as_speech_turns(regions)
    payload = {
        "audio": str(audio.relative_to(ROOT)),
        "duration_sec": duration,
        "vad_id": vad_id,
        "model": model,
        "provider": provider,
        "execution_mode": "local",
        "torch": torch_loaded(),
        "runtime_sec": round(runtime_sec, 3),
        "peak_rss_mb": peak_rss_mb(),
        "n_speech_regions": len(regions),
        "speech_regions": regions,
        "raw_turns": turns,
        "merged_turns": turns,
        "holes_ge_0_5_sec": holes(turns, duration),
        "num_threads": NUM_THREADS,
    }
    if extra:
        payload.update(extra)
    write_json(OUT / vad_id / f"{clip_id}.json", payload)


def mark_skipped(kind: str, item_id: str, failure_kind: str, note: str) -> None:
    write_json(
        OUT / item_id / "_run.json",
        {
            f"{kind}_id": item_id,
            "status": "skipped",
            "failure_kind": failure_kind,
            "torch": torch_loaded(),
            "note": note,
        },
    )


def run_silero(wavs: dict[str, tuple[np.ndarray, Path]]) -> bool:
    vad_id = "silero"
    vad = None
    try:
        vad_path = download(SILERO_VAD_URL, MODELS / "silero_vad.onnx")
        vad = SileroVadOnnx(vad_path)
    except Exception as exc:
        mark_skipped("vad", vad_id, "install", f"Silero VAD ONNX failed: {type(exc).__name__}: {exc}")
        return False
    started = time.monotonic()
    dest_dir = OUT / vad_id
    try:
        for clip_id, audio, duration in CLIPS:
            samples, _wav = wavs[clip_id]
            clip_started = time.monotonic()
            regions = merge_speech_gaps(speech_timestamps(samples, vad))
            write_vad_clip(
                vad_id,
                clip_id,
                audio,
                duration,
                regions,
                model="silero-vad-onnx",
                provider="onnxruntime",
                runtime_sec=time.monotonic() - clip_started,
                extra={"vad_model": str(vad_path.relative_to(ROOT))},
            )
        write_json(
            dest_dir / "_run.json",
            {
                "vad_id": vad_id,
                "status": "success",
                "failure_kind": "none",
                "torch": torch_loaded(),
                "runtime_sec": round(time.monotonic() - started, 3),
                "peak_rss_mb": peak_rss_mb(),
                "model": str((MODELS / "silero_vad.onnx").relative_to(ROOT)),
            },
        )
        return True
    except Exception as exc:
        mark_skipped("vad", vad_id, "runtime", f"{type(exc).__name__}: {exc}")
        return False
    finally:
        if vad is not None:
            del vad
        gc.collect()


def ten_flags_to_regions(flags: list[int], hop: int, duration: float) -> list[dict[str, float]]:
    hop_sec = hop / 16000.0
    regions: list[dict[str, float]] = []
    start: int | None = None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            regions.append({"start": start * hop_sec, "end": index * hop_sec})
            start = None
    if start is not None:
        regions.append({"start": start * hop_sec, "end": min(len(flags) * hop_sec, duration)})
    return merge_speech_gaps(regions)


def run_ten_vad(wavs: dict[str, tuple[np.ndarray, Path]]) -> bool:
    vad_id = "ten_vad"
    hop = 256
    vad = None
    try:
        from ten_vad import TenVad

        vad = TenVad(hop_size=hop, threshold=0.5)
    except Exception as exc:
        mark_skipped("vad", vad_id, "install", f"ten-vad failed: {type(exc).__name__}: {exc}")
        return False
    started = time.monotonic()
    try:
        for clip_id, audio, duration in CLIPS:
            samples, _wav = wavs[clip_id]
            clip_started = time.monotonic()
            pcm = np.clip(np.asarray(samples) * 32768.0, -32768, 32767).astype(np.int16)
            flags: list[int] = []
            n_full = len(pcm) // hop
            for index in range(n_full):
                frame = pcm[index * hop : (index + 1) * hop]
                _prob, flag = vad.process(frame)
                flags.append(int(flag))
            if len(pcm) % hop:
                tail = np.zeros(hop, dtype=np.int16)
                leftover = pcm[n_full * hop :]
                tail[: len(leftover)] = leftover
                _prob, flag = vad.process(tail)
                flags.append(int(flag))
            regions = ten_flags_to_regions(flags, hop, duration)
            write_vad_clip(
                vad_id,
                clip_id,
                audio,
                duration,
                regions,
                model="ten-vad 1.0.6.8",
                provider="ten-vad",
                runtime_sec=time.monotonic() - clip_started,
                extra={"hop_size": hop, "threshold": 0.5},
            )
        write_json(
            OUT / vad_id / "_run.json",
            {
                "vad_id": vad_id,
                "status": "success",
                "failure_kind": "none",
                "torch": torch_loaded(),
                "runtime_sec": round(time.monotonic() - started, 3),
                "peak_rss_mb": peak_rss_mb(),
                "license_note": "Apache-2.0 with Agora non-compete (TEN-framework/ten-vad LICENSE).",
            },
        )
        return True
    except Exception as exc:
        mark_skipped("vad", vad_id, "runtime", f"{type(exc).__name__}: {exc}")
        return False
    finally:
        if vad is not None:
            del vad
        gc.collect()


def prepare_fsmn_dir() -> Path:
    src = MODELS / "fsmn-vad-onnx"
    dest = MODELS / "fsmn-vad-onnx-funasr"
    dest.mkdir(parents=True, exist_ok=True)
    onnx_src = src / "model.onnx"
    if not onnx_src.is_file():
        raise FileNotFoundError(f"missing {onnx_src}")
    shutil.copy2(onnx_src, dest / "model.onnx")
    shutil.copy2(src / "vad.mvn", dest / "am.mvn")
    raw = yaml.safe_load((src / "vad.yaml").read_text(encoding="utf-8"))
    if "model_conf" not in raw and "vad_post_conf" in raw:
        raw["model_conf"] = raw["vad_post_conf"]
    (dest / "config.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dest


def parse_fsmn_segments(raw: Any, duration: float) -> list[dict[str, float]]:
    if raw in ("", None):
        return []
    items = raw
    if isinstance(raw, list) and raw and isinstance(raw[0], list) and raw[0] and isinstance(raw[0][0], (list, tuple)):
        items = raw[0]
    regions: list[dict[str, float]] = []
    for item in items or []:
        if isinstance(item, dict):
            start, end = float(item["start"]), float(item["end"])
        else:
            start, end = float(item[0]), float(item[1])
        if max(start, end) > duration * 2:
            start, end = start / 1000.0, end / 1000.0
        start = min(max(0.0, start), duration)
        end = min(max(start, end), duration)
        if end > start:
            regions.append({"start": start, "end": end})
    return merge_speech_gaps(regions)


def run_fsmn_vad(wavs: dict[str, tuple[np.ndarray, Path]]) -> bool:
    vad_id = "fsmn_vad"
    vad = None
    try:
        from funasr_onnx import Fsmn_vad

        model_dir = prepare_fsmn_dir()
        vad = Fsmn_vad(str(model_dir), quantize=False, intra_op_num_threads=NUM_THREADS, device_id="-1")
    except Exception as exc:
        mark_skipped(
            "vad",
            vad_id,
            "install",
            f"FSMN-VAD ONNX failed (funasr_onnx, no torch installed): {type(exc).__name__}: {exc}",
        )
        return False
    started = time.monotonic()
    try:
        for clip_id, audio, duration in CLIPS:
            samples, _wav = wavs[clip_id]
            clip_started = time.monotonic()
            raw = vad(np.asarray(samples, dtype=np.float32))
            regions = parse_fsmn_segments(raw, duration)
            write_vad_clip(
                vad_id,
                clip_id,
                audio,
                duration,
                regions,
                model="funasr/fsmn-vad-onnx",
                provider="funasr_onnx",
                runtime_sec=time.monotonic() - clip_started,
                extra={"vad_model": str(model_dir.relative_to(ROOT)), "torch_pulled": False},
            )
        write_json(
            OUT / vad_id / "_run.json",
            {
                "vad_id": vad_id,
                "status": "success",
                "failure_kind": "none",
                "torch": torch_loaded(),
                "runtime_sec": round(time.monotonic() - started, 3),
                "peak_rss_mb": peak_rss_mb(),
                "model": "funasr/fsmn-vad-onnx via funasr_onnx 0.4.2",
                "note": "ONNX path only; torch was not installed or imported.",
            },
        )
        return True
    except Exception as exc:
        mark_skipped("vad", vad_id, "runtime", f"{type(exc).__name__}: {exc}")
        return False
    finally:
        if vad is not None:
            del vad
        gc.collect()


def load_vad_regions(vad_id: str) -> dict[str, list[dict[str, float]]] | None:
    out: dict[str, list[dict[str, float]]] = {}
    for clip_id, _, _ in CLIPS:
        path = OUT / vad_id / f"{clip_id}.json"
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("speech_regions") or [
            {"start": row["start"], "end": row["end"]} for row in payload.get("merged_turns", [])
        ]
        out[clip_id] = merge_speech_gaps(rows)
    return out


def fallback_silero_from_1f() -> dict[str, list[dict[str, float]]]:
    out: dict[str, list[dict[str, float]]] = {}
    for clip_id, _, _ in CLIPS:
        path = ROOT / "results/asr/1f/vad_wespeaker" / f"{clip_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        out[clip_id] = merge_speech_gaps(
            [{"start": float(row["start"]), "end": float(row["end"])} for row in payload["merged_turns"]]
        )
    return out


def freeze_speech() -> tuple[dict[str, list[dict[str, float]]], str]:
    silero = load_vad_regions("silero")
    if silero:
        source = "results/asr/1f2/silero (this run)"
        frozen = silero
    else:
        source = "results/asr/1f/vad_wespeaker (fallback; Silero failed this run)"
        frozen = fallback_silero_from_1f()
    write_json(
        OUT / "_frozen_silero.json",
        {
            "source": source,
            "note": "Phase B always uses Silero from this run, not the max-IoU VAD vs pyannote.",
            "clips": {clip_id: {"n_regions": len(rows), "speech_sec": round(sum(r["end"] - r["start"] for r in rows), 3)} for clip_id, rows in frozen.items()},
        },
    )
    return frozen, source


def write_speech_iou(vad_ok: dict[str, bool]) -> None:
    systems = ["pyannote31"] + [name for name in ("silero", "ten_vad", "fsmn_vad") if vad_ok.get(name)]
    clips: dict[str, Any] = {}
    for clip_id, _audio, duration in CLIPS:
        regions_by = {"pyannote31": pyannote_regions(clip_id)}
        for name in ("silero", "ten_vad", "fsmn_vad"):
            loaded = load_vad_regions(name) if vad_ok.get(name) else None
            if loaded:
                regions_by[name] = loaded[clip_id]
        masks = {name: speech_mask(rows, duration) for name, rows in regions_by.items()}
        pairwise = {}
        names = list(masks)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                pairwise[f"{a}__{b}"] = iou(masks[a], masks[b])
        exclusive = {}
        for name, mask in masks.items():
            others = [masks[other] for other in names if other != name]
            exclusive[name] = {
                "speech_sec": seconds(mask),
                "only_this_vs_all_others_sec": exclusive_seconds(mask, others),
                "this_not_pyannote_sec": exclusive_seconds(mask, [masks["pyannote31"]]) if name != "pyannote31" else 0.0,
                "pyannote_not_this_sec": exclusive_seconds(masks["pyannote31"], [mask]) if name != "pyannote31" else 0.0,
            }
        voice_windows = None
        if clip_id == "test_voice":
            voice_windows = {
                f"{int(start)}-{int(end)}s": {
                    name: window_cover(rows, start, end) for name, rows in regions_by.items()
                }
                for start, end in VOICE_WINDOWS
            }
        clips[clip_id] = {
            "duration_sec": duration,
            "pairwise_speech_iou": pairwise,
            "coverage": exclusive,
            "n_regions": {name: len(rows) for name, rows in regions_by.items()},
            "test_voice_windows": voice_windows,
        }
    write_json(
        REPORTS / "speech_iou.json",
        {
            "frame_sec": FRAME,
            "reference": "results/reports/1f/baseline/pyannote31 (union of merged_turns; not human gold)",
            "systems": systems,
            "gap_merge_sec": GAP_MERGE_SEC,
            "clips": clips,
        },
    )


class SherpaEmbedder:
    def __init__(self, model_path: Path):
        import sherpa_onnx

        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(model_path),
            num_threads=NUM_THREADS,
            provider="cpu",
        )
        if not config.validate():
            raise RuntimeError(f"invalid sherpa embedding config: {model_path}")
        self.extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
        self.dim = int(self.extractor.dim)

    def embed(self, chunk: np.ndarray) -> np.ndarray:
        stream = self.extractor.create_stream()
        stream.accept_waveform(sample_rate=16000, waveform=np.asarray(chunk, dtype=np.float32))
        stream.input_finished()
        if not self.extractor.is_ready(stream):
            raise RuntimeError("SpeakerEmbeddingExtractor is not ready")
        return np.asarray(self.extractor.compute(stream), dtype=np.float32).reshape(-1)


def make_wespeaker() -> tuple[Any, str, str, bool]:
    import onnxruntime as ort
    from speakeronnx import SpeakerEmbedder

    options = ort.SessionOptions()
    options.inter_op_num_threads = NUM_THREADS
    options.intra_op_num_threads = NUM_THREADS
    original = ort.InferenceSession

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("sess_options", options)
        kwargs.setdefault("providers", ["CPUExecutionProvider"])
        return original(*args, **kwargs)

    ort.InferenceSession = wrapped  # type: ignore[misc]
    try:
        embedder = SpeakerEmbedder(model="wespeaker-resnet34")
    finally:
        ort.InferenceSession = original  # type: ignore[misc]
    model_path = "Wespeaker/wespeaker-voxceleb-resnet34-LM (speakeronnx wespeaker-resnet34)"
    return embedder, model_path, "speakeronnx", False


def make_eres2net() -> tuple[Any, str, str, bool]:
    path = download(ERES2NET_URL, MODELS / "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")
    embedder = SherpaEmbedder(path)
    return embedder, str(path.relative_to(ROOT)), "sherpa-onnx", False


def make_titanet() -> tuple[Any, str, str, bool]:
    path = download(TITANET_URL, MODELS / "nemo_en_titanet_small.onnx")
    embedder = SherpaEmbedder(path)
    return embedder, str(path.relative_to(ROOT)), "sherpa-onnx", False


def run_embedder(
    embedder_id: str,
    factory: Callable[[], tuple[Any, str, str, bool]],
    frozen: dict[str, list[dict[str, float]]],
    source: str,
    wavs: dict[str, tuple[np.ndarray, Path]],
) -> bool:
    embedder = None
    try:
        embedder, model, provider, uses_torch = factory()
    except Exception as exc:
        mark_skipped(
            "embedder",
            embedder_id,
            "install",
            f"{embedder_id} failed: {type(exc).__name__}: {exc}",
        )
        return False
    started = time.monotonic()
    try:
        for clip_id, audio, duration in CLIPS:
            samples, _wav = wavs[clip_id]
            speech = frozen[clip_id]
            pending: list[tuple[float, float]] = []
            embeddings: list[np.ndarray] = []
            embed_sec = 0.0
            for seg in speech:
                for start, end in windows_for_segment(seg["start"], seg["end"]):
                    chunk = samples[int(start * 16000) : int(end * 16000)]
                    if len(chunk) < int(0.4 * 16000):
                        continue
                    t0 = time.monotonic()
                    embeddings.append(np.asarray(embedder.embed(chunk), dtype=np.float32).reshape(-1))
                    embed_sec += time.monotonic() - t0
                    pending.append((start, end))
            t1 = time.monotonic()
            windows: list[tuple[float, float, int]] = []
            if embeddings:
                labels = cluster_embeddings(np.stack(embeddings))
                windows = [(start, end, int(label)) for (start, end), label in zip(pending, labels)]
            cluster_sec = time.monotonic() - t1
            raw = assemble_turns(speech, windows)
            if not raw:
                raise RuntimeError(f"{clip_id}: assembler produced no turns")
            merged = merge_turns(raw)
            write_json(
                OUT / embedder_id / f"{clip_id}.json",
                {
                    "audio": str(audio.relative_to(ROOT)),
                    "duration_sec": duration,
                    "embedder_id": embedder_id,
                    "model": model,
                    "provider": provider,
                    "execution_mode": "local",
                    "torch": bool(uses_torch or torch_loaded()),
                    "speech_source": source,
                    "embed_runtime_sec": round(embed_sec, 3),
                    "cluster_runtime_sec": round(cluster_sec, 3),
                    "runtime_sec": round(embed_sec + cluster_sec, 3),
                    "peak_rss_mb": peak_rss_mb(),
                    "n_speakers": len({row["speaker"] for row in merged}),
                    "n_turns": len(merged),
                    "n_vad_segments": len(speech),
                    "n_embeddings": len(embeddings),
                    "raw_turns": raw,
                    "merged_turns": merged,
                    "holes_ge_0_5_sec": holes(merged, duration),
                    "num_threads": NUM_THREADS,
                },
            )
        write_json(
            OUT / embedder_id / "_run.json",
            {
                "embedder_id": embedder_id,
                "status": "success",
                "failure_kind": "none",
                "torch": torch_loaded(),
                "runtime_sec": round(time.monotonic() - started, 3),
                "peak_rss_mb": peak_rss_mb(),
                "model": model,
                "provider": provider,
                "speech_source": source,
            },
        )
        return True
    except Exception as exc:
        mark_skipped("embedder", embedder_id, "runtime", f"{type(exc).__name__}: {exc}")
        return False
    finally:
        if embedder is not None:
            del embedder
        gc.collect()


def compare_turns() -> None:
    hyp: list[str] = []
    for name in ("wespeaker", "eres2net", "titanet_small"):
        if any((OUT / name).glob("test_*.json")):
            hyp += ["--hyp-dir", str(OUT / name)]
    if not hyp:
        raise SystemExit("no embedder hyp dirs to compare")
    from subprocess import run

    run(
        [
            sys.executable,
            str(ROOT / "scripts/stage1f_compare_turns.py"),
            *hyp,
            "--ref-dir",
            str(BASE_TURNS),
            "--out",
            str(REPORTS / "turn_compare.json"),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", nargs="?", default="all", choices=["all", "vad", "embed", "compare"])
    args = parser.parse_args()
    require_clips_and_baseline()
    REPORTS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    wavs = prepare_wavs()
    if args.phase in {"all", "vad"}:
        vad_ok = {
            "silero": run_silero(wavs),
            "ten_vad": run_ten_vad(wavs),
            "fsmn_vad": run_fsmn_vad(wavs),
        }
        write_json(OUT / "_vad_status.json", vad_ok)
        write_speech_iou(vad_ok)
    else:
        vad_ok = json.loads((OUT / "_vad_status.json").read_text(encoding="utf-8")) if (OUT / "_vad_status.json").is_file() else {}
        if not (REPORTS / "speech_iou.json").is_file() and vad_ok:
            write_speech_iou(vad_ok)
    if args.phase in {"all", "embed"}:
        frozen, source = freeze_speech()
        for embedder_id, factory in (
            ("wespeaker", make_wespeaker),
            ("eres2net", make_eres2net),
            ("titanet_small", make_titanet),
        ):
            run_embedder(embedder_id, factory, frozen, source, wavs)
    if args.phase in {"all", "compare", "embed"}:
        compare_turns()


if __name__ == "__main__":
    main()
