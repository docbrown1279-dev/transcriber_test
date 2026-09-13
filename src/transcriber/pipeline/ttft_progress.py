"""Оценка ETA для TTFT file-split (простая таблица долей)."""

from __future__ import annotations

from dataclasses import dataclass

from transcriber.config.schema import TtftProgressConfig


def format_eta_ru(seconds: float | None) -> str | None:
    """Человекочитаемый ориентир: «ориентир ~2 мин»."""
    if seconds is None:
        return None
    total = max(0, int(round(float(seconds))))
    if total < 5:
        return "ориентир < 5 с"
    if total < 60:
        return f"ориентир ~{total} с"
    minutes = max(1, int(round(total / 60.0)))
    if minutes < 60:
        return f"ориентир ~{minutes} мин"
    hours, rem = divmod(minutes, 60)
    if rem == 0:
        return f"ориентир ~{hours} ч"
    return f"ориентир ~{hours} ч {rem} мин"


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

    def remember_prep(self, prep_wall_sec: float, n_parts: int) -> None:
        self.prep_wall_sec = max(0.0, float(prep_wall_sec))
        self.n_parts = max(1, int(n_parts))
        self.phase = "prep"

    @property
    def total_est_sec(self) -> float:
        frac = float(self.cfg.prep_fraction)
        if frac <= 1e-9:
            return self.prep_wall_sec
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
            # Cheap AHC on saved vectors — small slice of one part pack budget
            return max(5.0, self.part_budget_sec * 0.05)
        if phase == "titles":
            return max(15.0, self.part_budget_sec * 0.15)
        if phase == "prep":
            return max(0.0, self.prep_wall_sec) if self.prep_wall_sec else 30.0
        return budget

    def begin_part(self, part_index: int, phase: str) -> None:
        self.current_part_index = int(part_index)
        self.phase = phase

    def mark_part_done(self, part_index: int) -> None:
        self.parts_completed = max(self.parts_completed, int(part_index) + 1)
        self.phase = "pack"

    def overall_pct(self) -> int:
        """Грубая доля для полоски (не главный UI-сигнал)."""
        prep_f = float(self.cfg.prep_fraction)
        if self.phase == "prep":
            return max(1, min(4, int(prep_f * 100 * 0.5)))
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
            done = 1.0 - prep_f
            within = prep_f * 0.0
            base = 0.92
            return min(96, int(base * 100))
        elif self.phase == "titles":
            return 97
        elif self.phase == "done":
            return 100
        # current part in progress counts partially
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
            return "Генерация названий глав"
        if phase == "done":
            return "Готово"
        return "Обработка"
