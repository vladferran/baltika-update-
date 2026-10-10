-- Погода в сообщениях. Идемпотентно.
ALTER TABLE users ADD COLUMN IF NOT EXISTS show_weather BOOLEAN NOT NULL DEFAULT TRUE;
