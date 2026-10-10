/* Пивная кружка в SVG: стекло с ручкой и бликами, пиво с градиентом,
 * колышущаяся поверхность, пена, карбонизация и конденсат.
 * Уровень (0..1) меняет положение жидкости, анимацию запускает fx.js. */

let uid = 0;

// Координаты: вьюпорт 120×158. Стакан: верх y=34, низ y=146.
const TOP = 34;
const BOTTOM = 146;
const SPAN = BOTTOM - TOP;

/** translateY жидкости (в единицах viewBox) для заданного уровня 0..1 */
export function liquidOffset(level) {
  const l = Math.min(1, Math.max(0, level));
  return SPAN * (1 - l);
}

const BUBBLES = [
  // [cx, cy, r, delay(s), duration(s)]
  [42, 58, 1.6, 0.0, 2.8], [58, 74, 1.2, 0.9, 3.2], [70, 50, 1.9, 1.5, 2.6],
  [50, 92, 1.1, 2.1, 3.0], [64, 36, 1.4, 0.4, 2.9], [36, 84, 1.0, 1.8, 3.4],
  [76, 88, 1.3, 2.6, 2.7],
];

const FOAM_BUBBLES = [
  [36, -4, 2.4], [48, -7, 1.8], [58, -3, 2.9], [70, -6, 2.0], [80, -3, 1.6], [44, 1, 1.4], [64, 1, 1.5],
];

export function mugSvg(level = 0, { cls = "" } = {}) {
  const id = `mg${++uid}`;
  const off = liquidOffset(level);
  const bubbles = BUBBLES.map(([cx, cy, r, d, t], i) =>
    `<circle class="cb" cx="${cx}" cy="${cy}" r="${r}" style="animation-delay:${d}s;animation-duration:${t}s"/>`
  ).join("");
  const foamBubbles = FOAM_BUBBLES.map(([cx, cy, r], i) =>
    `<circle class="fb" cx="${cx}" cy="${cy}" r="${r}" style="animation-delay:${i * 0.3}s"/>`
  ).join("");

  return `
<svg class="mug ${cls}" data-level="${Math.min(1, Math.max(0, level))}" viewBox="0 0 120 158" aria-hidden="true">
  <defs>
    <linearGradient id="${id}-beer" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffe08c"/>
      <stop offset=".35" stop-color="#f4ad2e"/>
      <stop offset=".75" stop-color="#d07a12"/>
      <stop offset="1" stop-color="#8f4a0c"/>
    </linearGradient>
    <linearGradient id="${id}-foam" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#f1e3bf"/>
    </linearGradient>
    <linearGradient id="${id}-glass" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#fff" stop-opacity=".55"/>
      <stop offset=".16" stop-color="#fff" stop-opacity=".06"/>
      <stop offset=".84" stop-color="#fff" stop-opacity=".03"/>
      <stop offset="1" stop-color="#fff" stop-opacity=".40"/>
    </linearGradient>
    <linearGradient id="${id}-shine" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fff" stop-opacity=".9"/>
      <stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="${id}-shadow" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="#000" stop-opacity=".38"/>
      <stop offset="1" stop-color="#000" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="${id}-clip">
      <path d="M24 16 H84 L80.5 138 Q80.2 144 74 144 H34 Q27.8 144 27.5 138 Z"/>
    </clipPath>
  </defs>

  <ellipse cx="54" cy="155" rx="46" ry="5" fill="url(#${id}-shadow)"/>

  <!-- ручка: подложка и блик -->
  <path d="M86 52 C110 46 117 84 106 100 C100 108 93 110 86 108" fill="none" stroke="rgba(255,255,255,.22)" stroke-width="13" stroke-linecap="round"/>
  <path d="M86 52 C110 46 117 84 106 100 C100 108 93 110 86 108" fill="none" stroke="rgba(255,255,255,.85)" stroke-width="2.4" stroke-linecap="round"/>
  <path d="M86 52 C110 46 117 84 106 100 C100 108 93 110 86 108" fill="none" stroke="rgba(0,0,0,.10)" stroke-width="1" stroke-linecap="round" transform="translate(1.2 1.2)"/>

  <!-- жидкость, обрезанная формой стакана -->
  <g clip-path="url(#${id}-clip)">
    <g transform="translate(0 ${TOP})">
    <g class="mug-liquid" style="transform:translateY(${off}px)">
      <rect x="-20" y="0" width="160" height="200" fill="url(#${id}-beer)"/>
      <g class="mug-wave">
        <path d="M-36 2 Q-18 -3 0 2 T36 2 T72 2 T108 2 T144 2 V9 H-36 Z" fill="rgba(255,236,170,.75)"/>
      </g>
      <g class="mug-foam">
        <path d="M-36 -6 Q-18 -12 0 -6 T36 -6 T72 -6 T108 -6 T144 -6 V2 H-36 Z" fill="url(#${id}-foam)"/>
        ${foamBubbles}
      </g>
      <g class="mug-carb">${bubbles}</g>
    </g>
    </g>
  </g>

  <!-- стекло: корпус, тон, блики, край -->
  <path d="M22 34 H86 L82 138 Q81.6 146 74 146 H34 Q26.4 146 26 138 Z" fill="url(#${id}-glass)" stroke="rgba(255,255,255,.75)" stroke-width="1.6" stroke-linejoin="round"/>
  <path d="M29 42 L33 130" stroke="url(#${id}-shine)" stroke-width="3.4" stroke-linecap="round" opacity=".9"/>
  <path d="M77 46 L74 118" stroke="rgba(255,255,255,.35)" stroke-width="1.6" stroke-linecap="round"/>
  <ellipse cx="54" cy="34" rx="32" ry="4.2" fill="rgba(255,255,255,.35)" stroke="rgba(255,255,255,.9)" stroke-width="1.4"/>
  <g class="mug-drops" fill="rgba(255,255,255,.7)">
    <circle cx="40" cy="70" r="1.1"/><circle cx="46" cy="96" r=".8"/><circle cx="71" cy="82" r="1"/>
    <circle cx="38" cy="112" r=".9"/><circle cx="68" cy="122" r="1.2"/>
  </g>
</svg>`;
}
