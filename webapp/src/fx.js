/* Движение интерфейса на библиотеке Motion (motion.dev).
 * Все эффекты уважают «уменьшение движения» в настройках телефона. */
import { animate, stagger, inView } from "motion";
import { liquidOffset } from "./mug.js";

export const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
export const canHover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
const EASE = [0.2, 0.8, 0.2, 1];
const SPRING_SOFT = { type: "spring", stiffness: 380, damping: 30 };

/* Появление блоков каскадом (с размытием в фокус) */
export function reveal(root, selector = "[data-r]", gap = 0.07) {
  if (!root) return;
  const els = [...root.querySelectorAll(selector)];
  if (!els.length || reduce) return;
  animate(
    els,
    {
      opacity: [0, 1],
      transform: ["translateY(24px) scale(0.97)", "translateY(0px) scale(1)"],
      filter: ["blur(8px)", "blur(0px)"],
    },
    { duration: 0.85, delay: stagger(gap, { startDelay: 0.04 }), ease: EASE }
  );
}

/* Элементы, которые появляются при прокрутке в зону видимости */
export function revealOnScroll(root, selector = "[data-iv]") {
  if (reduce) return;
  root.querySelectorAll(selector).forEach((el) => {
    inView(
      el,
      () => {
        animate(el, { opacity: [0, 1], transform: ["translateY(18px)", "translateY(0px)"] }, { duration: 0.7, ease: EASE });
      },
      { amount: 0.12 }
    );
  });
}

/* Числа считаются от нуля до значения */
export function countUp(el, to, duration = 1.2) {
  const target = Number(to) || 0;
  if (reduce) { el.textContent = target; return; }
  animate(0, target, {
    duration,
    ease: "easeOut",
    onUpdate: (v) => { el.textContent = Math.round(v); },
  });
}

/* Заливка кружек: пиво льётся снизу вверх, пена появляется чуть позже */
export function fillMugs(root) {
  root.querySelectorAll(".mug").forEach((svg, i) => {
    const level = Number(svg.dataset.level) || 0;
    const liquid = svg.querySelector(".mug-liquid");
    const foam = svg.querySelector(".mug-foam");
    const wave = svg.querySelector(".mug-wave");
    const to = liquidOffset(level);
    if (reduce) {
      liquid.style.transform = `translateY(${to}px)`;
      return;
    }
    animate(liquid, { transform: [`translateY(${liquidOffset(0)}px)`, `translateY(${to}px)`] }, {
      duration: 1.8, delay: 0.25 + i * 0.12, ease: [0.3, 0.7, 0.2, 1],
    });
    animate(foam, { opacity: [0, 1], transform: ["translateY(4px)", "translateY(0px)"] }, {
      duration: 0.9, delay: 1.2 + i * 0.12, ease: EASE,
    });
    animate(wave, { transform: ["translateX(0px)", "translateX(-36px)"] }, {
      duration: 2.4, repeat: Infinity, ease: "linear",
    });
  });
}

/* Полоса прогресса смены: заливка и бегущий блик */
export function fillBar(el, pct) {
  if (!el) return;
  if (reduce) { el.style.width = `${pct}%`; return; }
  animate(el, { width: ["0%", `${pct}%`] }, { duration: 1.6, delay: 0.3, ease: EASE });
}

/* Метр в карточке стажа */
export function fillMeter(root) {
  root.querySelectorAll("[data-meter]").forEach((el, i) => {
    const pct = Number(el.dataset.meter) || 0;
    if (reduce) { el.style.width = `${pct}%`; return; }
    animate(el, { width: ["0%", `${pct}%`] }, { duration: 1.3, delay: 0.5 + i * 0.1, ease: EASE });
  });
}

/* Нажатие: пружинное сжатие + волна из точки касания */
export function bindPress(root) {
  if (reduce) return;
  root.addEventListener("pointerdown", (e) => {
    const el = e.target.closest(".press");
    if (!el) return;
    animate(el, { scale: 0.965 }, { type: "spring", stiffness: 700, damping: 36 });
    const r = el.getBoundingClientRect();
    const size = Math.max(r.width, r.height) * 1.6;
    const wave = document.createElement("span");
    wave.className = "ripple";
    wave.style.width = wave.style.height = `${size}px`;
    wave.style.left = `${e.clientX - r.left - size / 2}px`;
    wave.style.top = `${e.clientY - r.top - size / 2}px`;
    el.appendChild(wave);
    animate(wave, { scale: [0.2, 1], opacity: [0.45, 0] }, { duration: 0.7, ease: EASE });
    setTimeout(() => wave.remove(), 760);
    const up = () => {
      animate(el, { scale: 1 }, { type: "spring", stiffness: 420, damping: 20 });
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  });
}

/* Всплытие карточки (например, выбранного дня) */
export function pop(el) {
  if (!el || reduce) return;
  animate(el, { opacity: [0.3, 1], transform: ["translateY(10px) scale(0.985)", "translateY(0px) scale(1)"] }, { duration: 0.45, ease: EASE });
}

/* Наклон героя за курсором (только на устройствах с мышью) */
export function bindTilt(root) {
  if (!canHover || reduce) return;
  root.addEventListener("pointermove", (e) => {
    const card = e.target.closest(".tilt");
    if (!card) return;
    const inner = card.querySelector(".tilt-in");
    if (!inner) return;
    const r = card.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    inner.style.transform = `perspective(900px) rotateX(${(-y * 7).toFixed(2)}deg) rotateY(${(x * 9).toFixed(2)}deg)`;
  });
  root.addEventListener("pointerout", (e) => {
    const card = e.target.closest && e.target.closest(".tilt");
    if (!card || card.contains(e.relatedTarget)) return;
    const inner = card.querySelector(".tilt-in");
    if (inner) inner.style.transform = "";
  });
}

/* Свет за курсором на карточках */
export function bindLight(root) {
  if (!canHover || reduce) return;
  root.addEventListener("pointermove", (e) => {
    const c = e.target.closest(".card, .metric, .dcell, .drow, .lkbtn");
    if (!c) return;
    const r = c.getBoundingClientRect();
    c.style.setProperty("--mx", `${e.clientX - r.left}px`);
    c.style.setProperty("--my", `${e.clientY - r.top}px`);
    c.classList.add("lit");
  });
}

/* Пузырьки, поднимающиеся внутри героя */
export function bubbles(container, n = 10) {
  if (reduce || !container) return;
  for (let i = 0; i < n; i++) {
    const b = document.createElement("i");
    b.className = "bub";
    const size = 5 + Math.random() * 14;
    b.style.width = `${size}px`;
    b.style.height = `${size}px`;
    b.style.left = `${4 + Math.random() * 92}%`;
    container.appendChild(b);
    animate(
      b,
      {
        y: [0, -(120 + Math.random() * 120)],
        x: [0, (Math.random() - 0.5) * 22],
        opacity: [0, 0.85, 0],
        scale: [0.7, 1.05],
      },
      { duration: 3.6 + Math.random() * 2.6, delay: Math.random() * 3.5, repeat: Infinity, ease: "easeIn" }
    );
  }
}

/* Салют из пузырьков в точке (голосование «Я за») */
export function burst(x, y, n = 16) {
  if (reduce) return;
  for (let i = 0; i < n; i++) {
    const s = document.createElement("i");
    s.className = "spark";
    s.style.left = `${x}px`;
    s.style.top = `${y}px`;
    document.body.appendChild(s);
    const a = Math.random() * Math.PI * 2;
    const d = 46 + Math.random() * 80;
    animate(
      s,
      { x: [0, Math.cos(a) * d], y: [0, Math.sin(a) * d - 34], opacity: [1, 0], scale: [1, 0.3] },
      { duration: 0.95, delay: Math.random() * 0.12, ease: EASE }
    );
    setTimeout(() => s.remove(), 1200);
  }
}

/* Подвижка индикатора в нижнем меню */
export function moveNavIndicator(ind, index) {
  if (!ind) return;
  const w = ind.offsetWidth;
  if (reduce) { ind.style.transform = `translateX(${index * w}px)`; return; }
  animate(ind, { x: index * w }, SPRING_SOFT);
}

/* Экран загрузки: кружка наполняется, пока идёт запрос */
export function hideLoader(loader) {
  if (!loader) return;
  if (reduce) { loader.remove(); return; }
  loader.classList.add("done");
  setTimeout(() => loader.remove(), 650);
}

/* Переключатель: подсветка ставится без анимации и скользит между вариантами */
export function placeSeg(ind, index) {
  if (!ind) return;
  ind.dataset.i = String(index);
  ind.style.transform = `translateX(${index * ind.offsetWidth}px)`;
}
export function slideSeg(ind, index) {
  if (!ind) return;
  const w = ind.offsetWidth;
  const from = Number(ind.dataset.i) || 0;
  ind.dataset.i = String(index);
  if (reduce) { ind.style.transform = `translateX(${index * w}px)`; return; }
  animate(ind, { x: [from * w, index * w] }, SPRING_SOFT);
}
