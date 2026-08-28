"""Offline speech-to-text transcriber web app.

Uses ffmpeg to normalize any uploaded audio to 16 kHz mono PCM and
PocketSphinx (with its bundled English model) to transcribe it fully
offline -- no network calls or API keys required.
"""

import os
import subprocess
import tempfile
import threading
import wave

from flask import Flask, jsonify, render_template, request, send_from_directory
from pocketsphinx import Decoder

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

# A single shared decoder loads the bundled model once. PocketSphinx's decoder
# is not thread-safe, so serialize access with a lock (Flask serves requests
# from worker threads).
_decoder = Decoder()
_decoder_lock = threading.Lock()


class TranscriptionError(Exception):
    """Raised when audio cannot be decoded or transcribed."""


def _normalize_to_wav(src_path: str, dst_path: str) -> None:
    """Convert arbitrary audio into 16 kHz mono signed-16-bit WAV via ffmpeg."""
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", src_path,
            "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
            dst_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not os.path.exists(dst_path):
        raise TranscriptionError(
            "Could not decode the audio file. Please upload a valid audio "
            "file (wav, mp3, m4a, ogg, flac, or webm)."
        )


def _transcribe_wav(wav_path: str) -> str:
    """Run PocketSphinx over a normalized 16 kHz mono WAV and return the text."""
    with wave.open(wav_path, "rb") as wav_file:
        audio = wav_file.readframes(wav_file.getnframes())

    with _decoder_lock:
        _decoder.start_utt()
        _decoder.process_raw(audio, False, True)
        _decoder.end_utt()
        hypothesis = _decoder.hyp()

    return hypothesis.hypstr.strip() if hypothesis else ""


def transcribe_file(src_path: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = os.path.join(tmp, "audio.wav")
        _normalize_to_wav(src_path, wav_path)
        return _transcribe_wav(wav_path)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.get("/samples/<path:filename>")
def samples(filename):
    return send_from_directory(SAMPLES_DIR, filename)


@app.post("/transcribe")
def transcribe():
    uploaded = request.files.get("audio")
    if uploaded is None or uploaded.filename == "":
        return jsonify(error="No audio file was provided."), 400

    with tempfile.TemporaryDirectory() as tmp:
        src_path = os.path.join(tmp, uploaded.filename)
        uploaded.save(src_path)
        try:
            transcript = transcribe_file(src_path)
        except TranscriptionError as exc:
            return jsonify(error=str(exc)), 400

    if not transcript:
        return jsonify(
            transcript="",
            message="No speech was detected in the audio.",
        )
    return jsonify(transcript=transcript)


@app.post("/transcribe-sample")
def transcribe_sample():
    """Transcribe the bundled demo clip so the flow works with one click."""
    sample_path = os.path.join(SAMPLES_DIR, "go-forward.wav")
    if not os.path.exists(sample_path):
        return jsonify(error="Demo sample is missing from the server."), 500
    try:
        transcript = transcribe_file(sample_path)
    except TranscriptionError as exc:
        return jsonify(error=str(exc)), 500
    return jsonify(transcript=transcript, sample="go-forward.wav")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
