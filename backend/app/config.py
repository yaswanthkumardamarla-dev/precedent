"""Settings for Precedent, read from backend/.env (or real environment variables when hosted)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
GITHUB_CLIENT_ID = os.environ["GITHUB_CLIENT_ID"].strip()
GITHUB_PRIVATE_KEY_PATH = os.environ.get("GITHUB_PRIVATE_KEY_PATH", "github-app.pem")
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = 768

# Shared secret the dashboard sends to read and change data. Without it, /api/* refuses every request.
API_TOKEN = os.environ.get("API_TOKEN", "").strip()

# How often to ask GitHub to resend webhooks we missed (e.g. while asleep on a free host). 0 turns it off.
REDELIVERY_SWEEP_SECONDS = int(os.environ.get("REDELIVERY_SWEEP_SECONDS", "300"))


def _key_file() -> Path:
    path = Path(GITHUB_PRIVATE_KEY_PATH)
    return path if path.is_absolute() else BACKEND_DIR / path


def github_private_key() -> str:
    """The GitHub App private key: backend/github-app.pem locally, a Secret File on Render."""
    path = _key_file()
    if not path.is_file():
        raise RuntimeError(f"No GitHub App private key at {path}")
    return path.read_text()


def describe_github_key() -> str:
    """Say whether the key loads, without revealing any of it."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    try:
        load_pem_private_key(github_private_key().encode(), password=None)
        return f"OK, from {_key_file()}"
    except Exception as error:
        return f"NOT USABLE ({type(error).__name__}): {error}"
