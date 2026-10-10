"""Кнопка открытия приложения в сообщениях бота."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app import appkb


def test_with_app_adds_web_app_row_to_empty_message():
    kb = appkb.with_app(None)
    assert appkb.has_app_button(kb)
    assert len(kb.inline_keyboard) == 1
    assert kb.inline_keyboard[0][0].web_app.url == appkb.WEBAPP_URL


def test_with_app_keeps_existing_buttons_and_adds_one_row():
    beer = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🍺 Я за", callback_data="beer:yes:1"),
    ]])
    kb = appkb.with_app(beer)
    assert kb.inline_keyboard[0][0].callback_data == "beer:yes:1"
    assert appkb.has_app_button(kb)
    assert len(kb.inline_keyboard) == 2


def test_with_app_is_idempotent():
    once = appkb.with_app(None)
    twice = appkb.with_app(once)
    assert len(twice.inline_keyboard) == 1


def test_attendance_message_has_only_app_button():
    kb = appkb.app_only_kb(appkb.ATTEND_TEXT)
    buttons = [b for row in kb.inline_keyboard for b in row]
    assert len(buttons) == 1
    assert buttons[0].web_app is not None
    assert buttons[0].callback_data is None
    assert "приложении" in buttons[0].text
