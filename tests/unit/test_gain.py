"""Тесты расчета линейного усиления звука (gain)."""

from transcriber.audio.gain import calculate_gain


def test_d1_gain_01_rms_at_or_above_threshold() -> None:
    """[D1-GAIN-01] RMS at/above threshold -> gain_db=0, gain_applied=false."""
    # Точно на пороге (-30.0 dBFS)
    res_exact = calculate_gain(
        rms_dbfs=-30.0,
        peak_dbfs=-5.0,
        threshold_dbfs=-30.0,
    )
    assert res_exact.gain_db == 0.0
    assert res_exact.gain_applied is False

    # Выше порога (-25.0 dBFS > -30.0 dBFS)
    res_above = calculate_gain(
        rms_dbfs=-25.0,
        peak_dbfs=-2.0,
        threshold_dbfs=-30.0,
    )
    assert res_above.gain_db == 0.0
    assert res_above.gain_applied is False


def test_d1_gain_02_rms_below_threshold_and_clamping() -> None:
    """[D1-GAIN-02] RMS below threshold -> positive gain, clamped by max_gain and peak ceiling."""
    # Стандартный случай: raw gain 7 dB, peak -12 + 7 = -5 <= -1 ceiling
    res_normal = calculate_gain(
        rms_dbfs=-35.0,
        peak_dbfs=-12.0,
        threshold_dbfs=-30.0,
        target_dbfs=-28.0,
        max_gain_db=18.0,
        peak_ceiling_dbfs=-1.0,
    )
    assert res_normal.gain_db == 7.0
    assert res_normal.gain_applied is True

    # Ограничение по пиковому потолку (peak ceiling):
    # raw gain: -23 - (-35) = 12 dB. Peak -4 + 12 = 8 > -1.
    # Clamped gain: -1 - (-4) = 3 dB.
    res_ceiling = calculate_gain(
        rms_dbfs=-35.0,
        peak_dbfs=-4.0,
        threshold_dbfs=-30.0,
        target_dbfs=-23.0,
        max_gain_db=18.0,
        peak_ceiling_dbfs=-1.0,
    )
    assert res_ceiling.gain_db == 3.0
    assert res_ceiling.gain_applied is True

    # Ограничение по max_gain:
    # raw gain: -23 - (-55) = 32 dB. Max gain = 18 dB.
    res_max = calculate_gain(
        rms_dbfs=-55.0,
        peak_dbfs=-25.0,
        threshold_dbfs=-30.0,
        target_dbfs=-23.0,
        max_gain_db=18.0,
        peak_ceiling_dbfs=-1.0,
    )
    assert res_max.gain_db == 18.0
    assert res_max.gain_applied is True
