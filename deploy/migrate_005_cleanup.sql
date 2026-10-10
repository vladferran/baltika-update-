-- Автоочистка чата и админ-панель. Идемпотентно.

ALTER TABLE users ADD COLUMN IF NOT EXISTS autoclean       BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS clean_after_min INTEGER NOT NULL DEFAULT 180;

CREATE TABLE IF NOT EXISTS pending_deletes (
    id         SERIAL PRIMARY KEY,
    chat_id    BIGINT      NOT NULL,
    message_id INTEGER     NOT NULL,
    delete_at  TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_pending_delete UNIQUE (chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS ix_pending_deletes_chat_id   ON pending_deletes (chat_id);
CREATE INDEX IF NOT EXISTS ix_pending_deletes_delete_at ON pending_deletes (delete_at);
