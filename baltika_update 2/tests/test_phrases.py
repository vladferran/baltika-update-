"""Каждая фраза банка должна собираться с типовым набором плейсхолдеров."""

from __future__ import annotations

import string

from app.phrases import PHRASES, seed_rows

FMT = {"left": "2 ч", "kind": "дневная смена", "when": "08:00", "station": "Парнас",
       "place": "у проходной", "weekend": "3 дн."}


def _fields(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_every_phrase_formats_with_known_fields():
    for cat, lvl, text in seed_rows():
        unknown = _fields(text) - set(FMT)
        assert not unknown, f"{cat}/{lvl}: неизвестный плейсхолдер {unknown}"
        text.format(**FMT)  # не должно упасть


def test_no_duplicates_and_all_levels_present():
    rows = seed_rows()
    assert len(rows) == len(set(rows))
    for cat, levels in PHRASES.items():
        assert set(levels) == {1, 2, 3}, f"{cat}: нужны уровни 1, 2, 3"
