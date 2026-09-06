"""D3 prompt loading and substitution tests."""

import pytest

from transcriber.llm.prompts import load_prompt, render_prompt


def test_d3_prm_01_leftover_placeholder_raises() -> None:
    """[D3-PRM-01] An unresolved named placeholder fails loudly."""
    with pytest.raises(ValueError, match="Unresolved"):
        render_prompt("Текст {{required}}", {})


def test_d3_prm_01_frozen_extract_prompt_renders() -> None:
    """[D3-PRM-01] Every runtime placeholder in the frozen extract prompt is replaced."""
    rendered = render_prompt(
        load_prompt("prompts/meeting_insights/v1_extract.md"),
        {
            "chapter_id": "C00",
            "title": "Сроки",
            "start": "1.000",
            "end": "2.000",
            "chapter_text": "A: срок 10 дней",
            "src_catalog": "s0001 | 1.000-2.000 | A",
        },
    )
    assert "{{chapter_id}}" not in rendered
    assert "срок 10 дней" in rendered
