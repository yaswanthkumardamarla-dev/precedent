"""Settings for Precedent, read from backend/.env (or real environment variables when hosted)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
GITHUB_APP_ID = os.environ["GITHUB_APP_ID"]
GITHUB_CLIENT_ID = os.environ["GITHUB_CLIENT_ID"].strip()
GITHUB_PRIVATE_KEY_PATH = os.environ.get("GITHUB_PRIVATE_KEY_PATH", "github-app.pem")
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = 768

# Shared secret the dashboard sends to read and change data. Without it, /api/* refuses every request.
API_TOKEN = os.environ.get("API_TOKEN", "").strip()


def github_private_key() -> str:
    """Return the GitHub App private key.

    Locally it is read from the .pem file. When hosted, the key's text goes in
    the GITHUB_PRIVATE_KEY environment variable instead, since there is no file.
    """
    key = os.environ.get("GITHUB_PRIVATE_KEY")
    if key:
        return key
    path = Path(GITHUB_PRIVATE_KEY_PATH)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path.read_text()