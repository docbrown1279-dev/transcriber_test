"""[D5T-PROG] TTFT ETA table helpers."""

from transcriber.config.schema import TtftProgressConfig
from transcriber.pipeline.ttft_progress import (
    TtftEtaClock,
    format_dual_eta_ru,
    format_eta_ru,
)


def test_format_eta_ru() -> None:
    assert format_eta_ru(3) == "ориентир < 5 с"
    assert "с" in (format_eta_ru(40) or "")
    assert "мин" in (format_eta_ru(120) or "")


def test_format_dual_eta() -> None:
    dual = format_dual_eta_ru(90.0, 450.0)
    assert dual is not None
    assert "до конца фрагмента" in dual
    assert "до конца файла" in dual
    only_file = format_dual_eta_ru(None, 120.0)
    assert only_file is not None
    assert "до конца файла" in only_file
    assert "фрагмента" not in only_file


def test_eta_clock_part_and_file_remaining() -> None:
    """prep 1% → dual ETA: part phases left + whole-file remaining."""
    cfg = TtftProgressConfig(prep_fraction=0.01, diar_fraction=0.55, asr_fraction=0.35)
    clock = TtftEtaClock(cfg=cfg)
    clock.remember_prep(prep_wall_sec=6.0, n_parts=3)
    assert abs(clock.total_est_sec - 600.0) < 1e-6
    clock.begin_part(0, "diar")
    assert "фрагмент 1 из 3" in clock.label_ru("diar")
    part_rem = clock.remaining_in_part_sec()
    assert part_rem is not None
    # Full part budget at start of diar ≈ part_budget
    assert abs(part_rem - clock.part_budget_sec) < 1.0
    file_rem = clock.remaining_eta_sec(elapsed_wall_sec=6.0)
    assert abs(file_rem - 594.0) < 1e-6


def test_titles_label_includes_chapter_and_fragment() -> None:
    cfg = TtftProgressConfig(prep_fraction=0.01, diar_fraction=0.55, asr_fraction=0.35)
    clock = TtftEtaClock(cfg=cfg, n_parts=3)
    clock.remember_prep(6.0, 3)
    clock.begin_part(0, "titles")
    clock.set_title_progress(2, 5)
    label = clock.label_ru("titles")
    assert "глава 2 из 5" in label
    assert "фрагмент 1 из 3" in label
