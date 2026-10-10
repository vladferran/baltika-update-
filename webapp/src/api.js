/* Связь с сервером. Все запросы подписываются initData от Telegram. */

export const tg = window.Telegram && window.Telegram.WebApp;
export const INIT = tg ? tg.initData : "";

// В превью-сборке (VITE_MOCK) подменяем сеть вымышленными данными.
// В боевой сборке этот импорт вырезается целиком.
export const ready = import.meta.env.VITE_MOCK ? import("./mock.js") : Promise.resolve();

export async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", "X-Init-Data": INIT, ...(opts.headers || {}) },
  });
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error((data && data.error) || `HTTP ${res.status}`);
  return data;
}
