/* Настройка графика в приложении: цикл → дата первой смены → проверка календаря → подтверждение.
   Тот же смысл, что у мастера /start в боте, но одним экраном и с живым календарём. */
import { api, tg } from "./api.js";

export const BALTIKA = "ДДВННВВВ";
const WD = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
const KIND_CLS = { "Д": "day", "Н": "night", "В": "off" };
const KIND_WORD = { "Д": "День", "Н": "Ночь", "В": "Выходной" };
const KIND_SHORT = { "Д": "день", "Н": "ночь", "В": "вых" };
const KIND_ADJ = { "Д": "дневная", "Н": "ночная", "В": "выходной" };
const PREVIEW_DAYS = 14;
const ERR = {
  bad_setup: "Проверь цикл и дату и попробуй ещё раз",
  auth: "Открой приложение из Telegram",
};

const p2 = (n) => String(n).padStart(2, "0");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ymd = (d) => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
const todayYmd = () => ymd(new Date());
/* сдвиг даты в днях; 12:00 — чтобы переход на летнее/зимнее время ничего не сдвинул */
const shiftYmd = (base, n) => {
  const d = new Date(base + "T12:00:00");
  d.setDate(d.getDate() + n);
  return ymd(d);
};
/* разница в днях между двумя датами YYYY-MM-DD, считается в UTC, без сюрпризов с часовыми поясами */
const dayDiff = (a, b) => Math.round((Date.parse(b + "T00:00:00Z") - Date.parse(a + "T00:00:00Z")) / 864e5);

/* вид смены в день: тот же расчёт, что ShiftConfig.kind на сервере (без отпусков) */
export function kindOn(pattern, anchor, day) {
  const n = dayDiff(anchor, day);
  return pattern[((n % pattern.length) + pattern.length) % pattern.length];
}

/* «ддвннввв», «DDVNNVVV», «Д Д В Н Н В В В» -> «ДДВННВВВ»; мусор -> null */
export function cleanPattern(raw) {
  const s = String(raw || "")
    .toUpperCase()
    .replace(/[\s,.;\-]/g, "")
    .replace(/D/g, "Д")
    .replace(/N/g, "Н")
    .replace(/[VOB]/g, "В");
  if (!/^[ДНВ]{2,31}$/.test(s) || !/[ДН]/.test(s)) return null;
  return s;
}

/* Монтирует экран в host. onBack есть только при редактировании; onDone — после сохранения. */
export function mountSetup(host, { editing = false, current = null, onBack, onDone }) {
  const cur = current && current.pattern ? current : null;
  const st = {
    mode: cur && cur.pattern !== BALTIKA ? "custom" : "baltika",
    custom: cur && cur.pattern !== BALTIKA ? cur.pattern : "",
    anchor: cur && cur.anchor ? cur.anchor : todayYmd(),
    busy: false,
    err: "",
  };

  const pattern = () => (st.mode === "baltika" ? BALTIKA : cleanPattern(st.custom));
  const preview = (pat) => {
    const today = todayYmd();
    return Array.from({ length: PREVIEW_DAYS }, (_, i) => {
      const d = shiftYmd(today, i);
      return { d, k: kindOn(pat, st.anchor, d), today: i === 0 };
    });
  };
  const gridHtml = (pat) =>
    pat
      ? preview(pat).map(({ d, k, today }) => {
          const dt = new Date(d + "T12:00:00");
          return `<div class="sg-cell ${KIND_CLS[k]} ${today ? "today" : ""}">
            <span class="sg-wd">${WD[dt.getDay()]}</span><b>${dt.getDate()}</b><span class="sg-k">${KIND_SHORT[k]}</span>
          </div>`;
        }).join("")
      : `<div class="muted setup-hint">Введи цикл, и здесь появится календарь</div>`;

  const firstHint = (pat) => (pat ? `В эту дату стоит первая буква цикла: <b>${KIND_ADJ[pat[0]]}</b> смена.` : "");
  const errText = (pat) => {
    if (st.err) return st.err;
    if (st.mode === "custom" && st.custom.trim() && !pat) return "Цикл не читается: только Д (день), Н (ночь), В (выходной) и хотя бы одна смена";
    return "";
  };

  function render() {
    const pat = pattern();
    const chips = [["Сегодня", 0], ["Вчера", -1], ["Позавчера", -2]]
      .map(([label, n]) => {
        const v = shiftYmd(todayYmd(), n);
        return `<button class="opt press ${st.anchor === v ? "on" : ""}" data-anchor="${v}">${label}</button>`;
      })
      .join("");
    host.innerHTML = `
      <div class="setup-wrap">
        <header class="setup-top">
          ${onBack ? `<button class="ib press" data-act="back" aria-label="Назад">←</button>` : ""}
          <div>
            <h1 class="setup-h">${editing ? "Изменить график" : "Настрой график"}</h1>
            <div class="muted">${editing ? "Поменяй цикл или дату, календарь пересчитается" : "Три шага, и бот начнёт напоминать"}</div>
          </div>
        </header>

        <section class="card glass setup-card">
          <div class="setup-step"><b>1</b>Цикл смен</div>
          <button class="setup-pat press ${st.mode === "baltika" ? "on" : ""}" data-mode="baltika">
            <span class="setup-strip">${BALTIKA.split("").map((k) => `<i class="${KIND_CLS[k]}"></i>`).join("")}</span>
            <span>2 дневные · выходной · 2 ночные · 3 выходных</span>
          </button>
          <button class="setup-pat press ${st.mode === "custom" ? "on" : ""}" data-mode="custom">
            <span>✏️ Свой цикл</span>
          </button>
          ${st.mode === "custom" ? `
            <label class="fld">Буквами: Д — день, Н — ночь, В — выходной
              <input id="sCustom" value="${esc(st.custom)}" placeholder="например ДДВННВВВ" autocapitalize="characters" autocomplete="off">
            </label>` : ""}
        </section>

        <section class="card glass setup-card">
          <div class="setup-step"><b>2</b>Дата первой смены цикла</div>
          <div class="muted setup-hint" id="sFirst">${firstHint(pat)}</div>
          <div class="opts">${chips}</div>
          <label class="fld"><input type="date" id="sDate" value="${st.anchor}"></label>
        </section>

        <section class="card glass setup-card">
          <div class="setup-step"><b>3</b>Проверь календарь</div>
          <div class="muted setup-hint">Сверь с графиком на заводе. Если совпадает, подтверди.</div>
          <div class="setup-grid" id="sGrid">${gridHtml(pat)}</div>
          <button class="btn accept press" id="sSave" ${pat && !st.busy ? "" : "disabled"}>
            ${st.busy ? "Сохраняю…" : "Да, совпадает, сохранить"}
          </button>
          <div class="setup-err" id="sErr">${esc(errText(pat))}</div>
        </section>
      </div>`;
  }

  /* быстрое обновление без перерисовки поля ввода, чтобы не терять фокус */
  function refresh() {
    const pat = pattern();
    host.querySelector("#sGrid").innerHTML = gridHtml(pat);
    host.querySelector("#sFirst").innerHTML = firstHint(pat);
    host.querySelector("#sSave").disabled = !pat || st.busy;
    host.querySelector("#sErr").textContent = errText(pat);
  }

  async function save() {
    const pat = pattern();
    if (!pat || st.busy) return;
    st.busy = true;
    st.err = "";
    render();
    try {
      await api("/api/setup", { method: "POST", body: JSON.stringify({ pattern: pat, anchor: st.anchor }) });
      try { tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred("success"); } catch (_) {}
      if (onDone) onDone();
    } catch (e) {
      st.busy = false;
      st.err = ERR[e.message] || "Не получилось сохранить, попробуй ещё раз";
      render();
    }
  }

  host.onclick = (e) => {
    const mode = e.target.closest("[data-mode]");
    if (mode) { st.mode = mode.dataset.mode; st.err = ""; return render(); }
    const anchor = e.target.closest("[data-anchor]");
    if (anchor) { st.anchor = anchor.dataset.anchor; st.err = ""; return render(); }
    if (e.target.closest("#sSave")) return save();
    if (e.target.closest("[data-act='back']") && onBack) return onBack();
  };
  host.oninput = (e) => {
    if (e.target.id === "sCustom") { st.custom = e.target.value; st.err = ""; refresh(); }
  };
  host.onchange = (e) => {
    if (e.target.id === "sDate" && e.target.value) { st.anchor = e.target.value; st.err = ""; render(); }
  };

  render();
}
