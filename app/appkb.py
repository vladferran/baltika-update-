"""Кнопки, которые открывают Mini App прямо из чата.

Отметка смены и просмотр данных теперь только в приложении: в сообщениях
бота остаётся кнопка перехода, а старые кнопки «Вышел/Больничный» больше
ничего не меняют.
"""

from __future__ import annotations

import os

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://baltikbot.ru/")
APP_TEXT = "📱 Открыть в приложении"
ATTEND_TEXT = "✅ Отметиться в приложении"


def app_button(text: str = APP_TEXT) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=WEBAPP_URL))


def has_app_button(markup: InlineKeyboardMarkup | None) -> bool:
    if markup is None:
        return False
    return any(btn.web_app is not None for row in markup.inline_keyboard for btn in row)


def with_app(markup: InlineKeyboardMarkup | None = None) -> InlineKeyboardMarkup:
    """Добавляет последней строкой кнопку приложения, если её ещё нет."""
    if has_app_button(markup):
        return markup
    rows = [list(r) for r in markup.inline_keyboard] if markup else []
    rows.append([app_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def app_only_kb(text: str = APP_TEXT) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[app_button(text)]])
