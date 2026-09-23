"""
Create the reports table in the configured Postgres database.

Usage:
    DATABASE_URL=postgres://... python scripts/init_db.py
"""

import os
import sys

import psycopg

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


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
        conn.commit()

    print("Schema created (or already present).")


if __name__ == "__main__":
    main()
