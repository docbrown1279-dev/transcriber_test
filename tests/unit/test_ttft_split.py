"""D5.TTFT unit/contract tests (bare checkout — no audio / models)."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

# Import web.app before jobs.queue to avoid circular import (same as test_health).
from transcriber.web.app import app  # noqa: E402

from transcriber.audio.gain import calculate_gain
from transcriber.config.loader import load_config
from transcriber.diarization.eos_refine import greedy_remap_by_duration, refine_window_speakers_v1
from transcriber.diarization.gallery import SpeakerGallery
from transcriber.diarization.merge import merge_turns
from transcriber.diarization.wespeaker import l2_normalize
from transcriber.jobs.queue import job_events_payload
from transcriber.jobs.store import create_job, update_job_flags, update_job_state
from transcriber.models.artifacts import (
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
    TranscriptArtifact,
    TranscriptSegment,
    TurnItem,
    dump_artifact,
)
from transcriber.pipeline.orchestrator import plan_job
from transcriber.pipeline.pause_cut import plan as pause_plan, propose_n_parts
from transcriber.pipeline.steps import PIPELINE_STEPS
from transcriber.pipeline.ttft_split import should_run_ttft_split

CONTRACT_ORDER: list[str] = [
    "normalize",
    "vad",
    "diarize",
    "asr",
    "correction_suggest",
    "chunk",
    "titles",
    "insights_extract",
    "report",
]

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
_CUT_BOUND_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:180(?:\.0)?|270(?:\.0)?|300(?:\.0)?)(?![A-Za-z0-9_])"
)
_CUT_MODULE_PATHS = [
    _SRC_ROOT / "transcriber" / "pipeline" / "pause_cut.py",
    _SRC_ROOT / "transcriber" / "pipeline" / "ttft_split.py",
]


def test_d5t_cfg_01_ttft_split_false_keeps_legacy_plan(tmp_job_dir: Path) -> None:
    """[D5T-CFG-01] ttft_split:false keeps the old step graph; no cut_plan required."""
    cfg = load_config("prod")  # base default overlay path still has ttft_split false in base
    # Explicit: base pipeline default
    base = load_config("demo")
    base = base.model_copy(deep=True)
    base.pipeline.ttft_split = False
    assert base.pipeline.ttft_split is False
    assert should_run_ttft_split(base, duration_sec=900.0) is False

    step_names = [step.stage for step in PIPELINE_STEPS]
    assert step_names == CONTRACT_ORDER
    plans = plan_job(tmp_job_dir)
    assert [p.stage for p in plans] == CONTRACT_ORDER
    assert not (tmp_job_dir / "cut_plan.json").exists()
    # prod profile inherits base ttft_split=false
    assert cfg.pipeline.ttft_split is False


def test_d5t_cfg_02_demo_overlay_and_no_cut_literals() -> None:
    """[D5T-CFG-02] demo has ttft_split true + file_max_db; cut bounds not hardcoded in src."""
    demo = load_config("demo")
    assert demo.pipeline.ttft_split is True
    assert demo.audio.gain.file_max_db == 2.0
    assert demo.pipeline.ttft.max_part_sec == 300
    assert demo.pipeline.ttft.min_part_sec == 180
    assert demo.pipeline.ttft.target_part_sec == 270

    for path in _CUT_MODULE_PATHS:
        text = path.read_text(encoding="utf-8")
        # Strip comments / docstrings loosely — fail on bare cut-bound literals in code body.
        stripped = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        hits = _CUT_BOUND_RE.findall(stripped)
        assert hits == [], f"cut-bound literals in {path.name}: {hits}"


def test_d5t_cut_01_pause_near_ideal_and_midpoint_fallback() -> None:
    """[D5T-CUT-01] long pause near ideal chosen; no-pause → midpoint; parts in [min,max]."""
    duration = 810.0
    min_p, max_p, target = 180.0, 300.0, 270.0
    n = propose_n_parts(
        duration, min_part_sec=min_p, max_part_sec=max_p, target_part_sec=target
    )
    assert n >= 2

    # Long pause near ideal first cut (~270)
    regions_pause = [
        (0.0, 250.0),
        (268.0, 520.0),
        (540.0, 810.0),
    ]
    planned = pause_plan(
        regions_pause,
        duration_sec=duration,
        n_parts=n,
        min_part_sec=min_p,
        max_part_sec=max_p,
        min_pause_sec=0.8,
        search_half_width=90.0,
    )
    first_cut = planned["cuts"][0]["t"]
    assert abs(first_cut - 259.0) < 5.0  # mid of 250–268 pause ≈ 259
    for part in planned["parts"]:
        assert min_p <= part["duration_sec"] <= max_p

    # Continuous speech → midpoint / ideal fallback (pause_duration 0)
    regions_dense = [(0.0, duration)]
    planned_mid = pause_plan(
        regions_dense,
        duration_sec=duration,
        n_parts=3,
        min_part_sec=min_p,
        max_part_sec=max_p,
        min_pause_sec=0.8,
        search_half_width=90.0,
    )
    assert all(c["pause_duration"] == 0.0 for c in planned_mid["cuts"])
    for part in planned_mid["parts"]:
        assert min_p <= part["duration_sec"] <= max_p


def test_d5t_gain_01_file_cap_vs_per_turn() -> None:
    """[D5T-GAIN-01] file path caps at file_max_db=2.0; per-turn still allows 18 dB."""
    # Quiet file: raw target gain = -23 - (-40) = 17 dB
    file_gain = calculate_gain(
        rms_dbfs=-40.0,
        peak_dbfs=-20.0,
        threshold_dbfs=-30.0,
        target_dbfs=-23.0,
        max_gain_db=2.0,
        peak_ceiling_dbfs=-1.0,
    )
    assert file_gain.gain_db == 2.0
    assert file_gain.gain_applied is True
    assert file_gain.capped is True

    turn_gain = calculate_gain(
        rms_dbfs=-40.0,
        peak_dbfs=-20.0,
        threshold_dbfs=-30.0,
        target_dbfs=-23.0,
        max_gain_db=18.0,
        peak_ceiling_dbfs=-1.0,
    )
    assert turn_gain.gain_db == 17.0
    assert turn_gain.gain_applied is True
    assert turn_gain.capped is False


def test_d5t_diar_01_gallery_assign_threshold_not_h1() -> None:
    """[D5T-DIAR-01] dist≤0.85 → existing id; else new id (per-window, not whole-cluster H1)."""
    dim = 8
    c0 = l2_normalize(np.ones((1, dim), dtype=np.float64))[0]
    # Orthogonal-ish second centroid
    c1 = l2_normalize(np.array([[1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0]], dtype=np.float64))[0]
    gallery = SpeakerGallery(threshold=0.85)
    gallery.speakers = [
        {"id": "SPEAKER_00", "n_windows": 2, "centroid": c0},
        {"id": "SPEAKER_01", "n_windows": 2, "centroid": c1},
    ]

    # Near SPEAKER_00 (cosine dist ~0)
    near = l2_normalize(c0.reshape(1, -1) + 0.01 * np.random.default_rng(0).normal(size=(1, dim)))
    # Far from both → new id
    far = l2_normalize(np.array([[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]], dtype=np.float64))
    # Flip far if somehow close
    dist_to_gallery = 1.0 - float(np.clip(far @ np.stack([c0, c1]).T, -1, 1).max())
    if dist_to_gallery <= 0.85:
        far = l2_normalize(np.array([[1.0, 1.0, -1.0, -1.0, 0.0, 0.0, 0.0, 0.0]], dtype=np.float64))

    emb = np.vstack([near, far])
    assigned, summary = gallery.assign(emb)
    assert assigned[0] == "SPEAKER_00"
    assert assigned[1] not in {"SPEAKER_00", "SPEAKER_01"} or summary["new"] >= 1
    assert assigned[1].startswith("SPEAKER_")
    # Method B: each window assigned independently (not one cluster→id for all)
    assert summary["windows"][0]["assigned"] == assigned[0]
    assert summary["windows"][1]["assigned"] == assigned[1]
    assert summary["matched"] >= 1


def test_d5t_diar_02_absorb_under_one_sec_after_assign() -> None:
    """[D5T-DIAR-02] absorb < 1 s still applied after gallery assign."""
    turns = [
        TurnItem(id="t0001", start=0.0, end=4.0, speaker="SPEAKER_00"),
        TurnItem(id="t0002", start=4.1, end=4.6, speaker="SPEAKER_02"),  # 0.5 s
        TurnItem(id="t0003", start=5.0, end=9.0, speaker="SPEAKER_01"),
    ]
    merged = merge_turns(turns, same_speaker_gap_sec=0.3, absorb_shorter_than_sec=1.0)
    assert all((t.end - t.start) >= 1.0 - 1e-6 or t.speaker != "SPEAKER_02" for t in merged)
    assert not any(t.speaker == "SPEAKER_02" for t in merged)
    assert len(merged) == 2


def test_d5t_eos_01_remap_unique_overlap_no_wav() -> None:
    """[D5T-EOS-01] remap keeps published ids when overlap unique; no wav required."""
    mapping = greedy_remap_by_duration(
        cluster_labels=[0, 0, 1, 1],
        published_ids=["SPEAKER_00", "SPEAKER_00", "SPEAKER_01", "SPEAKER_01"],
        durations=[2.0, 3.0, 1.5, 2.5],
    )
    assert mapping[0] == "SPEAKER_00"
    assert mapping[1] == "SPEAKER_01"

    rng = np.random.default_rng(42)
    emb_a = l2_normalize(rng.normal(size=(3, 4)))
    emb_b = l2_normalize(rng.normal(size=(3, 4)) + 5.0)
    embeddings = np.vstack([emb_a, emb_b])
    segments = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (10.0, 11.0), (11.0, 12.0), (12.0, 13.0)]
    mid = ["SPEAKER_00"] * 3 + ["SPEAKER_01"] * 3
    final, summary = refine_window_speakers_v1(
        embeddings,
        segments,
        mid,
        distance_threshold=0.85,
        published_order=["SPEAKER_00", "SPEAKER_01"],
    )
    assert set(final) >= {"SPEAKER_00", "SPEAKER_01"}
    assert summary["n_windows"] == 6
    assert "mapping" in summary


def _seed_editable_job(storage: Path, job_id: str) -> None:
    create_job(job_id, "127.0.0.1", storage)
    update_job_state(job_id, "running", storage)
    update_job_flags(job_id, storage, early_ready=True, speakers_finalized=False)
    job_dir = storage / "jobs" / job_id
    dump_artifact(
        TranscriptArtifact(
            schema_version="1",
            job_id=job_id,
            engine="gigaam_v3_rnnt",
            language="ru",
            segments=[
                TranscriptSegment(
                    id="s0001",
                    turn_id="t0001",
                    start=0.0,
                    end=5.0,
                    speaker="SPEAKER_00",
                    text="привет",
                    gain_db=0.0,
                    empty=False,
                )
            ],
            holes=[],
            max_segment_sec=25,
            runtime_sec=0.1,
        ),
        job_dir / "transcript.json",
    )
    dump_artifact(
        ChaptersArtifact(
            schema_version="1",
            job_id=job_id,
            chunker="packing_c",
            embedding_model="rubert_tiny2",
            similarity_threshold=0.7,
            chapters=[
                ChapterItem(
                    id="C00",
                    start=0.0,
                    end=5.0,
                    source_ids=["s0001"],
                    speakers=["SPEAKER_00"],
                    title="",
                    duration_sec=5.0,
                )
            ],
            metrics=ChapterMetrics(chapters_per_minute=1.0, short_chapters=0, long_chapters=0),
            runtime_sec=0.1,
        ),
        job_dir / "chapters.json",
    )


def test_d5t_ui_01_speaker_edits_rejected_before_eos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[D5T-UI-01] alias POST + segment speaker change rejected while speakers_finalized=false."""
    storage = tmp_path / "var"
    storage.mkdir(parents=True, exist_ok=True)
    job_id = "ttft_lock_job"
    _seed_editable_job(storage, job_id)

    cfg = load_config("demo")
    cfg = cfg.model_copy(deep=True)
    cfg.app.storage_root = str(storage)
    cfg.ui.allow_editing = True
    monkeypatch.setattr("transcriber.web.routes._cfg", lambda: cfg)
    monkeypatch.setattr("transcriber.web.routes.load_config", lambda *a, **k: cfg)

    client = TestClient(app)
    headers = {"Accept": "application/json"}

    alias_resp = client.post(
        f"/jobs/{job_id}/actions/speakers",
        data={"speaker_id": "SPEAKER_00", "speaker_alias": "Алексей"},
        headers=headers,
    )
    assert alias_resp.status_code == 409, alias_resp.text

    edit_resp = client.post(
        f"/jobs/{job_id}/chapters/C00/edit",
        data={
            "seg_id": "s0001",
            "seg_text": "привет",
            "seg_speaker": "SPEAKER_01",
        },
        headers=headers,
    )
    assert edit_resp.status_code == 409, edit_resp.text


def test_d5t_ui_02_events_include_early_ready(tmp_path: Path) -> None:
    """[D5T-UI-02] events JSON has early_ready (payload enough for progress redirect)."""
    storage = tmp_path / "var"
    storage.mkdir(parents=True, exist_ok=True)
    job_id = "ttft_events_job"
    create_job(job_id, "127.0.0.1", storage)
    update_job_state(job_id, "running", storage)
    update_job_flags(job_id, storage, early_ready=True, speakers_finalized=False)

    payload = job_events_payload(job_id, storage)
    assert payload["early_ready"] is True
    assert payload["speakers_finalized"] is False
    assert payload["state"] == "running"
    # Progress JS redirects when early_ready OR state==done
    assert payload["early_ready"] or payload["state"] == "done"
