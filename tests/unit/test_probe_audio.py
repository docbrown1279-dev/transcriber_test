"""Тесты проверки аудиофайлов через ffprobe и CLI probe-audio."""

import json
from pathlib import Path
import subprocess

import pytest

from transcriber.web.health import probe_audio_file


@pytest.mark.requires_inputs
def test_d0_aud_01_probe_audio_on_packed_voice(fixtures_dir: Path) -> None:
    """[D0-AUD-01] transcriber probe-audio on test_voice.m4a exits 0 and reports duration in 80-90 s."""
    audio_path = fixtures_dir / "audio" / "test_voice.m4a"
    if not audio_path.is_file():
        pytest.skip(f"Packed D0 audio fixture absent: {audio_path}")

    # Проверка через функцию
    res = probe_audio_file(audio_path)
    assert 80.0 <= res["duration_sec"] <= 90.0
    assert res["size_bytes"] > 0

    # Проверка через CLI
    cli_res = subprocess.run(
        ["uv", "run", "transcriber", "probe-audio", str(audio_path)],
        capture_output=True,
        text=True,
    )
    assert cli_res.returncode == 0
    parsed = json.loads(cli_res.stdout)
    assert 80.0 <= parsed["duration_sec"] <= 90.0


def test_d0_aud_02_probe_missing_path_fails_and_no_asr_called(tmp_path: Path) -> None:
    """[D0-AUD-02] probe on missing path exits non-zero; D0 must not call ASR on packed clip."""
    missing_file = tmp_path / "nonexistent.m4a"

    with pytest.raises(FileNotFoundError):
        probe_audio_file(missing_file)

    cli_res = subprocess.run(
        ["uv", "run", "transcriber", "probe-audio", str(missing_file)],
        capture_output=True,
        text=True,
    )
    assert cli_res.returncode != 0
