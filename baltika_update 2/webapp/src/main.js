/* Telegram Mini App «Балтика · смены». Данные только из /api/state. */
import "./styles.css";
import { animate } from "motion";
import { api, tg, ready } from "./api.js";
import { mugSvg } from "./mug.js";
import * as fx from "./fx.js";

const LK_URL = "https://lk.baltika.com/";
const TITLES = { shift: "Смена", schedule: "График", shuttle: "Развозка", stats: "Стаж", more: "Ещё" };
const ORDER = ["shift", "schedule", "shuttle", "stats", "more"];
const TAB_COLOR = { shift: "#3b82f6", schedule: "#7b5cff", shuttle: "#14b8a6", stats: "#ff5b6e", more: "#ec4899" };
const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const MONTHS_FULL = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
const MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
const WD = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
const WD_FULL = ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"];
const WEEK_MON = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];
const KIND = { "Д": { cls: "day", label: "День" }, "Н": { cls: "night", label: "Ночь" }, "В": { cls: "off", label: "Выходной" } };
/* Настройки: те же поля и те же значения, что в команде /nastroiki бота */
const SWITCHES = [
  ["notify_d2", "За 2 дня до смены"],
  ["notify_d1", "За сутки до смены"],
  ["notify_freedom", "Выходные: поздравлять и звать в зал"],
  ["notify_checkin", "Просить отметиться на смене"],
  ["beer_enabled", "Опрос «по пиву»"],
  ["show_weather", "Погода в сообщениях"],
];
const CHOICES = [
  { field: "notify_soon_h", title: "Перед сменой", num: true,
    opts: [[0, "выкл"], [1, "за 1 ч"], [2, "за 2 ч"], [3, "за 3 ч"]] },
  { field: "notify_home_min", title: "«Скоро домой»", num: true,
    opts: [[0, "выкл"], [30, "30 мин"], [60, "60 мин"], [80, "80 мин"], [120, "120 мин"]] },
  { field: "notify_bus_min", title: "Напоминать о развозке", num: true,
    opts: [[0, "выкл"], [15, "15 мин"], [30, "30 мин"], [45, "45 мин"], [60, "60 мин"]] },
  { field: "clean_after_min", title: "Автоочистка чата", num: true,
    opts: [[0, "выкл"], [60, "1 ч"], [180, "3 ч"], [360, "6 ч"], [720, "12 ч"]] },
  { field: "sarcasm", title: "Сила сарказма", num: true,
    opts: [[1, "тихий"], [2, "ехидный"], [3, "ядовитый"]] },
];
const API_ERR = {
  bad_range: "Даты не читаются или период длиннее 92 дней",
  bad_date: "Дата не читается",
  future: "Дата устройства не может быть в будущем",
  not_registered: "Сначала настрой график в боте: /start",
};

/* Иконки в одном стиле: тонкая обводка, скругления */
const PATHS = {
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  cal: '<rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  bus: '<rect x="5" y="3.5" width="14" height="14" rx="3"/><path d="M5 11h14M8.5 20.5v-3M15.5 20.5v-3"/><path d="M9 14.5h.01M15 14.5h.01"/>',
  beer: '<path d="M5 8.5h10.5v8.5a3.5 3.5 0 0 1-3.5 3.5H8.5A3.5 3.5 0 0 1 5 17z"/><path d="M15.5 10.5h2a2.5 2.5 0 0 1 0 5h-2"/><path d="M7.5 5.5c.8-1 1.7-1 2.5 0s1.7 1 2.5 0"/>',
  star: '<path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8L12 16.9l-5.3 2.7 1-5.8-4.2-4.1 5.9-.9z"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  pin: '<path d="M12 21s-6-5.3-6-10a6 6 0 0 1 12 0c0 4.7-6 10-6 10z"/><circle cx="12" cy="11" r="2.2"/>',
  cloud: '<path d="M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.6-1.4A4 4 0 0 1 17 18z"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M19 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4"/>',
  cabinet: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M19 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4"/>',
  users: '<circle cx="9" cy="8.5" r="3.2"/><path d="M3.5 19.5c.6-3 2.8-4.6 5.5-4.6s4.9 1.6 5.5 4.6"/><path d="M15.5 5.6a3 3 0 0 1 0 5.8M17.5 15c1.6.5 2.6 2 3 4.3"/>',
  alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.5h.01"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
  thermo: '<path d="M10 14.5V5.5a2 2 0 0 1 4 0v9a4 4 0 1 1-4 0z"/><path d="M12 9.5v6"/>',
  list: '<path d="M9 6.5h11M9 12h11M9 17.5h11"/><circle cx="4.5" cy="6.5" r=".9"/><circle cx="4.5" cy="12" r=".9"/><circle cx="4.5" cy="17.5" r=".9"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/>',
};
const ico = (k, cls = "") =>
  `<span class="ico ${cls}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[k] || ""}</svg></span>`;

const HOP = `<svg class="hop" viewBox="0 0 22 26" aria-hidden="true"><path d="M11 1v24" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/><circle cx="11" cy="6" r="3.2" fill="rgba(255,255,255,.9)"/><circle cx="7.5" cy="11" r="3.2" fill="rgba(255,255,255,.75)"/><circle cx="14.5" cy="11" r="3.2" fill="rgba(255,255,255,.75)"/><circle cx="11" cy="16" r="3.2" fill="rgba(255,255,255,.6)"/></svg>`;

let S = null, tab = "shift", timer = null, selDate = null, schedView = "grid";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hm = (iso) => (iso ? iso.slice(11, 16) : "—");
const ms = (iso) => (iso ? Date.parse(iso) - Date.now() : null);

function buzz(kind = "light") { try { tg && tg.HapticFeedback && tg.HapticFeedback.impactOccurred(kind); } catch (_) {} }
function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), 1900);
}
function fmtDelta(v) {
  if (v == null || v < 0) return "00:00:00";
  const s = Math.floor(v / 1000);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const p = (n) => String(n).padStart(2, "0");
  return d ? `${d}д ${p(h)}:${p(m)}:${p(sec)}` : `${p(h)}:${p(m)}:${p(sec)}`;
}
function openLk() {
  buzz("medium");
  try {
    if (tg && tg.openLink) { tg.openLink(LK_URL); return; }
  } catch (_) {}
  window.open(LK_URL, "_blank", "noopener");
}
function badge(kind, extra = "") {
  const k = KIND[kind] || { cls: "off", label: "—" };
  return `<span class="sbadge ${k.cls} ${extra}">${k.label}</span>`;
}
const kindCls = (k) => (k === "Д" ? "day" : k === "Н" ? "night" : "off");
const hoursOf = (d) => (d.start && d.end ? (Date.parse(d.end) - Date.parse(d.start)) / 3600000 : 0);

/* ---------- загрузка ---------- */

async function load() {
  try {
    await ready;
    S = await api("/api/state");
    $("who").textContent = S.name || "";
    renderAll();
  } catch (e) {
    const msg = {
      auth: "Открой приложение из Telegram: без подписи данные не отдаём.",
      not_registered: "Сначала настрой график в боте: /start",
    }[e.message] || "Не удалось загрузить данные. Потяни вниз или открой позже.";
    document.querySelectorAll(".view").forEach((v) => {
      v.innerHTML = `<div class="card err" data-r><b>Нет доступа</b>${esc(msg)}</div>`;
    });
    fx.reveal($("v-" + tab));
  } finally {
    fx.hideLoader($("loader"));
  }
}

function renderAll() {
  renderShift();
  renderSchedule();
  renderShuttle();
  renderStats();
  renderMore();
  startTimer();
  const sel = tab === "schedule" ? "[data-r], .gcell, .drow" : "[data-r]";
  fx.reveal($("v-" + tab), sel, 0.03);
  fx.revealOnScroll($("v-" + tab));
}

/* ---------- Смена ---------- */

function heroTheme(st) {
  if (st.working) return st.shift_kind === "Н" ? "night" : "day";
  return st.in_weekend ? "off" : "rest";
}

function renderShift() {
  const st = S.status;
  const target = st.working ? st.shift_end : st.next_start;
  const head = st.working
    ? `${badge(st.shift_kind)} <span class="muted">до конца ${hm(st.shift_end)}</span>`
    : (st.in_weekend ? `${badge("В")} <span class="muted">выходные</span>`
                     : `${badge(st.next_kind)} <span class="muted">следующая в ${hm(st.next_start)}</span>`);

  let progress = 0;
  if (st.working && st.shift_start && st.shift_end) {
    const a = Date.parse(st.shift_start), b = Date.parse(st.shift_end);
    progress = Math.min(100, Math.max(0, ((Date.now() - a) / (b - a)) * 100));
  }

  let html = `
    <section class="hero tilt theme-${heroTheme(st)}" data-r>
      <div class="tilt-in">
        <div class="bubbles" id="bubs"></div>
        <div class="hero-top">
          <div class="hero-text">
            <div class="eyebrow">${HOP}<span>${st.working ? "Смена идёт" : "Пока без смены"}</span></div>
            <div class="head">${head}</div>
            <div class="countdown num" id="cd">${fmtDelta(ms(target))}</div>
            <div class="muted">${st.working ? "до конца смены" : "до начала смены"}</div>
          </div>
          <div class="hero-mug">${mugSvg(st.working ? progress / 100 : 0)}</div>
        </div>
        ${st.working
          ? `<div class="bar"><i id="pb"></i></div><div class="hero-foot"><span>${Math.round(progress)}% смены позади</span></div>`
          : `<div class="hero-foot"><span>Отдыхай, пиво подождёт</span></div>`}
      </div>
    </section>`;

  if (S.weather) {
    html += `
      <section class="card" data-r>
        <div class="row">${ico("cloud", "c-sky")}<div style="min-width:0;flex:1"><div class="muted">Погода на заводе</div><div class="strong">${esc(S.weather.line)}</div></div></div>
        <div class="muted" style="margin-top:8px">${esc(S.weather.advice)}</div>
      </section>`;
  }

  let beerHtml = "";
  if (S.beer) {
    const b = S.beer;
    beerHtml = `
      <section class="card quiet" data-r>
        <div class="row">${ico("beer", "amber")}<div style="min-width:0;flex:1"><div class="strong">После смены</div><div class="muted">${esc(b.place)}</div></div>${ico("users", "c-violet")}</div>
        <div class="muted" style="margin-top:10px">${b.yes_count ? esc(b.yes_names.join(", ")) : "Пока никто не ответил"}</div>
        <div class="btns">
          <button class="btn press ${b.my_vote === true ? "on" : "ghost"}" data-vote="1">Я за</button>
          <button class="btn press ${b.my_vote === false ? "on" : "ghost"}" data-vote="0">Не в этот раз</button>
        </div>
      </section>`;
  }

  if (S.wellness) {
    html += `
      <section class="card" data-r>
        <div class="row">${ico("check", "c-green")}<div class="strong" style="flex:1">Зал · Бассейн · Сауна</div></div>
        <div style="margin-top:12px">${wellnessHtml(S.wellness.state, S.wellness.gender)}</div>
      </section>`;
  }

  if (S.shuttle && S.shuttle.mine) {
    const m = S.shuttle.mine;
    const list = st.working ? m.next_from_work : m.next_to_work;
    html += `
      <section class="card" data-r>
        <div class="row">${ico("bus", "c-teal")}<div style="min-width:0;flex:1"><div class="muted">${st.working ? "С завода" : "На смену"}</div><div class="strong">${esc(m.station)}</div></div></div>
        <div class="bus" style="margin-top:12px">
          ${list.length ? list.map((t, i) => `<span class="chip ${i === 0 ? "next" : ""}">${hm(t)}</span>`).join("") : `<span class="muted">Рейсов на ближайшее время нет</span>`}
        </div>
      </section>`;
  }

  html += `
    <section class="btns single" data-r>
      <button class="btn press accept" id="markBtn">${svgIco("check")}<span>Отметиться</span></button>
    </section>
    <button class="lkbtn press" id="lkBtn" data-r>
      <span class="lk-l">${ico("cabinet", "c-pink")}<span class="lk-t"><b>Личный кабинет Балтики</b><small>Документы и кадровые сведения</small></span></span>
      <span class="arr" aria-hidden="true">↗</span>
    </button>`;

  html += beerHtml;
  $("v-shift").innerHTML = html;
  $("title").textContent = TITLES[tab];
  fx.bubbles($("bubs"), 11);
  fx.fillBar($("pb"), progress);
  fx.fillMugs($("v-shift"));
}

/* ---------- График ---------- */

function groupMonths(cal) {
  const out = [];
  cal.forEach((d) => {
    const key = d.date.slice(0, 7);
    let g = out.find((x) => x.key === key);
    if (!g) {
      const [y, m] = key.split("-").map(Number);
      g = { key, y, m: m - 1, days: [] };
      out.push(g);
    }
    g.days.push(d);
  });
  return out;
}

function scheduleSummary(cal) {
  const work = cal.filter((d) => d.kind !== "В");
  return {
    work: work.length,
    day: cal.filter((d) => d.kind === "Д").length,
    night: cal.filter((d) => d.kind === "Н").length,
    off: cal.filter((d) => d.kind === "В").length,
    hours: Math.round(work.reduce((a, d) => a + hoursOf(d), 0)),
  };
}

/* месячная сетка: понедельник первым, пустые клетки до первого дня */
function monthGrid(days, today) {
  const first = new Date(days[0].date + "T12:00:00");
  const lead = (first.getDay() + 6) % 7;
  const cells = [];
  for (let i = 0; i < lead; i++) cells.push(`<i class="gcell empty" aria-hidden="true"></i>`);
  days.forEach((d) => {
    const n = new Date(d.date + "T12:00:00").getDate();
    const cls = [kindCls(d.kind), d.date === today ? "today" : "", d.date === selDate ? "sel" : ""].join(" ");
    cells.push(`<button class="gcell press ${cls}" data-date="${d.date}" aria-label="${n}"><span>${n}</span><i class="gdot"></i></button>`);
  });
  return `<div class="wkhead">${WEEK_MON.map((w) => `<span>${w}</span>`).join("")}</div><div class="grid">${cells.join("")}</div>`;
}

function rowHtml(d, today) {
  const dt = new Date(d.date + "T12:00:00");
  let tm, sub;
  if (d.start && d.end) {
    const hours = Math.round(hoursOf(d));
    const nextDay = d.end.slice(0, 10) !== d.date ? " · до утра следующего дня" : "";
    tm = `${hm(d.start)} — ${hm(d.end)}`;
    sub = `${d.kind === "Д" ? "Дневная" : "Ночная"} смена, ${hours} ч${nextDay}`;
  } else {
    tm = "Выходной";
    sub = d.weekend ? "Выходные" : "Отдых";
  }
  return `
    <div class="drow press ${d.kind === "В" ? "wk" : ""} ${d.date === today ? "today" : ""} ${d.date === selDate ? "sel" : ""}" data-date="${d.date}">
      <div class="dt"><span>${WD[dt.getDay()]}</span><b>${dt.getDate()}</b><span>${MONTHS[dt.getMonth()]}</span></div>
      <div class="tm">${tm}<small>${sub}</small></div>
      ${badge(d.kind, d.kind === "В" ? "" : "glow")}
    </div>`;
}

function dayDetail(d) {
  if (!d) return "";
  const dt = new Date(d.date + "T12:00:00");
  const isWork = d.kind !== "В";
  const hours = isWork ? Math.round(hoursOf(d)) : 0;
  const cross = isWork && d.end && d.end.slice(0, 10) !== d.date;
  const until = isWork && d.start ? ms(d.start) : null;
  return `
    <div class="dd-head">
      <div class="dd-date"><b>${dt.getDate()}</b><span>${MONTHS_GEN[dt.getMonth()]}, ${WD_FULL[dt.getDay()]}</span></div>
      ${badge(d.kind, isWork ? "glow" : "")}
    </div>
    <div class="dd-time num">${isWork ? `${hm(d.start)} — ${hm(d.end)}` : "Выходной"}</div>
    <div class="dd-meta">
      ${isWork ? `<span class="pill">${hours} ч${cross ? " · до утра" : ""}</span>` : `<span class="pill">${d.weekend ? "выходные" : "отдых"}</span>`}
      ${until != null && until > 0 ? `<span class="pill soft">через ${fmtDelta(until)}</span>` : ""}
    </div>
    ${d.wellness ? `<div style="margin-top:14px">${wellnessHtml(d.wellness, d.gender)}</div>` : ""}`;
}

function renderSchedule() {
  const cal = S.calendar || [];
  const today = S.today || (cal[0] && cal[0].date) || "";
  if (!selDate || !cal.some((d) => d.date === selDate)) selDate = today;

  const sum = scheduleSummary(cal);
  const sel = cal.find((d) => d.date === selDate);
  $("v-schedule").innerHTML = `
    <section class="card sumcard" data-r>
      <div class="sum-head">
        <div class="eyebrow dark">Ближайшие ${cal.length} дней</div>
        <div class="sum-title strong">${sum.work} смен · ${sum.hours} ч</div>
      </div>
      <div class="sum-grid">
        <div class="sum-i c-blue"><b>${sum.day}</b><span>дневных</span></div>
        <div class="sum-i c-violet"><b>${sum.night}</b><span>ночных</span></div>
        <div class="sum-i c-green"><b>${sum.off}</b><span>выходных</span></div>
        <div class="sum-i c-amber"><b>${sum.hours}</b><span>часов</span></div>
      </div>
      <div class="seg" id="seg">
        <span class="seg-ind" id="segInd"></span>
        <button type="button" class="${schedView === "grid" ? "on" : ""}" data-sview="grid">Сетка</button>
        <button type="button" class="${schedView === "list" ? "on" : ""}" data-sview="list">Список</button>
      </div>
    </section>
    <section class="detail card" id="detail" data-r>${dayDetail(sel)}</section>
    <div class="legend" data-r>
      <span><i class="dot day"></i>день</span><span><i class="dot night"></i>ночь</span><span><i class="dot off"></i>выходной</span>
    </div>
    <div id="schedBody"></div>`;
  fx.placeSeg($("segInd"), schedView === "list" ? 1 : 0);
  renderSchedBody();
}

function renderSchedBody() {
  const cal = S.calendar || [];
  const today = S.today || (cal[0] && cal[0].date) || "";
  const body = groupMonths(cal).map((g) => {
    const title = `<div class="mon" data-iv>${MONTHS_FULL[g.m]} ${g.y}</div>`;
    return schedView === "grid"
      ? `${title}<div class="cal card" data-iv>${monthGrid(g.days, today)}</div>`
      : `${title}<div class="group" data-iv>${g.days.map((d) => rowHtml(d, today)).join("")}</div>`;
  }).join("");
  $("schedBody").innerHTML = body;
}

function selectDay(date) {
  if (date === selDate) return;
  selDate = date;
  buzz();
  const view = $("v-schedule");
  view.querySelectorAll("[data-date]").forEach((el) => el.classList.toggle("sel", el.dataset.date === date));
  const cal = S.calendar || [];
  const detail = $("detail");
  if (detail) {
    detail.innerHTML = dayDetail(cal.find((d) => d.date === date));
    fx.pop(detail);
  }
}

/* ---------- Развозка ---------- */

function routeHtml(r) {
  const chips = (arr) => (arr.length ? arr.map((t) => `<span class="chip">${t}</span>`).join("") : `<span class="muted">Рейсов нет</span>`);
  return `
    <section class="card tap route press ${r.is_mine ? "mine" : ""}" data-iv>
      ${r.is_mine ? `<span class="tag">моя</span>` : ""}
      <div class="row">${ico("bus", r.is_mine ? "c-teal" : "soft")}<div class="title">${esc(r.title)}</div></div>
      <div class="lbl">Со станции на завод</div>
      <div class="bus">${chips(r.to_work_today)}</div>
      <div class="lbl">С завода на станцию</div>
      <div class="bus">${chips(r.from_work_today)}</div>
    </section>`;
}

function renderShuttle() {
  const sh = S.shuttle;
  if (!sh || !sh.routes || !sh.routes.length) {
    $("v-shuttle").innerHTML = `<div class="card err" data-r><b>Развозка не настроена</b>Проверь расписание на сервере</div>`;
    return;
  }
  const wk = sh.routes[0].is_weekend ? "выходные" : "будни";
  let html = `<div class="muted sub" data-r>Расписание на ${wk} · все станции</div>`;
  if (sh.mine) {
    const m = sh.mine;
    const list = S.status.working ? m.next_from_work : m.next_to_work;
    html += `
      <section class="card glass" data-r>
        <div class="row">${ico("pin", "c-coral")}<div style="min-width:0;flex:1"><div class="muted">Твоя станция</div><div class="strong">${esc(m.station)}</div></div></div>
        <div class="lbl">${S.status.working ? "Ближайшие с завода" : "Ближайшие на смену"}</div>
        <div class="bus">${list.length ? list.map((t, i) => `<span class="chip ${i === 0 ? "next" : ""}">${hm(t)}</span>`).join("") : `<span class="muted">Рейсов на ближайшее время нет</span>`}</div>
      </section>`;
  } else {
    html += `<div class="card muted" data-r>Станция не выбрана. Выбери её в боте: /nastroiki</div>`;
  }
  html += sh.routes.map(routeHtml).join("");
  $("v-shuttle").innerHTML = html;
}

/* ---------- Стаж ---------- */

function renderStats() {
  const s = S.stats;
  if (!s) {
    $("v-stats").innerHTML = `<div class="card err" data-r><b>Стаж не посчитан</b>Укажи дату устройства во вкладке «Ещё», в профиле.</div>`;
    return;
  }
  const rate = s.planned_shifts ? Math.round(s.rate * 100) : 0;
  const worked = s.planned_shifts ? Math.round((s.worked_shifts / s.planned_shifts) * 100) : 0;
  const hired = s.hired.split("-").reverse().join(".");
  $("v-stats").innerHTML = `
    <section class="hero tilt theme-stazh" data-r>
      <div class="tilt-in">
        <div class="bubbles" id="bubs2"></div>
        <div class="hero-top">
          <div class="hero-text">
            <div class="eyebrow">${HOP}<span>Стаж на заводе</span></div>
            <div class="big num">
              <span><b data-count="${s.years}">0</b><small>г</small></span>
              <span><b data-count="${s.months}">0</b><small>м</small></span>
              <span><b data-count="${s.days}">0</b><small>д</small></span>
            </div>
            <div class="muted">с ${hired} · всего ${s.total_days} дн.</div>
          </div>
          <div class="hero-mug">${mugSvg(rate / 100)}</div>
        </div>
        <div class="rate-row"><span>Посещаемость смен</span><b><span data-count="${rate}">0</span>%</b></div>
        <div class="bar"><i data-meter="${rate}"></i></div>
      </div>
    </section>
    <div class="metrics">
      <div class="metric c1" data-r>
        ${ico("check", "c-blue")}
        <b data-count="${s.worked_shifts}">0</b><span>отработано смен</span>
        <div class="meter"><i data-meter="${worked}"></i></div>
      </div>
      <div class="metric c2" data-r>
        ${ico("clock", "c-violet")}
        <b data-count="${Math.round(s.worked_hours)}">0</b><span>часов на заводе</span>
        <div class="meter"><i data-meter="${Math.min(100, rate)}"></i></div>
      </div>
      <div class="metric c3" data-r>
        ${ico("alert", "c-coral")}
        <b data-count="${s.missed_shifts ?? 0}">0</b><span>пропусков</span>
        <div class="meter"><i data-meter="${Math.min(100, (s.missed_shifts ?? 0) * 5)}"></i></div>
      </div>
      <div class="metric c4" data-r>
        ${ico("star", "amber")}
        <b><span data-count="${rate}">0</span>%</b><span>посещаемость</span>
        <div class="meter"><i data-meter="${rate}"></i></div>
      </div>
    </div>
    ${s.unconfirmed ? `<section class="card glass" data-r style="margin-top:12px"><div class="row">${ico("alert", "amber")}<div style="flex:1"><div class="strong">Не отмечено</div><div class="muted">${s.unconfirmed} смен без отметки</div></div></div></section>` : ""}`;

  fx.bubbles($("bubs2"), 9);
  fx.fillMugs($("v-stats"));
  fx.fillMeter($("v-stats"));
  $("v-stats").querySelectorAll("[data-count]").forEach((el) => fx.countUp(el, el.dataset.count));
}

/* ---------- Ещё: настройки и кабинет ---------- */

function renderMore() {
  const cfg = S.settings || {};
  const routes = (S.shuttle && S.shuttle.routes) || [];
  const routeChoice = {
    field: "shuttle_route", title: "Станция развозки", num: false,
    opts: [...routes.map((r) => [r.key, r.station]), ["none", "не пользуюсь"]],
  };
  const sw = SWITCHES.map(([k, label]) => `
    <div class="set-row">
      <span>${esc(label)}</span>
      <label class="sw"><input type="checkbox" data-set="${k}" ${cfg[k] ? "checked" : ""}><i></i></label>
    </div>`).join("");
  const group = (list) => `<div class="group" data-iv>${list.map((c) => choiceHtml(c, cfg)).join("")}</div>`;
  $("v-more").innerHTML = `
    ${profileCard()}
    <section class="hero tilt theme-lk" data-r>
      <div class="tilt-in">
        <div class="bubbles" id="bubs3"></div>
        <div class="hero-top">
          <div class="hero-text">
            <div class="eyebrow">${HOP}<span>Личный кабинет</span></div>
            <div class="head strong-h">Балтика</div>
            <div class="muted">Документы и кадровые сведения на сайте компании</div>
          </div>
          <div class="hero-mug">${mugSvg(0.82)}</div>
        </div>
        <button class="btn press light" id="lkBtn2">${ico("ext")}<span>Личный кабинет Балтики</span></button>
      </div>
    </section>
    <div class="mon" data-r>Уведомления</div>
    <div class="group" data-iv>${sw}</div>
    <div class="mon" data-r>Когда напоминать</div>
    ${group(CHOICES.slice(0, 3))}
    <div class="mon" data-r>Развозка и чат</div>
    ${group([routeChoice, ...CHOICES.slice(3)])}
    <div class="muted foot" data-r>Всё, что меняешь здесь, сразу уходит в бота.</div>`;

  fx.bubbles($("bubs3"), 8);
  fx.fillMugs($("v-more"));
}

/* ---------- звания, профиль, отпуск и больничный ---------- */

const GEN_LABEL = { m: "мужской", w: "женский" };
const ZONES_UI = [["🏋️", "Зал"], ["🏊", "Бассейн"], ["🧖", "Сауна"]];
const svgIco = (k) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[k] || ""}</svg>`;
const fmtDay = (iso) => (iso ? iso.split("-").reverse().join(".") : "—");
const daysBetween = (a, b) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000) + 1;
const tenureText = (s) =>
  [s.years && `${s.years} г`, s.months && `${s.months} мес`, s.days && `${s.days} дн`].filter(Boolean).join(" ") || "меньше дня";

/* Профиль: имя, стаж, отпуск, больничный, дата устройства */
function profileCard() {
  const s = S.stats;
  const sub = s ? `В строю с ${fmtDay(s.hired)} · ${tenureText(s)}` : "Дата устройства не указана";
  const today = S.today || "";
  const vac = S.vacations || [];
  const rows = vac.map((v) => {
    const st = v.finish < today ? "прошёл" : v.start <= today ? "идёт сейчас" : "впереди";
    return `
      <div class="vac-row">
        ${ico("sun", "c-amber")}
        <div class="vac-t"><b>${fmtDay(v.start)} — ${fmtDay(v.finish)}</b><small>${daysBetween(v.start, v.finish)} дн. · ${st}</small></div>
        <button class="ib" data-vdel="${v.id}" aria-label="Удалить отпуск">×</button>
      </div>`;
  }).join("");
  return `
    <section class="card profile" data-r>
      <div class="prof-name">${esc(S.name || "Без имени")}</div>
      <div class="muted">${esc(sub)}</div>
      <div class="btns">
        <button class="btn ghost press" id="vacBtn">${svgIco("sun")}<span>Отпуск</span></button>
        <button class="btn ghost press" id="sickBtn">${svgIco("thermo")}<span>Больничный</span></button>
      </div>
      <button class="linkbtn" id="hiredBtn">${s ? "Изменить дату устройства" : "Указать дату устройства"}</button>
      ${rows ? `<div class="lbl">Отпуска</div><div class="vac-list">${rows}</div><button class="linkbtn danger" id="vacClear">Удалить все отпуска</button>` : ""}
    </section>`;
}

/* Зал · Бассейн · Сауна: состояние дня для посетителя */
function wellnessHtml(state, gender) {
  const open = state === "open";
  const head = open
    ? "Можно сходить"
    : state === "other"
      ? `${GEN_LABEL[gender]} день, сюда не пускают`
      : "Смена, не до спорта";
  return `
    <div class="wl ${open ? "open" : "closed"}">
      <div class="wl-head"><b>${head}</b><span class="pill ${open ? "" : "soft"}">${GEN_LABEL[gender] || ""} день</span></div>
      <div class="zones">${ZONES_UI.map(([e, t]) => `<span class="zone"><i>${e}</i>${t}</span>`).join("")}</div>
    </div>`;
}

/* Строка выбора для настроек: кнопки-капсулы, одна выбрана */
function choiceHtml(c, cfg) {
  const cur = cfg[c.field];
  return `
    <div class="set-col">
      <div class="set-lbl">${esc(c.title)}</div>
      <div class="opts" data-field="${c.field}" data-num="${c.num ? 1 : 0}">
        ${c.opts.map(([v, l]) => `<button class="opt press ${String(v) === String(cur) ? "on" : ""}" data-val="${esc(v)}">${esc(l)}</button>`).join("")}
      </div>
    </div>`;
}

async function saveChoice(btn) {
  const wrap = btn.closest(".opts");
  const field = wrap.dataset.field;
  const val = wrap.dataset.num === "1" ? Number(btn.dataset.val) : btn.dataset.val;
  const prev = S.settings[field];
  if (String(prev) === String(val)) return;
  buzz();
  const mark = (cur) => wrap.querySelectorAll(".opt").forEach((b) => b.classList.toggle("on", String(b.dataset.val) === String(cur)));
  mark(val);
  S.settings[field] = val;
  if (field === "clean_after_min") S.settings.autoclean = val > 0;
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify({ [field]: val }) });
    toast("Сохранил");
  } catch (e) {
    S.settings[field] = prev;
    mark(prev);
    toast("Не сохранилось, попробуй ещё");
  }
}

/* Нижняя шторка с полями: открывается пружиной, закрывается плавно */
function openSheet({ title, body, okText, onOk }) {
  buzz("light");
  const wrap = document.createElement("div");
  wrap.className = "sheet-wrap";
  wrap.innerHTML = `
    <div class="sheet-bg" data-x></div>
    <div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <div class="grab"></div>
      <h3 class="sheet-t">${esc(title)}</h3>
      ${body}
      <div class="btns sheet-btns">
        <button class="btn ghost press" data-x>Отмена</button>
        <button class="btn press" data-ok>${esc(okText)}</button>
      </div>
    </div>`;
  document.body.appendChild(wrap);
  const sheet = wrap.querySelector(".sheet");
  fx.reveal(sheet, ".sheet-t, .sheet-hint, .fld, .opts, .period, .sheet-btns", 0.06);
  const bg = wrap.querySelector(".sheet-bg");
  let closing = false;
  const close = () => {
    if (closing) return;
    closing = true;
    if (fx.reduce) { wrap.remove(); return; }
    animate(sheet, { transform: ["translateY(0%)", "translateY(110%)"] }, { duration: 0.28, ease: [0.4, 0, 1, 1] });
    animate(bg, { opacity: [1, 0] }, { duration: 0.28 });
    setTimeout(() => wrap.remove(), 300);
  };
  wrap.addEventListener("click", (e) => {
    if (e.target.closest("[data-x]")) return close();
    if (e.target.closest("[data-ok]")) return onOk(wrap, close);
  });
  if (!fx.reduce) {
    animate(bg, { opacity: [0, 1] }, { duration: 0.3 });
    animate(sheet, { transform: ["translateY(110%)", "translateY(0%)"] }, { type: "spring", stiffness: 320, damping: 34 });
  }
  return wrap;
}

/* Защита от двойного нажатия «Записать» */
const once = (run) => {
  let busy = false;
  return async (wrap, close) => {
    if (busy) return;
    busy = true;
    try { await run(wrap, close); } finally { busy = false; }
  };
};
const todayIso = () => S.today || new Date().toISOString().slice(0, 10);
const addDays = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
const apiErr = (e) => API_ERR[e.message] || "Не получилось, попробуй ещё";
const dateField = (id, label, value) =>
  `<label class="fld"><span>${esc(label)}</span><input type="date" id="${id}" value="${esc(value)}"></label>`;

/* Выбор периода: быстрые пресеты, живая сводка и проверка пересечений */
function periodHtml(first) {
  const presets = [["Сегодня", 0], ["Неделя", 6], ["2 недели", 13], ["Месяц", 29]];
  return `
    <div class="opts presets">${presets.map(([l, n]) => `<button class="opt press" data-preset="${n}">${l}</button>`).join("")}</div>
    ${dateField("fStart", "С", first)}${dateField("fFinish", "По", first)}
    <div class="period" id="pSum"></div>
    <div class="period warn" id="pWarn" hidden></div>`;
}

function updatePeriod(wrap, kind) {
  const a = wrap.querySelector("#fStart").value, b = wrap.querySelector("#fFinish").value;
  const sum = wrap.querySelector("#pSum"), warn = wrap.querySelector("#pWarn");
  warn.hidden = true;
  if (!a || !b) { sum.textContent = ""; return; }
  if (b < a) { sum.innerHTML = `<span class="bad">«По» раньше «с»</span>`; return; }
  const days = daysBetween(a, b);
  const cal = S.calendar || [];
  const lastShown = cal.length ? cal[cal.length - 1].date : a;
  const inCal = cal.filter((d) => d.date >= a && d.date <= b);
  const shifts = inCal.filter((d) => d.kind !== "В").length;
  const beyond = b > lastShown;
  const shiftWord = kind === "vac" ? "попадает смен" : "отметим смен";
  const shiftTxt = inCal.length
    ? `${shiftWord}: <b>${shifts}</b>${beyond ? " (дальше графика видно не всё)" : ""}`
    : "смены дальше графика, посчитаем на сервере";
  sum.innerHTML = `<b>${days} дн.</b> · ${shiftTxt}`;
  const overlap = (S.vacations || []).find((v) => v.start <= b && v.finish >= a);
  if (overlap) {
    warn.hidden = false;
    warn.textContent = `Пересекается с отпуском ${fmtDay(overlap.start)} — ${fmtDay(overlap.finish)}`;
  }
}

function bindPeriod(wrap, kind) {
  wrap.addEventListener("click", (e) => {
    const p = e.target.closest("[data-preset]");
    if (!p) return;
    const start = wrap.querySelector("#fStart").value || todayIso();
    wrap.querySelector("#fStart").value = start;
    wrap.querySelector("#fFinish").value = addDays(start, Number(p.dataset.preset));
    wrap.querySelectorAll("[data-preset]").forEach((b) => b.classList.toggle("on", b === p));
    buzz();
    updatePeriod(wrap, kind);
  });
  wrap.addEventListener("input", () => updatePeriod(wrap, kind));
  updatePeriod(wrap, kind);
}

function readRange(wrap) {
  const a = wrap.querySelector("#fStart").value, b = wrap.querySelector("#fFinish").value;
  if (!a || !b) { toast("Выбери обе даты"); return null; }
  if (b < a) { toast("Дата «по» раньше даты «с»"); return null; }
  if (daysBetween(a, b) > 92) { toast("Период длиннее 92 дней, проверь даты"); return null; }
  return { start: a, finish: b };
}

function openVacation() {
  const wrap = openSheet({
    title: "Отпуск",
    body: `<div class="sheet-hint">Бот не трогает смены в эти дни.</div>${periodHtml(todayIso())}`,
    okText: "Записать",
    onOk: once(async (w, close) => {
      const rng = readRange(w);
      if (!rng) return;
      try {
        await api("/api/vacation", { method: "POST", body: JSON.stringify(rng) });
        buzz("medium");
        toast("Отпуск записан");
        close();
        await load();
      } catch (e) { toast(apiErr(e)); }
    }),
  });
  bindPeriod(wrap, "vac");
}

function openSick() {
  const wrap = openSheet({
    title: "Больничный",
    body: `<div class="sheet-hint">Рабочие смены в периоде уйдут в стаж как больничные. Можно задним числом.</div>${periodHtml(todayIso())}`,
    okText: "Отметить",
    onOk: once(async (w, close) => {
      const rng = readRange(w);
      if (!rng) return;
      try {
        const r = await api("/api/sick", { method: "POST", body: JSON.stringify(rng) });
        buzz("medium");
        toast(`Отмечено смен: ${r.count ?? 0}`);
        close();
        await load();
      } catch (e) { toast(apiErr(e)); }
    }),
  });
  bindPeriod(wrap, "sick");
}

function openHired() {
  openSheet({
    title: "Дата устройства",
    body: `<div class="sheet-hint">От неё считаются стаж и звание. В будущем дата быть не может.</div>${dateField("fStart", "Вышел на завод", (S.stats && S.stats.hired) || todayIso())}`,
    okText: "Сохранить",
    onOk: once(async (wrap, close) => {
      const date = wrap.querySelector("#fStart").value;
      if (!date) return toast("Выбери дату");
      try {
        await api("/api/hired", { method: "POST", body: JSON.stringify({ date }) });
        buzz("medium");
        toast("Дата сохранена");
        close();
        await load();
      } catch (e) { toast(apiErr(e)); }
    }),
  });
}

async function deleteVacation(id) {
  buzz();
  try {
    await api("/api/vacation/delete", { method: "POST", body: JSON.stringify({ id: Number(id) }) });
    toast("Удалил");
    await load();
  } catch (e) { toast("Не получилось, попробуй ещё"); }
}

async function clearVacations() {
  const go = async () => {
    try {
      await api("/api/vacation/delete", { method: "POST", body: JSON.stringify({ clear: true }) });
      toast("Отпуска удалены");
      await load();
    } catch (e) { toast("Не получилось, попробуй ещё"); }
  };
  if (tg && typeof tg.showConfirm === "function") tg.showConfirm("Удалить все отпуска?", (ok) => ok && go());
  else go();
}

/* ---------- таймер, действия и навигация ---------- */

function startTimer() {
  clearInterval(timer);
  timer = setInterval(() => {
    if (!S) return;
    const st = S.status;
    const target = st.working ? st.shift_end : st.next_start;
    const el = $("cd");
    if (el && tab === "shift") el.textContent = fmtDelta(ms(target));
  }, 1000);
}

async function saveSetting(input) {
  const key = input.dataset.set, val = input.checked;
  buzz();
  S.settings = S.settings || {};
  S.settings[key] = val;
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify({ [key]: val }) });
    toast("Сохранил");
  } catch (e) {
    input.checked = !val;
    S.settings[key] = !val;
    toast("Не сохранилось, попробуй ещё");
  }
}

async function vote(yes, x, y) {
  if (!S || !S.beer) return;
  buzz("medium");
  try {
    await api("/api/beer/vote", { method: "POST", body: JSON.stringify({ event_id: S.beer.event_id, yes }) });
    toast(yes ? "Записал: ты за" : "Записал: в этот раз мимо");
    if (yes) fx.burst(x, y);
    await load();
  } catch (e) { toast("Не получилось, попробуй ещё"); }
}

function markToday() {
  buzz();
  const labels = { worked: "Отработал", sick: "Больничный", absent: "Прогул", dayoff: "Выходной", vacation: "Отпуск" };
  const send = async (status) => {
    try {
      await api("/api/mark", { method: "POST", body: JSON.stringify({ status }) });
      toast(labels[status] + " — записал");
      await load();
    } catch (e) { toast(e.message === "no_shift" ? "Смены не нашёл" : "Не получилось"); }
  };
  if (tg && tg.showPopup) {
    tg.showPopup({
      title: "Отметка по смене",
      message: "Что отмечаем?",
      buttons: [
        { id: "worked", type: "default", text: "Отработал" },
        { id: "sick", type: "default", text: "Больничный" },
        { id: "absent", type: "destructive", text: "Прогул" },
        { type: "cancel" },
      ],
    }, (id) => { if (id) send(id); });
  } else {
    send("worked");
  }
}

function switchTab(name) {
  if (name === tab) { window.scrollTo({ top: 0, behavior: "smooth" }); return; }
  const prev = tab;
  tab = name;
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("on"));
  const view = $("v-" + name);
  view.classList.add("on");
  if (!fx.reduce) {
    const dir = ORDER.indexOf(name) > ORDER.indexOf(prev) ? 1 : -1;
    animate(view, { opacity: [0, 1], transform: [`translateX(${28 * dir}px) scale(0.985)`, "translateX(0px) scale(1)"] },
      { type: "spring", stiffness: 300, damping: 32 });
  }
  document.querySelectorAll(".nav button").forEach((b) => {
    const on = b.dataset.tab === name;
    b.classList.toggle("on", on);
    if (on) {
      const svg = b.querySelector("svg");
      if (!fx.reduce && svg) animate(svg, { transform: ["scale(0.7)", "scale(1.12)", "scale(1)"] }, { duration: 0.5, ease: [0.3, 1.4, 0.4, 1] });
    }
  });
  $("nav").style.setProperty("--tab", TAB_COLOR[name]);
  fx.moveNavIndicator($("ind"), ORDER.indexOf(name));
  $("title").textContent = TITLES[name];
  buzz("light");
  window.scrollTo({ top: 0, behavior: "smooth" });
  fx.reveal(view, tab === "schedule" ? "[data-r], .gcell, .drow" : "[data-r]", 0.03);
  fx.revealOnScroll(view);
}

/* события */
$("nav").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-tab]");
  if (b) switchTab(b.dataset.tab);
});
$("menuBtn").addEventListener("click", () => { buzz(); switchTab("more"); });
$("searchBtn").addEventListener("click", () => { buzz(); toast("Поиск пока не подключён"); });
$("v-schedule").addEventListener("click", (e) => {
  const sv = e.target.closest("[data-sview]");
  if (sv) {
    const next = sv.dataset.sview;
    if (next === schedView) return;
    schedView = next;
    buzz();
    document.querySelectorAll("#seg button").forEach((b) => b.classList.toggle("on", b.dataset.sview === next));
    fx.slideSeg($("segInd"), next === "list" ? 1 : 0);
    renderSchedBody();
    fx.reveal($("schedBody"), ".gcell, .drow, .cal, .group, .mon", 0.025);
    return;
  }
  const d = e.target.closest("[data-date]");
  if (d) selectDay(d.dataset.date);
});
$("v-shift").addEventListener("click", (e) => {
  const v = e.target.closest("[data-vote]");
  if (v) {
    const r = v.getBoundingClientRect();
    return vote(v.dataset.vote === "1", r.left + r.width / 2, r.top + r.height / 2);
  }
  if (e.target.closest("#markBtn")) return markToday();
  if (e.target.closest("#lkBtn")) return openLk();
});
$("v-more").addEventListener("change", (e) => {
  const i = e.target.closest("input[data-set]");
  if (i) saveSetting(i);
});
$("v-more").addEventListener("click", (e) => {
  if (e.target.closest("#lkBtn2")) return openLk();
  if (e.target.closest("#vacBtn")) return openVacation();
  if (e.target.closest("#sickBtn")) return openSick();
  if (e.target.closest("#hiredBtn")) return openHired();
  if (e.target.closest("#vacClear")) return clearVacations();
  const del = e.target.closest("[data-vdel]");
  if (del) return deleteVacation(del.dataset.vdel);
  const opt = e.target.closest(".opt");
  if (opt) saveChoice(opt);
});

fx.bindPress(document);
fx.bindLight(document);
fx.bindTilt(document);

/* экран загрузки: кружка наливается, пока тянем данные */
function startLoaderMug() {
  const host = $("loaderMug");
  if (!host) return;
  host.innerHTML = mugSvg(0, { cls: "loader-svg" });
  if (fx.reduce) return;
  const liquid = host.querySelector(".mug-liquid");
  animate(
    liquid,
    { transform: ["translateY(112px)", "translateY(0px)", "translateY(0px)", "translateY(112px)"] },
    { duration: 2.6, times: [0, 0.6, 0.85, 1], repeat: Infinity, ease: "easeInOut" }
  );
}

if (tg) { tg.ready(); tg.expand(); }
$("title").textContent = TITLES[tab];
$("nav").style.setProperty("--tab", TAB_COLOR[tab]);
startLoaderMug();
load();
