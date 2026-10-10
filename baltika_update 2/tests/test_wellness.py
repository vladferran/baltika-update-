"""Зал, бассейн, сауна: правило чётных и нечётных дней и выходные по графику."""

from __future__ import annotations

from datetime import date

from app import schedule as sch
from app import wellness as wl


def cfg(vacations=()):
    # Анкор: 2026-10-10 — первый день цикла «ДДВННВВВ» (Д).
    return sch.ShiftConfig(pattern="ДДВННВВВ", anchor=date(2026, 10, 10), vacations=tuple(vacations))


def test_even_day_is_women_odd_is_men():
    assert wl.day_gender(date(2026, 10, 10)) == wl.WOMEN
    assert wl.day_gender(date(2026, 10, 11)) == wl.MEN


def test_free_odd_day_is_open_for_man():
    # 2026-10-15: позиция цикла 5 → «В» (выходной), число нечётное
    d = date(2026, 10, 15)
    assert cfg().kind(d) == sch.OFF
    a = wl.access(cfg(), d)
    assert a["state"] == wl.STATE_OPEN and a["open"] is True


def test_free_even_day_is_other_gender():
    # 2026-10-12: выходной, число чётное — женский день
    d = date(2026, 10, 12)
    assert cfg().kind(d) == sch.OFF
    a = wl.access(cfg(), d)
    assert a["state"] == wl.STATE_OTHER and a["open"] is False


def test_shift_day_is_never_open():
    # 2026-10-11: «Д», смена, число нечётное — но на смене не до спорта
    d = date(2026, 10, 11)
    assert cfg().kind(d) in sch.WORK
    a = wl.access(cfg(), d)
    assert a["state"] == wl.STATE_SHIFT and a["open"] is False


def test_vacation_counts_as_free_day():
    # отпуск на 2026-10-11 (нечётное, смена по графику) — становится свободным мужским днём
    d = date(2026, 10, 11)
    c = cfg(vacations=[(date(2026, 10, 11), date(2026, 10, 11))])
    assert wl.access(c, d)["open"] is True


def test_three_zones_listed():
    keys = [z["key"] for z in wl.access(cfg(), date(2026, 10, 15))["zones"]]
    assert keys == ["gym", "pool", "sauna"]
