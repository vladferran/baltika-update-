"""Настройка графика из приложения: проверка входных данных и пресеты."""

from datetime import date, timedelta

from app import schedule as sch
from app.webapp import parse_setup


def test_only_baltika_preset_left():
    assert list(sch.PRESETS) == ["baltika"]
    assert sch.PRESETS["baltika"][0] == "ДДВННВВВ"


def test_setup_accepts_custom_pattern_and_normalizes_it():
    out = parse_setup({"pattern": "ddvnnvvv", "anchor": "2026-10-10"})
    assert out == {"pattern": "ДДВННВВВ", "anchor": date(2026, 10, 10)}


def test_setup_rejects_bad_input():
    assert parse_setup({"pattern": "XYZ", "anchor": "2026-10-10"}) is None
    assert parse_setup({"pattern": "ДДВ", "anchor": "не дата"}) is None
    assert parse_setup({"pattern": "ДДВ"}) is None
    assert parse_setup(["ДДВ"]) is None


def test_setup_rejects_anchor_far_from_today():
    far = (date.today() + timedelta(days=800)).isoformat()
    assert parse_setup({"pattern": "ДДВ", "anchor": far}) is None
