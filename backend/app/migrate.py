"""Apply schema.sql to the database. Safe to run any number of times.

Usage (from the backend folder):  python -m app.migrate
"""
import psycopg

from app import config


def migrate() -> None:
    schema = (config.BACKEND_DIR / "schema.sql").read_text()
    with psycopg.connect(config.DATABASE_URL) as conn:
        conn.execute(schema)  # no parameters, so several statements may run at once
    print("schema is up to date", flush=True)


if __name__ == "__main__":
    migrate()
