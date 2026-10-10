"""Зал, бассейн, сауна: кому и когда можно сходить.

Правило заведения: по чётным числам месяца — женский день, по нечётным —
мужской. Сходить можно, только если день свободен по графику (выходной
или отпуск) и день подходит полу посетителя. Отпуск в ShiftConfig.kind
уже считается выходным, поэтому отдельной логики для него нет.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import schedule as sch

MEN = "m"
WOMEN = "w"
# Владелец бота — мужчина, поэтому в его мужские дни (нечётные числа) заведение открыто.
USER_GENDER = MEN

GENDER_LABEL = {MEN: "мужской", WOMEN: "женский"}
ZONES = (
    ("gym", "Зал", "🏋️"),
    ("pool", "Бассейн", "🏊"),
    ("sauna", "Сауна", "🧖"),
)
STATE_OPEN = "open"        # свободный день и подходящий пол — можно сходить
STATE_OTHER = "other"      # свободный день, но чужой пол
STATE_SHIFT = "shift"      # день на смене, не до спорта


def day_gender(d: date) -> str:
    """Чётное число — женский день, нечётное — мужской."""
    return WOMEN if d.day % 2 == 0 else MEN


def access(cfg: sch.ShiftConfig, d: date, gender: str = USER_GENDER) -> dict:
    """Статус одного дня для конкретного посетителя."""
    gen = day_gender(d)
    if cfg.kind(d) in sch.WORK:
        state = STATE_SHIFT
    elif gen != gender:
        state = STATE_OTHER
    else:
        state = STATE_OPEN
    return {
        "date": d.isoformat(),
        "gender": gen,
        "gender_label": GENDER_LABEL[gen],
        "state": state,
        "open": state == STATE_OPEN,
        "zones": [{"key": k, "title": t, "emoji": e} for k, t, e in ZONES],
    }


def notify_text(d: date) -> str:
    """Текст уведомления в мужской выходной: кратко и с чёрным юмором."""
    return (
        f"🏋️ <b>Мужской выходной ({d:%d.%m})</b>\n\n"
        "Зал, бассейн и сауна открыты для тебя. "
        "Смена за тебя пока не отработает, так что иди, пока сам не вспомнил о диване."
    )
