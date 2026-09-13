"""EOS micro-speaker absorb (UI speech metric) and greedy remap."""

import numpy as np

from transcriber.diarization.eos_refine import (
    absorb_micro_speaker_map,
    absorb_micro_speakers,
    centroids_from_windows,
)


def test_absorb_by_ui_speech_merges_crumbs() -> None:
    """Speakers with transcript speech <2s map onto nearest centroid."""
    rng = np.random.default_rng(0)
    a = rng.normal(size=8)
    b = rng.normal(size=8) + 5.0
    micro = a + rng.normal(scale=0.01, size=8)
    embeddings = np.stack([a, a, b, b, micro]).astype(np.float64)
    speakers = ["SPEAKER_00", "SPEAKER_00", "SPEAKER_01", "SPEAKER_01", "SPEAKER_03"]
    segments = [(0.0, 1.5), (1.5, 3.0), (3.0, 4.5), (4.5, 6.0), (6.0, 7.5)]
    # UI shows 03 with 1.0s even though a window is long
    speech = {"SPEAKER_00": 100.0, "SPEAKER_01": 80.0, "SPEAKER_03": 1.0}
    cents = centroids_from_windows(embeddings, speakers)
    remap, summary = absorb_micro_speaker_map(speech, cents, min_speech_sec=2.0)
    assert remap["SPEAKER_03"] == "SPEAKER_00"
    assert summary["absorbed"]
    assert summary["metric"] == "ui_speech_sum"
    out, _ = absorb_micro_speakers(
        embeddings, segments, speakers, min_speech_sec=2.0, speech_sec=speech
    )
    assert "SPEAKER_03" not in out
    assert out[4] == "SPEAKER_00"


def test_absorb_skips_when_ui_speech_above_threshold() -> None:
    rng = np.random.default_rng(1)
    embeddings = rng.normal(size=(4, 4)).astype(np.float64)
    speakers = ["SPEAKER_00", "SPEAKER_00", "SPEAKER_01", "SPEAKER_01"]
    segments = [(0.0, 1.0)] * 4
    speech = {"SPEAKER_00": 50.0, "SPEAKER_01": 40.0}
    cents = centroids_from_windows(embeddings, speakers)
    remap, summary = absorb_micro_speaker_map(speech, cents, min_speech_sec=2.0)
    assert remap["SPEAKER_00"] == "SPEAKER_00"
    assert remap["SPEAKER_01"] == "SPEAKER_01"
    assert summary["absorbed"] == []


def test_absorb_disabled_when_threshold_zero() -> None:
    speech = {"SPEAKER_00": 0.5, "SPEAKER_01": 100.0}
    cents = {
        "SPEAKER_00": np.ones(4),
        "SPEAKER_01": np.zeros(4),
    }
    remap, summary = absorb_micro_speaker_map(speech, cents, min_speech_sec=0.0)
    assert remap == {"SPEAKER_00": "SPEAKER_00", "SPEAKER_01": "SPEAKER_01"}
    assert summary["disabled"] is True
