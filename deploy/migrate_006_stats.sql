-- Стаж и посещаемость. Идемпотентно.

ALTER TABLE users ADD COLUMN IF NOT EXISTS hired_at       DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_checkin BOOLEAN NOT NULL DEFAULT TRUE;

CREATE TABLE IF NOT EXISTS attendance (
    id         SERIAL PRIMARY KEY,
    user_id    BIGINT      NOT NULL,
    shift_date DATE        NOT NULL,
    status     VARCHAR(16) NOT NULL,
    note       VARCHAR(200),
    marked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_attendance UNIQUE (user_id, shift_date)
);

CREATE INDEX IF NOT EXISTS ix_attendance_user_id ON attendance (user_id);
