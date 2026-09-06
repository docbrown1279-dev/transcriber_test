"""Unit tests for speech region IoU."""

from transcriber.quality.intervals import speech_regions_iou


def test_speech_iou_identical() -> None:
    regions = [(0.0, 1.0), (2.0, 3.0)]
    assert speech_regions_iou(regions, regions) == 1.0


def test_speech_iou_disjoint() -> None:
    assert speech_regions_iou([(0.0, 1.0)], [(2.0, 3.0)]) == 0.0


def test_speech_iou_partial_overlap() -> None:
    # ref 0-2 (2s), hyp 1-3 (2s), inter 1s, union 3s → 1/3
    iou = speech_regions_iou([(0.0, 2.0)], [(1.0, 3.0)])
    assert abs(iou - (1.0 / 3.0)) < 1e-9
