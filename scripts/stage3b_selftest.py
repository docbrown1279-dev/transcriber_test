#!/usr/bin/env python3
"""Parser checks for Stage 3b. No network, no model load."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stage3b_insights import (  # noqa: E402
    match_src,
    parse_insights,
    parse_verdict,
    redact,
    render_insight_md,
)


def main() -> None:
    raw = (
        "<think>plan</think>\n"
        "```markdown\n"
        "# Канализация через паркинг\n\n"
        "<!-- chapter: D00 -->\n"
        "<!-- clock_json: 99:99:99.00-99:99:99.00 -->\n\n"
        "- kind: fact\n"
        "  src: [00:00:21.77-00:00:46.77 | SPEAKER_02 | D00]\n"
        "  text: канализация через паркинг по точкам подключения\n"
        "```\n"
    )
    title, insights, empty = parse_insights(raw)
    assert title == "Канализация через паркинг"
    assert empty is False
    assert insights[0]["kind"] == "fact"
    assert "00:00:21.77" in insights[0]["src"]

    allowed = ["[00:00:21.77-00:00:46.77 | SPEAKER_02 | D00]"]
    assert match_src("00:00:21.77-00:00:46.77", allowed) == allowed[0]
    assert match_src(allowed[0], allowed) == allowed[0]
    assert match_src("[99:99:99.00-99:99:99.00 | X]", allowed) is None

    rendered = render_insight_md(
        title,
        "D00",
        "00:00:09.97-00:01:58.73",
        insights,
        allowed,
        False,
    )
    assert rendered.startswith("# Канализация через паркинг")
    assert "<!-- clock_json: 00:00:09.97-00:01:58.73 -->" in rendered
    assert "99:99:99" not in rendered
    assert rendered.splitlines()[0].startswith("# ")

    empty_md = render_insight_md("вне глав", "D_unassigned", "", [], [], True)
    assert "нет инсайтов" in empty_md

    none_title, none_insights, none_empty = parse_insights("# Тишина\n\nнет инсайтов\n")
    assert none_title == "Тишина"
    assert none_empty is True
    assert none_insights == []

    assert parse_verdict("мелочи\nverdict: usable\n") == "usable"
    assert parse_verdict("verdict: not_usable") == "not_usable"
    assert parse_verdict("нет вердикта") is None

    previous = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = "secret-test-key-value"
    leaked = redact("url?key=secret-test-key-value Authorization: Bearer abc HTTP 401")
    assert "secret-test-key-value" not in leaked
    assert "Bearer abc" not in leaked
    assert "REDACTED" in leaked
    if previous is None:
        del os.environ["GEMINI_API_KEY"]
    else:
        os.environ["GEMINI_API_KEY"] = previous
    print("stage3b_selftest ok")


if __name__ == "__main__":
    main()
