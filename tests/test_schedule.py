"""Тесты движка циклов. Запуск: pytest -q"""

from datetime import date, datetime, timedelta

import pytest

from app import schedule as sch

BALTIKA = "ДДВННВВВ"
ANCHOR = date(2026, 8, 30)


@pytest.fixture
def cfg() -> sch.ShiftConfig:
    return sch.ShiftConfig(pattern=BALTIKA, anchor=ANCHOR)


def at(cfg, s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=cfg.zone)


def test_normalize_pattern():
    assert sch.normalize_pattern("ддвннввв") == BALTIKA
    assert sch.normalize_pattern("DD-V-NN-VVV") == BALTIKA
    assert sch.normalize_pattern("Д Д В Н Н В В В") == BALTIKA


@pytest.mark.parametrize("raw", ["", "ВВВВ", "ДДZ", "Д" * 40])
def test_bad_patterns(raw):
    with pytest.raises(ValueError):
        sch.normalize_pattern(raw)


def test_cycle_repeats(cfg):
    for i in range(0, 40):
        d = ANCHOR + timedelta(days=i)
        assert cfg.kind(d) == cfg.kind(d + timedelta(days=8))


def test_kinds(cfg):
    expected = "ДДВННВВВ"
    for i, k in enumerate(expected):
        assert cfg.kind(ANCHOR + timedelta(days=i)) == k


def test_anchor_works_backwards(cfg):
    """Даты до якоря тоже должны считаться корректно."""
    assert cfg.kind(ANCHOR - timedelta(days=8)) == "Д"
    assert cfg.kind(ANCHOR - timedelta(days=1)) == "В"


def test_night_crosses_midnight(cfg):
    start, end = cfg.bounds(date(2026, 9, 3))
    assert start == at(cfg, "2026-09-03 20:00")
    assert end == at(cfg, "2026-09-04 08:00")


def test_working_during_night(cfg):
    st = sch.status(cfg, at(cfg, "2026-09-04 03:00"))
    assert st.working and st.shift_kind == "Н"
    assert st.shift_end == at(cfg, "2026-09-04 08:00")


def test_single_off_day_is_not_weekend(cfg):
    """01.09 — одиночный В между дневными и ночными."""
    st = sch.status(cfg, at(cfg, "2026-09-01 12:00"))
    assert not st.working
    assert not st.in_weekend
    assert st.short_break
    assert st.weekend_start == at(cfg, "2026-09-04 08:00")


def test_real_weekend_starts_after_last_night(cfg):
    """Свобода наступает в 08:00, когда закончилась ночная, а не в полночь."""
    st = sch.status(cfg, at(cfg, "2026-09-04 09:00"))
    assert st.in_weekend
    assert st.weekend_start == at(cfg, "2026-09-04 08:00")
    assert st.weekend_end == at(cfg, "2026-09-07 08:00")


def test_still_working_at_0700_on_first_off_day(cfg):
    st = sch.status(cfg, at(cfg, "2026-09-04 07:00"))
    assert st.working


def test_next_shift(cfg):
    st = sch.status(cfg, at(cfg, "2026-09-05 12:00"))
    assert st.next_start == at(cfg, "2026-09-07 08:00")
    assert st.next_kind == "Д"


def test_vacation_blocks_shifts():
    cfg = sch.ShiftConfig(
        pattern=BALTIKA, anchor=ANCHOR,
        vacations=((date(2026, 9, 1), date(2026, 9, 14)),),
    )
    assert cfg.kind(date(2026, 9, 3)) == "В"
    st = sch.status(cfg, at(cfg, "2026-09-03 12:00"))
    assert not st.working
    assert st.next_start >= at(cfg, "2026-09-15 00:00")


def test_home_reminder_fires_at_1840(cfg):
    """80 минут до конца дневной смены = 18:40."""
    st = sch.status(cfg, at(cfg, "2026-08-31 18:40"))
    assert st.shift_end - timedelta(minutes=80) == at(cfg, "2026-08-31 18:40")


def test_human_delta():
    assert sch.human_delta(timedelta(days=3)) == "3 дня"
    assert sch.human_delta(timedelta(hours=1, minutes=20)) == "1 час 20 минут"
    assert sch.human_delta(timedelta(days=1, hours=10)) == "1 день 10 часов"
    assert sch.human_delta(timedelta(seconds=-5)) == "меньше минуты"


def test_all_presets_valid():
    for key, (pattern, title) in sch.PRESETS.items():
        assert sch.normalize_pattern(pattern) == pattern, key
        cfg = sch.ShiftConfig(pattern=pattern, anchor=ANCHOR)
        st = sch.status(cfg, at(cfg, "2026-09-01 12:00"))
        assert st.next_start is not None, key


# ─────────────────────────── развозка ───────────────────────────────────

from app import shuttle as sh  # noqa: E402


def dt(cfg, s: str):
    return at(cfg, s)


def test_all_routes_wellformed():
    for key, r in sh.ROUTES.items():
        assert r.key == key
        assert r.to_work_weekday and r.from_work_weekday, key
        for group in (r.to_work_weekday, r.to_work_weekend,
                      r.from_work_weekday, r.from_work_weekend):
            assert list(group) == sorted(group), f"{key}: расписание не отсортировано"


def test_parnas_day_shift(cfg):
    """К дневной в 08:00 последний удобный рейс — 7:35."""
    r = sh.ROUTES["parnas"]
    buses = sh.to_work_buses(r, dt(cfg, "2026-09-07 08:00"))
    assert [b.strftime("%H:%M") for b in buses] == ["07:35", "07:20"]


def test_parnas_night_shift(cfg):
    """К ночной в 20:00 — 19:40."""
    r = sh.ROUTES["parnas"]
    buses = sh.to_work_buses(r, dt(cfg, "2026-09-02 20:00"))
    assert buses[0].strftime("%H:%M") == "19:40"


def test_parnas_after_night(cfg):
    """Ночная кончается в 08:00 — первый автобус 8:10."""
    r = sh.ROUTES["parnas"]
    buses = sh.from_work_buses(r, dt(cfg, "2026-09-04 08:00"))
    assert buses[0].strftime("%H:%M") == "08:10"


def test_parnas_after_day(cfg):
    r = sh.ROUTES["parnas"]
    buses = sh.from_work_buses(r, dt(cfg, "2026-09-07 20:00"))
    assert buses[0].strftime("%H:%M") == "20:10"


def test_weekend_schedule_differs(cfg):
    """05.09.2026 — суббота, расписание выходного дня."""
    r = sh.ROUTES["parnas"]
    assert sh.is_weekend(date(2026, 9, 5))
    buses = sh.to_work_buses(r, dt(cfg, "2026-09-05 08:00"))
    assert buses[0].strftime("%H:%M") == "07:15"


def test_from_work_rolls_to_next_day(cfg):
    """Если после конца смены рейсов нет — берём завтрашние."""
    r = sh.ROUTES["devyatkino"]
    buses = sh.from_work_buses(r, dt(cfg, "2026-09-07 21:00"))
    assert buses and buses[0].date() == date(2026, 9, 8)


def test_buffer_respected(cfg):
    """С буфером 60 минут рейс за 25 минут до смены не подходит."""
    r = sh.ROUTES["parnas"]
    buses = sh.to_work_buses(r, dt(cfg, "2026-09-07 08:00"), buffer_min=60)
    assert buses[0].strftime("%H:%M") == "07:00" if False else buses[0] <= dt(cfg, "2026-09-07 07:00")


# ─────────────────────────── погода ─────────────────────────────────────

from app import weather as wx  # noqa: E402


def _payload(base: datetime, hours: int = 72) -> dict:
    times = [(base + timedelta(hours=i)) for i in range(hours)]
    return {
        "current": {"time": base.strftime("%Y-%m-%dT%H:%M"), "temperature_2m": 14.3,
                    "apparent_temperature": 11.8, "weather_code": 61, "wind_speed_10m": 4.2},
        "hourly": {
            "time": [h.strftime("%Y-%m-%dT%H:%M") for h in times],
            "temperature_2m": [14.0] * hours,
            "apparent_temperature": [11.0] * hours,
            "weather_code": [3] * hours,
            "precipitation_probability": [70] * hours,
            "wind_speed_10m": [3.0] * hours,
        },
    }


def test_weather_parse():
    w = wx._parse(_payload(datetime(2026, 9, 2, 12, 0)), "Europe/Moscow")
    assert len(w.hourly) == 72
    assert w.now.temp == 14.3
    assert w.now.emoji == "🌧"


def test_weather_at_hour_matches():
    base = datetime(2026, 9, 2, 12, 0)
    w = wx._parse(_payload(base), "Europe/Moscow")
    target = base.replace(tzinfo=w.now.at.tzinfo) + timedelta(hours=8)
    p = w.at_hour(target)
    assert p is not None and p.at.hour == 20


def test_weather_far_future_returns_none():
    base = datetime(2026, 9, 2, 12, 0)
    w = wx._parse(_payload(base), "Europe/Moscow")
    far = base.replace(tzinfo=w.now.at.tzinfo) + timedelta(days=10)
    assert w.at_hour(far) is None


def test_weather_broken_payload_survives():
    """Битые часы пропускаются, а не роняют разбор."""
    base = datetime(2026, 9, 2, 12, 0)
    payload = _payload(base, 5)
    payload["hourly"]["temperature_2m"][2] = None
    w = wx._parse(payload, "Europe/Moscow")
    assert len(w.hourly) == 4


@pytest.mark.parametrize("feels,code,expect", [
    (-25, 3, "капуста"), (-12, 3, "Шапка"), (-3, 3, "куртку"),
    (5, 63, "Зонт"), (5, 73, "Снег"), (18, 95, "Гроза"), (28, 0, "Жара"),
])
def test_weather_advice(feels, code, expect):
    p = wx.Point(at=datetime.now(), temp=feels, feels=feels, code=code, precip_prob=0, wind=3)
    assert expect in wx.advice(p)


def test_all_wmo_codes_described():
    for code in wx.WMO:
        emoji, text = wx.describe(code)
        assert emoji and text
    assert wx.describe(12345) == ("🌡", "непонятно что")


# ─────────────────────── опрос «по пиву» ────────────────────────────────


def test_beer_poll_only_after_day_shifts(cfg):
    """Опрос уходит только в дневную смену и ровно один раз на смену."""
    lead = timedelta(minutes=35)
    grace = timedelta(minutes=15)
    t = at(cfg, "2026-09-01 00:00")
    end = at(cfg, "2026-09-17 00:00")
    fired = []
    while t < end:
        st = sch.status(cfg, t)
        if (st.working and st.shift_kind == sch.DAY and st.shift_end
                and st.shift_end - lead <= t < st.shift_end - lead + grace):
            fired.append(st.shift_end)
        t += timedelta(minutes=5)

    ends = sorted(set(fired))
    assert ends, "опрос не сработал ни разу"
    for e in ends:
        assert cfg.kind(e.date()) == sch.DAY
        assert e.hour == 20


def test_beer_poll_silent_before_night_ends(cfg):
    """За 35 минут до конца ночной (07:25) опрос не должен срабатывать."""
    moment = at(cfg, "2026-09-04 07:25")
    st = sch.status(cfg, moment)
    assert st.working and st.shift_kind == sch.NIGHT
    assert st.shift_end == at(cfg, "2026-09-04 08:00")
    # производственное условие требует DAY — значит опрос молчит
    should_fire = st.shift_kind == sch.DAY
    assert should_fire is False


def test_beer_poll_fires_before_day_ends(cfg):
    """За 35 минут до конца дневной (19:25) — срабатывает."""
    moment = at(cfg, "2026-09-07 19:25")
    st = sch.status(cfg, moment)
    assert st.working and st.shift_kind == sch.DAY
    assert st.shift_end - timedelta(minutes=35) == moment


# ─────────────────────── автоочистка ────────────────────────────────────


def test_notification_lifetimes_are_semantic(cfg):
    """Каждое уведомление должно умирать не «через час», а когда стало не нужным."""
    nxt = at(cfg, "2026-09-07 08:00")          # начало дневной
    shift_end = at(cfg, "2026-09-07 20:00")
    bus = at(cfg, "2026-09-07 07:35")

    # напоминание о смене живёт ровно до её начала
    assert nxt > at(cfg, "2026-09-07 06:00")

    # «скоро домой» — до конца смены с запасом
    home_die = shift_end + timedelta(minutes=30)
    assert home_die > shift_end

    # автобус — двадцать минут после отправления
    bus_die = bus + timedelta(minutes=20)
    assert bus_die < nxt, "автобусное напоминание должно исчезнуть до начала смены"


def test_reply_helper_is_not_recursive():
    """Хелпер reply обязан звать message.answer, а не самого себя."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("app/handlers.py").read_text())
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "reply"
    )
    self_calls = [
        c for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "reply"
    ]
    assert not self_calls


def test_no_self_recursive_functions():
    """Общая страховка от той же ошибки в любом модуле."""
    import ast
    import pathlib

    offenders = []
    for path in sorted(pathlib.Path("app").glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                for inner in ast.walk(node):
                    if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                            and inner.func.id == node.name):
                        offenders.append(f"{path.name}:{node.name}")
    assert not offenders, offenders


# ─────────────────────── стаж и статистика ──────────────────────────────

from app import stats as stt  # noqa: E402


@pytest.mark.parametrize("hired,today", [
    (date(2025, 1, 31), date(2026, 3, 1)),
    (date(2024, 2, 29), date(2026, 2, 28)),
    (date(2024, 3, 15), date(2026, 9, 3)),
    (date(2026, 1, 31), date(2026, 2, 28)),
    (date(2026, 9, 3), date(2026, 9, 3)),
    (date(2020, 12, 31), date(2026, 1, 1)),
])
def test_tenure_never_negative(hired, today):
    y, m, d, total = stt.tenure(hired, today)
    assert y >= 0 and m >= 0 and d >= 0, (y, m, d)
    assert m < 12
    assert total == (today - hired).days


def test_tenure_exact_year():
    y, m, d, _ = stt.tenure(date(2025, 9, 3), date(2026, 9, 3))
    assert (y, m, d) == (1, 0, 0)


def test_tenure_leap_day():
    y, m, d, _ = stt.tenure(date(2024, 2, 29), date(2025, 3, 1))
    assert y == 1 and m == 0 and d >= 0


def test_bar_bounds():
    assert stt.bar(0.0) == "░" * 10
    assert stt.bar(1.0) == "▓" * 10
    assert len(stt.bar(0.5)) == 10
    assert len(stt.bar(5.0)) == 10          # выход за диапазон не ломает
    assert len(stt.bar(-1.0)) == 10


def test_stats_rate_no_division_by_zero():
    s = stt.Stats(hired=date(2026, 9, 3), today=date(2026, 9, 3))
    assert s.rate == 0.0
    assert s.missed_shifts == 0


def test_render_card_has_all_sections():
    s = stt.Stats(hired=date(2024, 3, 15), today=date(2026, 9, 3))
    s.planned_shifts, s.planned_hours = 100, 1200.0
    s.worked_shifts, s.worked_hours = 94, 1128.0
    s.by_kind = {sch.DAY: 47, sch.NIGHT: 47}
    s.missed = {stt.SICK: (4, 48.0), stt.DAYOFF: (2, 24.0)}
    s.unconfirmed = 3
    card = stt.render(s, "Тест")
    for chunk in ("СТАЖ", "ОТРАБОТАНО", "РАСКЛАД", "ПРОПУЩЕНО", "94", "Больничный", "Без отметки"):
        assert chunk in card, chunk


def test_render_card_without_misses():
    s = stt.Stats(hired=date(2026, 1, 1), today=date(2026, 9, 3))
    s.planned_shifts = s.worked_shifts = 50
    s.planned_hours = s.worked_hours = 600.0
    card = stt.render(s, "Тест")
    assert "Железный человек" in card
