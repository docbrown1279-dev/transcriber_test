"""Тесты алгоритма оценки доли русских слов и поиска латиницы."""

from transcriber.models.artifacts import TranscriptSegment
from transcriber.quality.ru_ratio import count_latin_characters, russian_word_ratio


def test_d0_ru_01_handwritten_strings_and_normalization() -> None:
    """[D0-RU-01] ratio on hand-written strings: pure Russian -> 1.0; half latin -> 0.5; digits and punctuation excluded; ё/е equivalent; tokens of one character ignored."""
    # Чистый русский
    pure_ru = russian_word_ratio("Привет, мир! Как ваши дела?")
    assert pure_ru.ratio == 1.0
    assert pure_ru.latin_chars == 0

    # Половина латиницы
    half_latin = russian_word_ratio("Привет world")
    assert half_latin.ratio == 0.5
    assert half_latin.total_words == 2
    assert half_latin.russian_words == 1

    # Числа и пунктуация исключены
    with_numbers = russian_word_ratio("Привет, 12345! world ... ???")
    assert with_numbers.ratio == 0.5
    assert with_numbers.total_words == 2

    # Эквивалентность ё и е
    yo_test = russian_word_ratio("Зелёная ёлка растет")
    assert yo_test.ratio == 1.0

    # Токены из одного символа игнорируются
    one_char = russian_word_ratio("я и ты в лес")
    # "я", "и", "в" - 1 символ (игнор), "ты" (2), "лес" (3) -> 2 слова, оба русские
    assert one_char.ratio == 1.0
    assert one_char.total_words == 2


def test_d0_ru_02_empty_segments_and_latin_contamination() -> None:
    """[D0-RU-02] empty segments contribute nothing and do not divide by zero; latin counter finds DimaTorzok-style contamination."""
    empty_res = russian_word_ratio("")
    assert empty_res.ratio == 1.0
    assert empty_res.total_words == 0

    segments = [
        TranscriptSegment(
            id="s0001",
            turn_id="t0001",
            start=0.0,
            end=1.0,
            speaker="S1",
            text="   ",
            empty=True,
        ),
        TranscriptSegment(
            id="s0002",
            turn_id="t0001",
            start=1.0,
            end=2.0,
            speaker="S1",
            text="",
            empty=True,
        ),
        TranscriptSegment(
            id="s0003",
            turn_id="t0001",
            start=2.0,
            end=3.0,
            speaker="S1",
            text="Хороший день",
            empty=False,
        ),
    ]
    seg_res = russian_word_ratio(segments)
    assert seg_res.ratio == 1.0
    assert seg_res.total_words == 2

    # Проверка поиска латиницы DimaTorzok
    latin_count = count_latin_characters("Пользователь DimaTorzok подключился")
    assert latin_count == 10  # D-i-m-a-T-o-r-z-o-k
