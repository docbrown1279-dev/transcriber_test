#!/usr/bin/env python3
"""Parser and frozen-metadata checks for Stage 3. No model load."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stage3_llm import (  # noqa: E402
    assert_frozen,
    chapter_row,
    extract_json_object,
    parse_oneshot,
    parse_points,
    parse_title,
)


def main() -> None:
    think_wrapped = (
        "<think>\nplan\n</think>\n"
        '{"title":"Подключение через паркинг","key_points":["Канализация через паркинг"],'
        '"actions":[],"open_questions":[],"asr_notes":[]}'
    )
    oneshot = parse_oneshot(think_wrapped)
    assert oneshot is not None
    assert oneshot["title"] == "Подключение через паркинг"
    assert oneshot["key_points"] == ["Канализация через паркинг"]

    points_only = parse_points(
        '```json\n{"key_points":["10 кВт на квартиру","Ждём экспертизу"],'
        '"actions":["Уточнить у ресурсника"],"open_questions":[],"asr_notes":["касторография"]}\n```'
    )
    assert points_only is not None
    assert len(points_only["key_points"]) == 2
    assert points_only["actions"] == ["Уточнить у ресурсника"]
    assert points_only["asr_notes"] == ["касторография"]

    title = parse_title('{"title":"Десять двенадцать киловатт на квартиру и ещё лишние слова сверх лимита"}')
    assert title is not None
    assert len(title.split()) <= 10

    assert extract_json_object("not json") is None
    assert parse_oneshot("не JSON") is None

    chapter = {
        "id": 0,
        "start": 9.970344,
        "end": 118.729719,
        "source_ids": [0, 1],
        "speakers": ["SPEAKER_02"],
        "text": "dummy",
    }
    row = chapter_row(chapter, oneshot)
    assert_frozen(chapter, row)
    assert "start" in row and row["start"] == 9.970344
    print(json.dumps({"ok": True, "title_words": len(title.split())}))


if __name__ == "__main__":
    main()
