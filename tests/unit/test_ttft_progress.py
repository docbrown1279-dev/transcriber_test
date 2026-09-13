"""[D5T-PROG] TTFT ETA table helpers."""

from transcriber.config.schema import TtftProgressConfig
from transcriber.pipeline.ttft_progress import TtftEtaClock, format_eta_ru


def test_format_eta_ru() -> None:
    assert format_eta_ru(3) == "ориентир < 5 с"
    assert "с" in (format_eta_ru(40) or "")
    assert "мин" in (format_eta_ru(120) or "")


def test_eta_clock_after_prep() -> None:
    """prep 5% → total = prep/0.05; part diar = budget*0.60."""
    cfg = TtftProgressConfig(prep_fraction=0.05, diar_fraction=0.60, asr_fraction=0.30)
    clock = TtftEtaClock(cfg=cfg)
    clock.remember_prep(prep_wall_sec=10.0, n_parts=3)
    assert abs(clock.total_est_sec - 200.0) < 1e-6
    assert abs(clock.part_budget_sec - (190.0 / 3.0)) < 1e-6
    clock.begin_part(0, "diar")
    assert "фрагмент 1 из 3" in clock.label_ru("diar")
    diar_eta = clock.eta_for_phase("diar")
    assert abs(diar_eta - clock.part_budget_sec * 0.60) < 1e-6
    asr_eta = clock.eta_for_phase("asr")
    assert abs(asr_eta - clock.part_budget_sec * 0.30) < 1e-6
