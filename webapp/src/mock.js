/* ВЫМЫШЛЕННЫЕ ДАННЫЕ — только для просмотра и правок интерфейса. */
(function () {
  const HOUR = 3600e3;
  const MSK = (ms) => new Date(ms + 3 * HOUR).toISOString().slice(0, 19) + "+03:00";
  const PATTERN = "ДДВННВВВ";
  const DAYS = 42;
  const todayMsk = new Date(Date.now() + 3 * HOUR).toISOString().slice(0, 10);
  const shiftOn = (date, hhmm) => `${date}T${hhmm}:00+03:00`;
  const plusDay = (date, n) => new Date(Date.parse(date + "T00:00:00Z") + n * 24 * HOUR).toISOString().slice(0, 10);

  function calendar() {
    const out = [];
    for (let i = 0; i < DAYS; i++) {
      const date = plusDay(todayMsk, i);
      const kind = PATTERN[i % 8];
      const wd = new Date(date + "T12:00:00Z").getUTCDay();
      const weekend = wd === 0 || wd === 6;
      let start = null, end = null;
      if (kind === "Д") { start = shiftOn(date, "08:00"); end = shiftOn(date, "20:00"); }
      if (kind === "Н") { start = shiftOn(date, "20:00"); end = shiftOn(plusDay(date, 1), "08:00"); }
      const dd = Number(date.slice(8, 10));
      const gender = dd % 2 ? "m" : "w";
      const wellness = kind === "В" ? (gender === "m" ? "open" : "other") : "shift";
      out.push({date, kind, weekend, start, end, wellness, gender});
    }
    return out;
  }

  const ROUTES = [
    {key: "parnas", station: "Парнас", title: "Парнас → завод", to: ["06:10", "07:10", "07:40", "08:00"], from: ["20:10", "20:40", "21:10"]},
    {key: "prosvet", station: "Пр. Просвещения", title: "Пр. Просвещения → завод", to: ["06:30", "07:30", "08:10"], from: ["20:20", "21:00"]},
    {key: "grazhdanka", station: "Гражданский пр.", title: "Гражданский пр. → завод", to: ["06:00", "07:00", "07:50"], from: ["20:05", "20:50"]},
    {key: "devyatkino", station: "Девяткино", title: "Девяткино → завод", to: ["05:50", "06:50", "07:20"], from: ["20:00", "20:30", "21:15"]},
  ];

  function state() {
    const now = Date.now();
    const start = now - 2 * HOUR;
    const end = start + 12 * HOUR;
    const mineKey = "parnas";
    const routes = ROUTES.map(r => ({
      key: r.key, station: r.station, title: r.title,
      to_work_today: r.to, from_work_today: r.from,
      is_weekend: false, is_mine: r.key === mineKey,
    }));
    const mine = routes.find(r => r.is_mine);
    return {
      name: "Владислав",
      sarcasm: true,
      today: todayMsk,
      status: {
        working: true, shift_kind: "Д",
        shift_start: MSK(start), shift_end: MSK(end),
        next_start: MSK(end + 12 * HOUR), next_kind: "Н",
        in_weekend: false, short_break: false,
        weekend_start: null, weekend_end: null,
      },
      calendar: calendar(),
      shuttle: {
        mine: {...mine, next_to_work: [], next_from_work: [MSK(end + 10 * 60e3), MSK(end + 40 * 60e3), MSK(end + 70 * 60e3)]},
        routes,
      },
      beer: {event_id: 1, place: "магазинчик у проходной", yes_names: ["Иван", "Сергей"], yes_count: 2, my_vote: null},
      stats: {
        hired: "2019-03-15", years: 7, months: 6, days: 12, total_days: 2760,
        planned_shifts: 120, worked_shifts: 112, worked_hours: 1344.0,
        missed_shifts: 3, missed_hours: 36.0, unconfirmed: 2, rate: 0.93,
      },
      vacations: [{id: 1, start: plusDay(todayMsk, 12), finish: plusDay(todayMsk, 25), note: null}],
      wellness: {
        date: todayMsk, gender: "m", gender_label: "мужской", state: "shift", open: false,
        zones: [{key: "gym", title: "Зал", emoji: "🏋️"}, {key: "pool", title: "Бассейн", emoji: "🏊"}, {key: "sauna", title: "Сауна", emoji: "🧖"}],
      },
      weather: {line: "−4°, снег, ветер 5 м/с", advice: "Куртка обязательна, шапка тоже"},
      settings: {
        notify_d2: true, notify_d1: true, notify_freedom: true, notify_checkin: true,
        beer_enabled: true, show_weather: true, autoclean: true,
        notify_soon_h: 2, notify_home_min: 80, notify_bus_min: 30, clean_after_min: 180,
        sarcasm: 2, shuttle_route: "parnas",
      },
    };
  }

  const realFetch = window.fetch.bind(window);
  window.fetch = async function (url, opts) {
    const json = (obj) => new Response(JSON.stringify(obj), {status: 200, headers: {"Content-Type": "application/json"}});
    if (String(url).startsWith("/api/state")) return json(state());
    if (String(url).startsWith("/api/")) return json({ok: true});
    return realFetch(url, opts);
  };
})();
