import os
import sys
from pathlib import Path

import pytest

# Test settings, so the app imports without real secrets. Nothing here calls GitHub or Gemini.
# Database tests use a separate database (never the real one); CI provides one, locally it's
# `precedent_test` in the docker-compose Postgres.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://precedent:precedent@127.0.0.1:5432/precedent_test?connect_timeout=3"
)
for key, value in {
    "DATABASE_URL": TEST_DATABASE_URL,
    "GITHUB_WEBHOOK_SECRET": "test-secret",
    "GITHUB_CLIENT_ID": "test",
    "GEMINI_API_KEY": "test",
    "API_TOKEN": "test-token",
    "REDELIVERY_SWEEP_SECONDS": "0",
    "DEMO_REPOS": "",
}.items():
    os.environ[key] = value

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_migrated = False


@pytest.fixture
def db():
    """An empty test database. Skipped when none is reachable, unless REQUIRE_DB=1 (as in CI)."""
    global _migrated
    import psycopg

    from app.migrate import migrate

    try:
        psycopg.connect(TEST_DATABASE_URL).close()
    except psycopg.OperationalError as error:
        if os.environ.get("REQUIRE_DB") == "1":
            raise
        pytest.skip(f"no test database: {error}")
    if not _migrated:
        migrate()
        _migrated = True
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute("TRUNCATE conflicts, decisions, webhook_events RESTART IDENTITY CASCADE")
    yield TEST_DATABASE_URL
