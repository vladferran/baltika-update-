-- Развозка: маршрут и напоминания об автобусе.
-- Идемпотентно — можно запускать повторно.

ALTER TABLE users ADD COLUMN IF NOT EXISTS shuttle_route  VARCHAR(24);
ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_bus_min INTEGER NOT NULL DEFAULT 30;
ALTER TABLE users ADD COLUMN IF NOT EXISTS bus_buffer_min INTEGER NOT NULL DEFAULT 20;

-- на случай, если база была создана до появления этих полей
ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_home_min  INTEGER NOT NULL DEFAULT 80;
ALTER TABLE users ADD COLUMN IF NOT EXISTS weekend_min_days INTEGER NOT NULL DEFAULT 2;
