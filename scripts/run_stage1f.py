#!/usr/bin/env python3
"""Stage 1f: ONNX diarizers vs frozen pyannote 3.1, then GigaAM v3.

Diarizer processes must not import torch. ASR (GigaAM) may use torch in a
separate interpreter. Threads default to 2 to approximate the 2 vCPU demo box.
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
import math
import resource
import shutil
import sys
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_stage1e import SAMPLE_RATE, astats, extract, holes, merge_turns  # noqa: E402

CLIPS = [
    ("test_voice", ROOT / "data/test_voice.m4a", 83.0),
    ("test_apartments", ROOT / "data/test_apartments.m4a", 85.0),
    ("test_transformers", ROOT / "data/test_transformers.m4a", 85.0),
    ("test_ninth", ROOT / "data/test_ninth.m4a", 85.0),
]
OUT = ROOT / "results" / "asr" / "1f"
EXTRACTS = OUT / "_extracts"
MODELS = ROOT / "models"
BASE_TURNS = ROOT / "results/reports/1f/baseline/pyannote31"
BASE_TEXT = ROOT / "results/reports/1f/baseline/gigaam_v3_on_pyannote"
NUM_THREADS = 2
SHERPA_SEG_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
)
SHERPA_EMB_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
)
SILERO_VAD_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def peak_rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)


def assert_no_torch() -> None:
    if "torch" in sys.modules:
        raise RuntimeError("torch is already loaded; ONNX diarizers must not import it")
    try:
        import torch  # noqa: F401
    except ImportError:
        return
    raise RuntimeError("torch is installed in this interpreter; use .venv-onnx for diarization")


def require_clips_and_baseline() -> None:
    missing = [str(path.relative_to(ROOT)) for _, path, _ in CLIPS if not path.is_file()]
    if missing:
        write_json(
            ROOT / "results/reports/1f/failure.json",
            {"failure_kind": "missing_fixture", "missing": missing},
        )
        raise SystemExit(f"failure_kind: missing_fixture ({missing})")
    if not BASE_TURNS.is_dir() or not BASE_TEXT.is_dir():
        write_json(
            ROOT / "results/reports/1f/failure.json",
            {"failure_kind": "missing_baseline", "turns": str(BASE_TURNS), "text": str(BASE_TEXT)},
        )
        raise SystemExit("failure_kind: missing_baseline")
    for clip_id, _, _ in CLIPS:
        if not (BASE_TURNS / f"{clip_id}.json").is_file():
            raise SystemExit(f"failure_kind: missing_baseline ({clip_id} turns)")
        if not (BASE_TEXT / f"{clip_id}.json").is_file():
            raise SystemExit(f"failure_kind: missing_baseline ({clip_id} text)")


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "stage1f-research"})
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    tmp.replace(dest)
    return dest


def wav16k(source: Path, destination: Path) -> np.ndarray:
    import soundfile as sf
    from run_stage1e import run

    destination.parent.mkdir(parents=True, exist_ok=True)
    run(
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
    return audio


def speaker_name(label: Any) -> str:
    text = str(label)
    if text.startswith("SPEAKER_"):
        return text
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return f"SPEAKER_{int(digits):02d}"
    return f"SPEAKER_{text}"


def copy_pyannote31() -> None:
    require_clips_and_baseline()
    dest_dir = OUT / "pyannote31"
    for clip_id, audio, duration in CLIPS:
        turns = json.loads((BASE_TURNS / f"{clip_id}.json").read_text(encoding="utf-8"))
        text = json.loads((BASE_TEXT / f"{clip_id}.json").read_text(encoding="utf-8"))
        merged = turns["merged_turns"]
        payload = {
            "audio": str(audio.relative_to(ROOT)),
            "language": "ru",
            "duration_sec": duration,
            "diarizer_id": "pyannote31",
            "model": turns.get("model", "pyannote/speaker-diarization-3.1"),
            "provider": turns.get("provider", "pyannote.audio"),
            "execution_mode": "local",
            "torch": True,
            "runtime_sec": turns.get("runtime_sec"),
            "peak_rss_mb": None,
            "n_speakers": len({row["speaker"] for row in merged}),
            "n_turns": len(merged),
            "raw_turns": turns.get("raw_turns"),
            "merged_turns": merged,
            "holes_ge_0_5_sec": turns.get("holes_ge_0_5_sec") or holes(merged, duration),
            "asr_model": text.get("model", "gigaam-v3-rnnt"),
            "asr_provider": text.get("provider", "gigaam"),
            "asr_runtime_sec": text.get("runtime_sec"),
            "gain": text.get("gain", "linear"),
            "segments": text.get("segments", []),
            "copied_from": {
                "turns": str((BASE_TURNS / f"{clip_id}.json").relative_to(ROOT)),
                "text": str((BASE_TEXT / f"{clip_id}.json").relative_to(ROOT)),
            },
            "note": "Copied Stage 1e pyannote 3.1 + GigaAM v3. Torch was used in 1e; not loaded here.",
        }
        write_json(dest_dir / f"{clip_id}.json", payload)
    write_json(
        dest_dir / "_run.json",
        {
            "diarizer_id": "pyannote31",
            "status": "copied",
            "torch": True,
            "note": "Baseline copy only; pyannote.audio was not imported.",
        },
    )


def ensure_sherpa_models() -> tuple[Path, Path]:
    archive = download(SHERPA_SEG_URL, MODELS / "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2")
    seg_dir = MODELS / "sherpa-onnx-pyannote-segmentation-3-0"
    seg_path = seg_dir / "model.onnx"
    if not seg_path.is_file():
        with tarfile.open(archive, "r:bz2") as tar:
            tar.extractall(MODELS)
    emb_path = download(
        SHERPA_EMB_URL,
        MODELS / "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
    )
    if not seg_path.is_file():
        raise RuntimeError(f"missing sherpa segmentation model at {seg_path}")
    return seg_path, emb_path


def diarize_sherpa() -> None:
    assert_no_torch()
    require_clips_and_baseline()
    import sherpa_onnx

    seg_path, emb_path = ensure_sherpa_models()
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(seg_path)),
            num_threads=NUM_THREADS,
            provider="cpu",
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(emb_path),
            num_threads=NUM_THREADS,
            provider="cpu",
        ),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=0.5),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise RuntimeError("sherpa-onnx diarization config failed validation")
    diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)
    started = time.monotonic()
    dest_dir = OUT / "sherpa_onnx"
    for clip_id, audio, duration in CLIPS:
        dest = dest_dir / f"{clip_id}.json"
        if dest.exists() and json.loads(dest.read_text(encoding="utf-8")).get("merged_turns"):
            continue
        clip_started = time.monotonic()
        samples = wav16k(audio, EXTRACTS / "sherpa_onnx" / f"{clip_id}.16k.wav")
        result = diarizer.process(samples).sort_by_start_time()
        raw = [
            {
                "start": round(float(item.start), 6),
                "end": round(float(item.end), 6),
                "speaker": speaker_name(item.speaker),
            }
            for item in result
            if float(item.end) > float(item.start)
        ]
        merged = merge_turns(raw)
        write_json(
            dest,
            {
                "audio": str(audio.relative_to(ROOT)),
                "duration_sec": duration,
                "diarizer_id": "sherpa_onnx",
                "model": "pyannote-segmentation-3.0-onnx + 3dspeaker-eres2net-base-zh-cn",
                "provider": "sherpa-onnx",
                "execution_mode": "local",
                "torch": False,
                "runtime_sec": round(time.monotonic() - clip_started, 3),
                "peak_rss_mb": peak_rss_mb(),
                "n_speakers": len({row["speaker"] for row in merged}),
                "n_turns": len(merged),
                "raw_turns": raw,
                "merged_turns": merged,
                "holes_ge_0_5_sec": holes(merged, duration),
                "segmentation_model": str(seg_path.relative_to(ROOT)),
                "embedding_model": str(emb_path.relative_to(ROOT)),
                "num_threads": NUM_THREADS,
                "cluster_threshold": 0.5,
            },
        )
    write_json(
        dest_dir / "_run.json",
        {
            "diarizer_id": "sherpa_onnx",
            "status": "success",
            "torch": False,
            "runtime_sec": round(time.monotonic() - started, 3),
            "peak_rss_mb": peak_rss_mb(),
            "sherpa_onnx": getattr(sherpa_onnx, "__version__", None),
        },
    )
    del diarizer
    gc.collect()


class SileroVadOnnx:
    """Silero VAD v5 ONNX wrapper with numpy only."""

    def __init__(self, path: Path):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.inter_op_num_threads = NUM_THREADS
        options.intra_op_num_threads = NUM_THREADS
        self.session = ort.InferenceSession(
            str(path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.input_names = {item.name for item in self.session.get_inputs()}
        self.reset()

    def reset(self) -> None:
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)

    def prob(self, chunk: np.ndarray) -> float:
        if chunk.shape[-1] != 512:
            padded = np.zeros(512, dtype=np.float32)
            padded[: chunk.shape[-1]] = chunk
            chunk = padded
        x = np.concatenate([self.context, chunk.reshape(1, -1)], axis=1).astype(np.float32)
        feeds: dict[str, np.ndarray] = {"input": x, "state": self.state, "sr": np.array(16000, dtype=np.int64)}
        extra = self.input_names - set(feeds)
        if extra:
            raise RuntimeError(f"unexpected Silero VAD inputs: {sorted(self.input_names)}")
        out, state = self.session.run(None, feeds)
        self.state = state
        self.context = x[:, -64:]
        return float(np.asarray(out).reshape(-1)[0])


def speech_timestamps(
    audio: np.ndarray,
    model: SileroVadOnnx,
    *,
    threshold: float = 0.45,
    min_speech_ms: int = 200,
    min_silence_ms: int = 50,
    speech_pad_ms: int = 20,
) -> list[dict[str, float]]:
    window = 512
    model.reset()
    probs: list[float] = []
    for start in range(0, len(audio), window):
        probs.append(model.prob(audio[start : start + window]))
    neg_threshold = max(threshold - 0.15, 0.01)
    min_speech = int(16000 * min_speech_ms / 1000)
    min_silence = int(16000 * min_silence_ms / 1000)
    pad = int(16000 * speech_pad_ms / 1000)
    triggered = False
    speeches: list[dict[str, int]] = []
    current: dict[str, int] = {}
    temp_end = 0
    for index, prob in enumerate(probs):
        cur = window * index
        if prob >= threshold and not triggered:
            triggered = True
            current = {"start": cur}
            temp_end = 0
            continue
        if triggered and prob < neg_threshold:
            if not temp_end:
                temp_end = cur
            if cur - temp_end >= min_silence:
                current["end"] = temp_end
                if current["end"] - current["start"] >= min_speech:
                    speeches.append(current)
                current = {}
                triggered = False
                temp_end = 0
        elif triggered:
            temp_end = 0
    if triggered:
        current["end"] = len(audio)
        if current["end"] - current["start"] >= min_speech:
            speeches.append(current)
    duration = len(audio)
    out: list[dict[str, float]] = []
    for index, row in enumerate(speeches):
        start_sample = max(0, row["start"] - pad)
        end_sample = min(duration, row["end"] + pad)
        if out:
            start_sample = max(start_sample, int(round(out[-1]["end"] * 16000)))
        if end_sample > start_sample:
            out.append(
                {
                    "start": round(start_sample / 16000, 6),
                    "end": round(end_sample / 16000, 6),
                }
            )
    return out


def cluster_embeddings(embeddings: np.ndarray) -> np.ndarray:
    from sklearn.cluster import SpectralClustering
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import normalize

    n = len(embeddings)
    if n < 2:
        return np.zeros(n, dtype=int)
    emb = normalize(embeddings, norm="l2")
    sim = cosine_similarity(emb)
    mask = ~np.eye(n, dtype=bool)
    sim_p10 = float(np.percentile(sim[mask], 10)) if n > 1 else 1.0
    if sim_p10 >= 0.16:
        return np.zeros(n, dtype=int)
    if n < 4:
        return np.zeros(n, dtype=int)

    pca_dim = min(8, n - 1, emb.shape[1])
    projected = PCA(n_components=pca_dim, random_state=42).fit_transform(emb)
    k_to_bic: dict[int, float] = {}
    for k in range(1, max(3, min(9, n // 2 + 1))):
        try:
            gmm = GaussianMixture(
                n_components=k,
                covariance_type="full",
                random_state=42,
                n_init=5,
                max_iter=300,
            )
            gmm.fit(projected)
            k_to_bic[k] = gmm.bic(projected)
        except Exception:
            continue
    if not k_to_bic:
        return np.zeros(n, dtype=int)
    best_k = min(k_to_bic, key=k_to_bic.get)

    def spectral(k: int) -> np.ndarray:
        k = min(k, n)
        if k <= 1:
            return np.zeros(n, dtype=int)
        affinity = np.maximum((cosine_similarity(emb) + 1) / 2, 0)
        np.fill_diagonal(affinity, 1.0)
        labels = SpectralClustering(
            n_clusters=k,
            affinity="precomputed",
            assign_labels="kmeans",
            random_state=42,
            n_init=10,
        ).fit_predict(affinity)
        unique = sorted(set(int(x) for x in labels))
        mapped = np.array([unique.index(int(x)) for x in labels], dtype=int)
        k_eff = len(unique)
        for _ in range(8):
            centroids = np.zeros((k_eff, emb.shape[1]))
            valid = True
            for label in range(k_eff):
                members = emb[mapped == label]
                if len(members) == 0:
                    valid = False
                    break
                centroid = members.mean(axis=0)
                norm = float(np.linalg.norm(centroid))
                if norm == 0:
                    valid = False
                    break
                centroids[label] = centroid / norm
            if not valid:
                break
            updated = np.argmax(emb @ centroids.T, axis=1)
            if len(set(updated)) < k_eff or np.array_equal(updated, mapped):
                break
            mapped = updated
        return mapped

    labels = spectral(best_k)
    if best_k >= 2 and n >= 4:
        distance = np.maximum(1 - (cosine_similarity(emb) + 1) / 2, 0)
        best_score = -1.0
        best_labels = labels
        lower = max(2, best_k - 2)
        upper = min(8, n - 1, best_k + 3)
        for candidate in range(lower, upper + 1):
            candidate_labels = spectral(candidate)
            try:
                sil = silhouette_score(distance, candidate_labels, metric="precomputed")
            except Exception:
                continue
            score = sil + 0.04 * math.log(max(candidate, 1))
            if score > best_score:
                best_score = score
                best_labels = candidate_labels
        labels = best_labels
    return labels


def windows_for_segment(start: float, end: float) -> list[tuple[float, float]]:
    duration = end - start
    if duration < 0.4:
        return []
    if duration <= 1.2 * 1.5:
        return [(start, end)]
    out: list[tuple[float, float]] = []
    cursor = start
    while cursor + 0.4 < end:
        out.append((cursor, min(cursor + 1.2, end)))
        cursor += 0.6
    return out or [(start, end)]


def assemble_turns(
    speech: list[dict[str, float]],
    windows: list[tuple[float, float, int]],
) -> list[dict[str, Any]]:
    if not windows:
        return [
            {"start": round(row["start"], 6), "end": round(row["end"], 6), "speaker": "SPEAKER_00"}
            for row in speech
        ]
    labels = np.array([item[2] for item in windows], dtype=int)
    if len(labels) >= 3:
        smoothed = labels.copy()
        for i in range(len(labels)):
            smoothed[i] = int(np.median(labels[max(0, i - 1) : min(len(labels), i + 2)]))
        labels = smoothed
        windows = [(start, end, int(label)) for (start, end, _), label in zip(windows, labels)]
    ordered = sorted(windows, key=lambda item: item[0])
    raw: list[dict[str, Any]] = []
    for start, end, label in ordered:
        speaker = speaker_name(label)
        if raw and raw[-1]["speaker"] == speaker and start <= raw[-1]["end"] + 0.05:
            raw[-1]["end"] = max(raw[-1]["end"], end)
        else:
            raw.append({"start": start, "end": end, "speaker": speaker})
    midpoints = [((start + end) / 2, speaker_name(label)) for start, end, label in ordered]
    used = {(round(row["start"], 3), round(row["end"], 3)) for row in raw}
    for seg in speech:
        if seg["end"] - seg["start"] >= 0.4:
            continue
        mid = (seg["start"] + seg["end"]) / 2
        speaker = min(midpoints, key=lambda item: abs(item[0] - mid))[1]
        key = (round(seg["start"], 3), round(seg["end"], 3))
        if key in used:
            continue
        raw.append({"start": seg["start"], "end": seg["end"], "speaker": speaker})
    raw.sort(key=lambda row: (row["start"], row["end"]))
    return [
        {"start": round(float(row["start"]), 6), "end": round(float(row["end"]), 6), "speaker": row["speaker"]}
        for row in raw
        if row["end"] > row["start"]
    ]


def diarize_vad_wespeaker() -> None:
    assert_no_torch()
    require_clips_and_baseline()
    from speakeronnx import SpeakerEmbedder

    vad_path = download(SILERO_VAD_URL, MODELS / "silero_vad.onnx")
    vad = SileroVadOnnx(vad_path)
    embedder = SpeakerEmbedder(model="wespeaker-resnet34")
    started = time.monotonic()
    dest_dir = OUT / "vad_wespeaker"
    for clip_id, audio, duration in CLIPS:
        dest = dest_dir / f"{clip_id}.json"
        if dest.exists() and json.loads(dest.read_text(encoding="utf-8")).get("merged_turns"):
            continue
        clip_started = time.monotonic()
        samples = wav16k(audio, EXTRACTS / "vad_wespeaker" / f"{clip_id}.16k.wav")
        speech = speech_timestamps(samples, vad)
        embeddings: list[np.ndarray] = []
        windows: list[tuple[float, float, int]] = []
        pending: list[tuple[float, float]] = []
        for seg in speech:
            for start, end in windows_for_segment(seg["start"], seg["end"]):
                chunk = samples[int(start * 16000) : int(end * 16000)]
                if len(chunk) < int(0.4 * 16000):
                    continue
                embeddings.append(np.asarray(embedder.embed(chunk), dtype=np.float32).reshape(-1))
                pending.append((start, end))
        if embeddings:
            labels = cluster_embeddings(np.stack(embeddings))
            windows = [(start, end, int(label)) for (start, end), label in zip(pending, labels)]
        raw = assemble_turns(speech, windows)
        if not raw:
            raise RuntimeError(f"{clip_id}: VAD produced no speaker-labelled turns")
        if len({row["speaker"] for row in raw}) < 1:
            raise RuntimeError(f"{clip_id}: VAD-only output without speaker ids")
        merged = merge_turns(raw)
        write_json(
            dest,
            {
                "audio": str(audio.relative_to(ROOT)),
                "duration_sec": duration,
                "diarizer_id": "vad_wespeaker",
                "model": "silero-vad-onnx + wespeaker-resnet34-LM",
                "provider": "onnxruntime+speakeronnx",
                "execution_mode": "local",
                "torch": False,
                "runtime_sec": round(time.monotonic() - clip_started, 3),
                "peak_rss_mb": peak_rss_mb(),
                "n_speakers": len({row["speaker"] for row in merged}),
                "n_turns": len(merged),
                "raw_turns": raw,
                "merged_turns": merged,
                "holes_ge_0_5_sec": holes(merged, duration),
                "vad_model": str(vad_path.relative_to(ROOT)),
                "embedding_model": "wespeaker-resnet34",
                "n_vad_segments": len(speech),
                "n_embeddings": len(embeddings),
                "num_threads": NUM_THREADS,
            },
        )
    write_json(
        dest_dir / "_run.json",
        {
            "diarizer_id": "vad_wespeaker",
            "status": "success",
            "torch": False,
            "runtime_sec": round(time.monotonic() - started, 3),
            "peak_rss_mb": peak_rss_mb(),
        },
    )
    del embedder
    del vad
    gc.collect()


def compare_turns() -> None:
    from subprocess import run

    hyp = []
    for name in ("sherpa_onnx", "vad_wespeaker"):
        if (OUT / name).is_dir() and any((OUT / name).glob("test_*.json")):
            hyp += ["--hyp-dir", str(OUT / name)]
    if not hyp:
        raise SystemExit("no ONNX hyp dirs to compare")
    run(
        [sys.executable, str(ROOT / "scripts/stage1f_compare_turns.py"), *hyp],
        check=True,
    )


def clamp_interval(start: float, end: float, duration: float) -> tuple[float, float]:
    start = min(max(0.0, float(start)), duration)
    end = min(max(start, float(end)), duration)
    return start, end


def extract_clip(
    source: Path,
    start: float,
    end: float,
    destination: Path,
    duration: float,
    gain_db: float = 0.0,
) -> None:
    import soundfile as sf

    start, end = clamp_interval(start, end, duration)
    try:
        extract(source, start, end, destination, gain_db)
        return
    except RuntimeError:
        if destination.is_file() and sf.info(destination).frames > 0:
            return
        raise


def prepare_gain_rows(
    clip_id: str,
    audio: Path,
    merged: list[dict[str, Any]],
    extract_dir: Path,
    duration: float,
) -> list[dict[str, Any]]:
    rows = []
    for index, row in enumerate(merged):
        start, end = clamp_interval(row["start"], row["end"], duration)
        raw_wav = extract_dir / f"turn_{index:03d}_raw.wav"
        gained_wav = extract_dir / f"turn_{index:03d}_linear.wav"
        extract_clip(audio, start, end, raw_wav, duration)
        rms, peak = astats(raw_wav)
        gain = 0.0
        if rms < -30.0 and peak < 0.0 and math.isfinite(rms):
            gain = min(-23.0 - rms, 18.0, -1.0 - peak)
            gain = max(0.0, gain)
        extract_clip(audio, start, end, gained_wav, duration, gain)
        item = dict(row)
        item.update(
            {
                "start": round(start, 6),
                "end": round(end, 6),
                "id": index,
                "rms_dbfs": round(rms, 3) if math.isfinite(rms) else None,
                "peak_dbfs": round(peak, 3) if math.isfinite(peak) else None,
                "gain_db": round(gain, 3),
            }
        )
        rows.append(item)
    return rows


def asr_gigaam(diarizer_id: str) -> None:
    if diarizer_id == "pyannote31":
        copy_pyannote31()
        return
    import gigaam

    dest_dir = OUT / diarizer_id
    model = gigaam.load_model("v3_rnnt", fp16_encoder=False, device="cpu")
    started = time.monotonic()
    for clip_id, audio, _duration in CLIPS:
        path = dest_dir / f"{clip_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("segments"):
            continue
        clip_started = time.monotonic()
        extract_dir = EXTRACTS / diarizer_id / clip_id
        duration = float(payload["duration_sec"])
        rows = prepare_gain_rows(clip_id, audio, payload["merged_turns"], extract_dir, duration)
        payload["merged_turns"] = rows
        payload["n_turns"] = len(rows)
        payload["n_speakers"] = len({row["speaker"] for row in rows})
        pieces: list[dict[str, Any]] = []
        import soundfile as sf

        max_samples = 25 * SAMPLE_RATE
        for row in rows:
            piece_start = row["start"]
            piece_number = 0
            while piece_start < row["end"] - 1e-9:
                piece_end = min(piece_start + 25.0, row["end"])
                wav = extract_dir / f"turn_{row['id']:03d}_piece_{piece_number:02d}_linear.wav"
                extract_clip(audio, piece_start, piece_end, wav, duration, row["gain_db"])
                data, rate = sf.read(wav)
                if len(data) > max_samples:
                    sf.write(wav, data[:max_samples], rate)
                text = str(model.transcribe(str(wav)))
                pieces.append(
                    {
                        "id": len(pieces),
                        "start": round(piece_start, 6),
                        "end": round(piece_end, 6),
                        "speaker": row["speaker"],
                        "text": text.strip(),
                    }
                )
                piece_start = piece_end
                piece_number += 1
        payload.update(
            {
                "language": "ru",
                "asr_model": "gigaam-v3-rnnt",
                "asr_provider": "gigaam",
                "asr_runtime_sec": round(time.monotonic() - clip_started, 3),
                "gain": "linear" if any(row["gain_db"] > 0 for row in rows) else "none",
                "segments": pieces,
            }
        )
        write_json(path, payload)
    run_path = dest_dir / "_run.json"
    meta = json.loads(run_path.read_text(encoding="utf-8")) if run_path.exists() else {}
    meta.update(
        {
            "asr_model": "v3_rnnt",
            "asr_runtime_sec": round(time.monotonic() - started, 3),
        }
    )
    write_json(run_path, meta)
    del model
    gc.collect()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase",
        choices=["copy", "sherpa", "vad", "compare", "asr"],
    )
    parser.add_argument("--id", dest="diarizer_id", default="")
    args = parser.parse_args()
    if args.phase == "copy":
        copy_pyannote31()
    elif args.phase == "sherpa":
        diarize_sherpa()
    elif args.phase == "vad":
        diarize_vad_wespeaker()
    elif args.phase == "compare":
        compare_turns()
    elif args.phase == "asr":
        if args.diarizer_id not in {"pyannote31", "sherpa_onnx", "vad_wespeaker"}:
            raise SystemExit("--id must be pyannote31, sherpa_onnx, or vad_wespeaker")
        asr_gigaam(args.diarizer_id)


if __name__ == "__main__":
    main()
