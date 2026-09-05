"""Расчет параметров линейного усиления громкости (gain) согласно контракту."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GainResult:
    """Результат расчета коэффициента усиления."""

    gain_db: float
    gain_applied: bool


def calculate_gain(
    rms_dbfs: float,
    peak_dbfs: float,
    threshold_dbfs: float = -30.0,
    target_dbfs: float = -23.0,
    max_gain_db: float = 18.0,
    peak_ceiling_dbfs: float = -1.0,
) -> GainResult:
    """Вычисляет величину линейного усиления audio.

    Линейное усиление применяется только если rms_dbfs < threshold_dbfs.
    gain_db = min(target_dbfs - rms_dbfs, max_gain_db) и ограничивается так,
    чтобы peak_dbfs + gain_db <= peak_ceiling_dbfs.
    """
    if rms_dbfs >= threshold_dbfs:
        return GainResult(gain_db=0.0, gain_applied=False)

    raw_gain = target_dbfs - rms_dbfs
    gain = min(raw_gain, max_gain_db)

    # Ограничение по пиковому потолку
    if peak_dbfs + gain > peak_ceiling_dbfs:
        gain = peak_ceiling_dbfs - peak_dbfs

    gain = max(0.0, round(gain, 3))
    applied = gain > 0.0
    return GainResult(gain_db=gain, gain_applied=applied)
