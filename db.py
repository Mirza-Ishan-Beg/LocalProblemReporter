"""
Database helpers for Local Problem Reporter.

Exposes:
    init_db()  — idempotent, creates the schema if missing
    get_db()   — returns a per-request connection (via Flask's g)
    close_db() — teardown handler
"""

import os

import psycopg
from psycopg.rows import dict_row

from flask import g

DATABASE_URL = os.environ.get("DATABASE_URL", "")

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id          SERIAL       PRIMARY KEY,
    name        VARCHAR(80)  NOT NULL,
    category    VARCHAR(32)  NOT NULL,
    location    VARCHAR(200) NOT NULL,
    description TEXT         NOT NULL,
    photo       BYTEA,
    photo_type  VARCHAR(50),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_category ON reports(category);
"""

def init_db(app=None):
    """Create schema if missing. Safe to call on every startup."""
    if not DATABASE_URL:
        if app:
            app.logger.warning("DATABASE_URL not set; skipping schema init.")
        else:
            print("DATABASE_URL not set; skipping schema init.")
        return

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA)
            conn.commit()
        if app:
            app.logger.info("Schema ready.")
        else:
            print("Schema ready.")
    except Exception:
        if app:
            app.logger.exception("Schema init failed")
        else:
            raise


def get_db():
    if "db" not in g:
        g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass
