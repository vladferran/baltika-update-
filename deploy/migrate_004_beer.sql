-- Опрос «по пиву» после дневной смены. Идемпотентно.

ALTER TABLE users ADD COLUMN IF NOT EXISTS beer_enabled BOOLEAN NOT NULL DEFAULT TRUE;

CREATE TABLE IF NOT EXISTS beer_events (
    id           SERIAL PRIMARY KEY,
    shift_end    TIMESTAMPTZ  NOT NULL UNIQUE,
    place        VARCHAR(200) NOT NULL,
    summary_sent BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS beer_votes (
    id       SERIAL PRIMARY KEY,
    event_id INTEGER     NOT NULL REFERENCES beer_events(id) ON DELETE CASCADE,
    user_id  BIGINT      NOT NULL,
    yes      BOOLEAN     NOT NULL,
    voted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_beer_vote UNIQUE (event_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_beer_votes_event_id ON beer_votes (event_id);
CREATE INDEX IF NOT EXISTS ix_beer_votes_user_id  ON beer_votes (user_id);
