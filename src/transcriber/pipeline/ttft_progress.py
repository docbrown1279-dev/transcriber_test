"""Оценка ETA для TTFT file-split (простая таблица долей)."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from transcriber.config.schema import TtftProgressConfig

_PART_PHASES = ("diar", "asr", "pack")


def format_eta_ru(seconds: float | None, *, prefix: str = "ориентир") -> str | None:
    """Человекочитаемый ориентир: «ориентир ~2 мин»."""
    if seconds is None:
        return None
    total = max(0, int(round(float(seconds))))
    if total < 5:
        body = "< 5 с"
    elif total < 60:
        body = f"~{total} с"
    else:
        minutes = max(1, int(round(total / 60.0)))
        if minutes < 60:
            body = f"~{minutes} мин"
        else:
            hours, rem = divmod(minutes, 60)
            body = f"~{hours} ч" if rem == 0 else f"~{hours} ч {rem} мин"
    return f"{prefix} {body}"


def format_dual_eta_ru(
    part_sec: float | None,
    total_sec: float | None,
) -> str | None:
    """Two clocks: current fragment (if any) + whole file."""
    parts: list[str] = []
    if part_sec is not None:
        label = format_eta_ru(part_sec, prefix="до конца фрагмента")
        if label:
            parts.append(label)
    if total_sec is not None:
        label = format_eta_ru(total_sec, prefix="до конца файла")
        if label:
            parts.append(label)
    if not parts:
        return None
    return " · ".join(parts)


@dataclass
class TtftEtaClock:
    """Часы ETA: prep = fraction; остаток делится на части; внутри — diar/asr/pack."""

    cfg: TtftProgressConfig
    prep_wall_sec: float = 0.0
    n_parts: int = 1
    # Progress cursors
    parts_completed: int = 0
    current_part_index: int = 0  # 0-based
    phase: str = "prep"  # prep | diar | asr | pack | eos | titles | done
    run_t0: float | None = None  # monotonic() at job start
    phase_t0: float | None = None  # monotonic() when current phase began
    title_index: int | None = None  # 1-based chapter being titled
    title_total: int | None = None

    def remember_prep(self, prep_wall_sec: float, n_parts: int) -> None:
        self.prep_wall_sec = max(0.0, float(prep_wall_sec))
        self.n_parts = max(1, int(n_parts))
        self.phase = "prep"

    def set_phase(self, phase: str) -> None:
        if phase != self.phase:
            self.phase_t0 = monotonic()
        self.phase = phase

    def set_title_progress(self, index_1based: int, total: int) -> None:
        self.title_index = int(index_1based)
        self.title_total = int(total)

    @property
    def total_est_sec(self) -> float:
        frac = float(self.cfg.prep_fraction)
        if frac <= 1e-9:
            return self.prep_wall_sec
        if self.prep_wall_sec <= 0:
            return 600.0
        return self.prep_wall_sec / frac

    @property
    def part_budget_sec(self) -> float:
        rem = max(0.0, self.total_est_sec - self.prep_wall_sec)
        return rem / float(self.n_parts)

    def eta_for_phase(self, phase: str) -> float:
        budget = self.part_budget_sec
        if phase == "diar":
            return budget * float(self.cfg.diar_fraction)
        if phase == "asr":
            return budget * float(self.cfg.asr_fraction)
        if phase == "pack":
            rest = max(
                0.0,
                1.0 - float(self.cfg.diar_fraction) - float(self.cfg.asr_fraction),
            )
            return budget * rest
        if phase == "eos":
            return max(5.0, self.part_budget_sec * 0.05)
        if phase == "titles":
            return max(15.0, self.part_budget_sec * 0.15)
        if phase == "prep":
            return max(0.0, self.prep_wall_sec) if self.prep_wall_sec else 30.0
        return budget

    def remaining_in_part_sec(self) -> float | None:
        """Seconds left in the current media fragment (None if not in a part loop)."""
        if self.phase == "titles" and self.parts_completed < self.n_parts:
            budget = self.eta_for_phase("titles")
            if self.phase_t0 is not None:
                phase_elapsed = max(0.0, monotonic() - float(self.phase_t0))
                return max(0.0, budget - phase_elapsed)
            return budget
        if self.phase not in _PART_PHASES:
            return None
        try:
            idx = _PART_PHASES.index(self.phase)
        except ValueError:
            return None
        rem = 0.0
        cur_budget = self.eta_for_phase(self.phase)
        if self.phase_t0 is not None:
            phase_elapsed = max(0.0, monotonic() - float(self.phase_t0))
            rem += max(0.0, cur_budget - phase_elapsed)
        else:
            rem += cur_budget
        for later in _PART_PHASES[idx + 1 :]:
            rem += self.eta_for_phase(later)
        return rem

    def remaining_eta_sec(self, *, elapsed_wall_sec: float | None = None) -> float:
        """Whole-file remaining wall ≈ total_est − elapsed."""
        if self.phase == "done":
            return 0.0
        if self.phase == "prep" and self.prep_wall_sec <= 0:
            return 30.0
        total = self.total_est_sec
        if elapsed_wall_sec is not None and elapsed_wall_sec >= 0:
            return max(0.0, total - float(elapsed_wall_sec))
        left_parts = max(0, self.n_parts - self.current_part_index - 1)
        part_rem = self.remaining_in_part_sec()
        if part_rem is None:
            part_rem = self.eta_for_phase(self.phase)
        return float(part_rem) + left_parts * self.part_budget_sec

    def begin_part(self, part_index: int, phase: str) -> None:
        self.current_part_index = int(part_index)
        self.set_phase(phase)

    def mark_part_done(self, part_index: int) -> None:
        self.parts_completed = max(self.parts_completed, int(part_index) + 1)
        self.set_phase("pack")

    def overall_pct(self) -> int:
        """Грубая доля для полоски (не главный UI-сигнал)."""
        prep_f = float(self.cfg.prep_fraction)
        if self.phase == "prep":
            return max(1, min(2, int(prep_f * 100 * 0.5) or 1))
        base = prep_f
        per_part = (1.0 - prep_f) / float(self.n_parts)
        done = float(self.parts_completed) * per_part
        within = 0.0
        if self.phase == "diar":
            within = per_part * float(self.cfg.diar_fraction) * 0.5
        elif self.phase == "asr":
            within = per_part * (
                float(self.cfg.diar_fraction) + float(self.cfg.asr_fraction) * 0.5
            )
        elif self.phase == "pack":
            within = per_part * 0.95
        elif self.phase == "eos":
            return 96
        elif self.phase == "titles":
            return 98
        elif self.phase == "done":
            return 100
        if self.parts_completed <= self.current_part_index:
            done = float(self.current_part_index) * per_part
        pct = int(round((base + done + within) * 100))
        return max(1, min(99, pct))

    def label_ru(self, phase: str | None = None) -> str:
        phase = phase or self.phase
        n = self.n_parts
        i = self.current_part_index + 1
        if phase == "prep":
            return "Подготовка аудио и VAD"
        if phase == "diar":
            return f"Диаризация: фрагмент {i} из {n}"
        if phase == "asr":
            return f"Распознавание речи: фрагмент {i} из {n}"
        if phase == "pack":
            return f"Сборка глав: фрагмент {i} из {n}"
        if phase == "eos":
            return "Уточнение спикеров (финал)"
        if phase == "titles":
            if self.title_index is not None and self.title_total is not None:
                base = (
                    f"Генерация названий: глава {self.title_index} "
                    f"из {self.title_total}"
                )
                if self.parts_completed < self.n_parts:
                    return f"{base} · фрагмент {i} из {n}"
                return base
            if self.parts_completed < self.n_parts:
                return f"Генерация названий глав · фрагмент {i} из {n}"
            return "Генерация названий глав"
        if phase == "done":
            return "Готово"
        return "Обработка"
