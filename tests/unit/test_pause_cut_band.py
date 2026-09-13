"""Pause-cut part sizing: 4–6 min band, no crumb parts from float overshoot."""

from transcriber.pipeline.pause_cut import (
    coalesce_short_parts,
    plan,
    propose_n_parts,
)


def test_propose_n_parts_15min_band_240_360() -> None:
    """900s with [240,360] target 300 → 3 parts (not 4)."""
    n = propose_n_parts(
        900.0, min_part_sec=240.0, max_part_sec=360.0, target_part_sec=300.0
    )
    assert n == 3


def test_propose_n_parts_float_overshoot_does_not_force_extra() -> None:
    """900.052s @ max=300 must not become 4 via ceil float noise."""
    n = propose_n_parts(
        900.052, min_part_sec=300.0, max_part_sec=300.0, target_part_sec=300.0
    )
    assert n == 3


def test_coalesce_merges_crumb_first_part() -> None:
    parts = [
        {"id": "part01", "index": 0, "start": 0.0, "end": 0.052, "duration_sec": 0.052},
        {"id": "part02", "index": 1, "start": 0.052, "end": 300.052, "duration_sec": 300.0},
        {"id": "part03", "index": 2, "start": 300.052, "end": 600.052, "duration_sec": 300.0},
        {"id": "part04", "index": 3, "start": 600.052, "end": 900.052, "duration_sec": 300.0},
    ]
    out = coalesce_short_parts(parts, min_part_sec=240.0)
    assert len(out) == 3
    assert out[0]["start"] == 0.0
    assert out[0]["duration_sec"] >= 240.0
    assert all(p["duration_sec"] >= 240.0 for p in out)


def test_plan_15min_demo_band_no_crumbs() -> None:
    duration = 900.052
    regions = [(0.5, duration - 0.5)]
    n = propose_n_parts(
        duration, min_part_sec=240.0, max_part_sec=360.0, target_part_sec=300.0
    )
    planned = plan(
        regions,
        duration_sec=duration,
        n_parts=n,
        min_part_sec=240.0,
        max_part_sec=360.0,
        min_pause_sec=0.8,
        search_half_width=90.0,
    )
    assert planned["n_parts"] == 3
    for part in planned["parts"]:
        assert part["duration_sec"] >= 240.0
        assert part["duration_sec"] <= 360.0 + 1e-6
