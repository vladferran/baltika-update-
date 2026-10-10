"""Звания по стажу и расширенные настройки / периоды в API приложения."""

from __future__ import annotations

from datetime import date

from app import ranks as rk
from app import shuttle as sh
from app.webapp import parse_range, parse_settings


# ---------- настройки бота в приложении ----------

def test_choice_settings_accept_only_bot_values():
    assert parse_settings({"notify_soon_h": 3}) == {"notify_soon_h": 3}
    assert parse_settings({"notify_home_min": 80}) == {"notify_home_min": 80}
    assert parse_settings({"notify_soon_h": 5}) is None
    assert parse_settings({"clean_after_min": 45}) is None
    assert parse_settings({"sarcasm": 4}) is None


def test_bool_not_accepted_as_choice():
    assert parse_settings({"notify_soon_h": True}) is None
    assert parse_settings({"sarcasm": False}) is None


def test_clean_zero_switches_autoclean_off():
    assert parse_settings({"clean_after_min": 0}) == {"clean_after_min": 0, "autoclean": False}
    assert parse_settings({"clean_after_min": 180}) == {"clean_after_min": 180, "autoclean": True}


def test_route_none_clears_route_and_known_key_is_kept():
    assert parse_settings({"shuttle_route": "none"}) == {"shuttle_route": None}
    key = next(iter(sh.ROUTES))
    assert parse_settings({"shuttle_route": key}) == {"shuttle_route": key}
    assert parse_settings({"shuttle_route": "moon"}) is None


def test_unknown_fields_still_ignored_when_valid_ones_present():
    assert parse_settings({"hack": 1, "sarcasm": 2}) == {"sarcasm": 2}


# ---------- периоды отпуска и больничного ----------

def test_range_defaults_finish_to_start():
    assert parse_range({"start": "2026-10-10"}) == (date(2026, 10, 10), date(2026, 10, 10))


def test_range_swaps_reversed_dates():
    assert parse_range({"start": "2026-10-20", "finish": "2026-10-10"}) == (
        date(2026, 10, 10), date(2026, 10, 20))


def test_range_rejects_bad_and_too_long_input():
    assert parse_range({"start": "10.10.2026"}) is None          # формат не ISO
    assert parse_range({}) is None
    assert parse_range({"start": "2026-01-01", "finish": "2026-12-31"}) is None
    assert parse_range(["2026-10-10"]) is None
    assert parse_range({"start": "1900-01-01"}) is None           # слишком давно
