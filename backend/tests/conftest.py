import os
import sys
from pathlib import Path

# Dummy settings so the app imports without real secrets. Nothing in these tests calls GitHub, Gemini or the database.
for key, value in {
    "DATABASE_URL": "postgresql://unused@127.0.0.1:1/unused",
    "GITHUB_WEBHOOK_SECRET": "test-secret",
    "GITHUB_APP_ID": "1",
    "GITHUB_CLIENT_ID": "test",
    "GEMINI_API_KEY": "test",
    "API_TOKEN": "test-token",
}.items():
    os.environ[key] = value

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
