"""Движок распознавания речи на базе GigaAM v3 RNNT."""

import tempfile
import time
from pathlib import Path

import soundfile as sf

from transcriber.asr.base import AsrEngine
from transcriber.asr.splitter import split_turns_into_slices
from transcriber.config.schema import AsrConfig
from transcriber.models.artifacts import (
    AudioArtifact,
    TranscriptArtifact,
    TranscriptSegment,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)


def transcribe_slices_with_model(
    wav_path: Path,
    turns: TurnsArtifact,
    max_segment_sec: int = 25,
    gain_db: float = 0.0,
    job_id: str | None = None,
) -> TranscriptArtifact:
    """Выполняет распознавание речи по репликам с помощью модели GigaAM v3 RNNT."""
    import gigaam

    t0 = time.time()
    resolved_job_id = job_id or turns.job_id

    audio, sr = sf.read(str(wav_path))
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    slices = split_turns_into_slices(turns.turns, max_segment_seconds=max_segment_sec)

    model = gigaam.load_model("v3_rnnt", fp16_encoder=False, device="cpu")

    segments: list[TranscriptSegment] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        slice_wav = Path(tmpdir) / "slice.wav"

        for idx, s in enumerate(slices, start=1):
            s_idx = max(0, int(s.start * sr))
            e_idx = min(len(audio), int(s.end * sr))

            seg_audio = audio[s_idx:e_idx]
            text = ""
            if len(seg_audio) >= int(0.1 * sr):  # минимум 100 мс
                sf.write(str(slice_wav), seg_audio, sr)
                res = model.transcribe(str(slice_wav))
                text = str(res.text or "").strip()

            empty = len(text) == 0
            segments.append(
                TranscriptSegment(
                    id=f"s{idx:04d}",
                    turn_id=s.turn_id,
                    start=s.start,
                    end=s.end,
                    speaker=s.speaker,
                    text=text,
                    gain_db=round(gain_db, 3),
                    empty=empty,
                )
            )

    runtime_sec = round(time.time() - t0, 3)

    return TranscriptArtifact(
        schema_version="1",
        job_id=resolved_job_id,
        engine="gigaam_v3_rnnt",
        language="ru",
        segments=segments,
        holes=list(turns.holes),
        max_segment_sec=max_segment_sec,
        runtime_sec=runtime_sec,
    )


class GigaAmAsrEngine(AsrEngine):
    """Компонент распознавания речи GigaAM v3 RNNT с опциональным запуском в подпроцессе."""

    name: str = "gigaam_v3_rnnt"

    def transcribe(
        self,
        wav: Path,
        turns: TurnsArtifact,
        cfg: AsrConfig,
        job_id: str | None = None,
    ) -> TranscriptArtifact:
        """Транскрибирует аудиофайл по репликам дикторов."""
        wav_path = Path(wav)
        if not wav_path.is_file():
            raise FileNotFoundError(f"WAV file not found: {wav_path}")

        job_dir = wav_path.parent
        resolved_job_id = job_id or turns.job_id or job_dir.name
        out_path = job_dir / "transcript.json"

        # Извлекаем gain_db из audio.json если файл существует
        gain_db = 0.0
        audio_json_path = job_dir / "audio.json"
        if audio_json_path.is_file():
            try:
                audio_art = load_artifact(audio_json_path, AudioArtifact)
                gain_db = audio_art.loudness.gain_db
            except Exception:
                gain_db = 0.0

        if cfg.subprocess:
            from transcriber.asr.subprocess_runner import run_asr_subprocess

            artifact = run_asr_subprocess(
                wav_path=wav_path,
                turns_path=job_dir / "turns.json",
                out_path=out_path,
                max_segment_sec=cfg.max_segment_seconds,
                gain_db=gain_db,
                job_id=resolved_job_id,
            )
        else:
            artifact = transcribe_slices_with_model(
                wav_path=wav_path,
                turns=turns,
                max_segment_sec=cfg.max_segment_seconds,
                gain_db=gain_db,
                job_id=resolved_job_id,
            )
            dump_artifact(artifact, out_path)

        return artifact
