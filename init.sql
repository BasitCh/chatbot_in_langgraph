-- Chainlit 2.11.x SQLAlchemyDataLayer schema (Postgres).
-- Tables/columns derived from chainlit/data/sql_alchemy.py in v2.11.1.
-- Safe to re-run: it drops only chainlit's tables, not LangGraph's
-- checkpoint_* tables.

-- 1. Drop any prior chainlit tables (both old PascalCase and lowercase plural
--    variants) so we converge on one schema.
DROP TABLE IF EXISTS feedbacks CASCADE;
DROP TABLE IF EXISTS elements  CASCADE;
DROP TABLE IF EXISTS steps     CASCADE;
DROP TABLE IF EXISTS threads   CASCADE;
DROP TABLE IF EXISTS users     CASCADE;

DROP TABLE IF EXISTS "Feedback" CASCADE;
DROP TABLE IF EXISTS "Element"  CASCADE;
DROP TABLE IF EXISTS "Step"     CASCADE;
DROP TABLE IF EXISTS "Thread"   CASCADE;
DROP TABLE IF EXISTS "User"     CASCADE;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. users -----------------------------------------------------------------
CREATE TABLE users (
    id          UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
    identifier  TEXT  NOT NULL UNIQUE,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    "createdAt" TEXT
);

-- 3. threads ---------------------------------------------------------------
CREATE TABLE threads (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "createdAt"      TEXT,
    name             TEXT,
    "userId"         UUID REFERENCES users(id) ON DELETE CASCADE,
    "userIdentifier" TEXT,
    tags             TEXT[],
    metadata         JSONB DEFAULT '{}'::jsonb
);

-- 4. steps -----------------------------------------------------------------
CREATE TABLE steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT,
    type            TEXT NOT NULL,
    "threadId"      UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    "parentId"      UUID,
    streaming       BOOLEAN NOT NULL DEFAULT false,
    "waitForAnswer" BOOLEAN,
    "isError"       BOOLEAN NOT NULL DEFAULT false,
    metadata        JSONB   DEFAULT '{}'::jsonb,
    tags            TEXT[],
    input           TEXT,
    output          TEXT,
    "createdAt"     TEXT,
    command         TEXT,
    start           TEXT,
    "end"           TEXT,
    generation      JSONB,
    "showInput"     TEXT DEFAULT 'json',
    language        TEXT,
    indent          INTEGER,
    "defaultOpen"   BOOLEAN DEFAULT false,
    "autoCollapse"  BOOLEAN DEFAULT false,
    modes           JSONB
);

-- 5. elements --------------------------------------------------------------
CREATE TABLE elements (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "threadId"    UUID REFERENCES threads(id) ON DELETE CASCADE,
    type          TEXT,
    url           TEXT,
    "chainlitKey" TEXT,
    name          TEXT NOT NULL,
    display       TEXT,
    "objectKey"   TEXT,
    size          TEXT,
    page          INTEGER,
    language      TEXT,
    "forId"       UUID,
    mime          TEXT,
    props         JSONB
);

-- 6. feedbacks -------------------------------------------------------------
CREATE TABLE feedbacks (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "forId"    UUID NOT NULL,
    "threadId" UUID,
    value      INTEGER NOT NULL,
    comment    TEXT
);

-- 7. indexes that keep the thread sidebar + history queries fast -----------
CREATE INDEX idx_users_identifier         ON users(identifier);
CREATE INDEX idx_threads_user             ON threads("userId");
CREATE INDEX idx_threads_useridentifier   ON threads("userIdentifier");
CREATE INDEX idx_threads_createdat        ON threads("createdAt" DESC);
CREATE INDEX idx_steps_thread             ON steps("threadId");
CREATE INDEX idx_steps_parent             ON steps("parentId");
CREATE INDEX idx_steps_createdat          ON steps("createdAt");
CREATE INDEX idx_steps_thread_createdat   ON steps("threadId", "createdAt");
CREATE INDEX idx_elements_thread          ON elements("threadId");
CREATE INDEX idx_elements_for             ON elements("forId");
CREATE INDEX idx_feedbacks_for            ON feedbacks("forId");
