"""Tests for title constraints from prompt P1."""

from transcriber.llm.titles import title_validation_error


def test_d2_q_02_rejects_overlong_and_stamp_titles() -> None:
    """[D2-Q-02] Titles over ten words or with stamp prefixes fail validation."""
    overlong = "один два три четыре пять шесть семь восемь девять десять одиннадцать"
    assert title_validation_error(overlong, 10) is not None
    assert title_validation_error("Обсуждение инженерных сетей", 10) is not None


def test_d2_q_03_rejects_empty_and_duplicate_titles() -> None:
    """[D2-Q-03] Empty and case-insensitive duplicate titles fail validation."""
    assert title_validation_error("", 10) is not None
    assert title_validation_error("Инженерные сети", 10, {"инженерные сети"}) is not None
    assert title_validation_error("Планировочные решения", 10, {"инженерные сети"}) is None
