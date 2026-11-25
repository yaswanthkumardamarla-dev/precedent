"""Settings for Precedent, read from backend/.env (or real environment variables when hosted)."""
import os
import re
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
GITHUB_APP_ID = os.environ["GITHUB_APP_ID"]
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


PEM_PATTERN = re.compile(r"(-----BEGIN [A-Z ]+-----)(.*?)(-----END [A-Z ]+-----)", re.DOTALL)


def normalize_pem(key: str) -> str:
    """Rebuild a PEM key whose line breaks were lost when pasted into a hosting dashboard.

    Handles breaks turned into spaces, written as a literal \\n, or removed entirely, and stray quotes.
    """
    key = key.strip().strip("\"'").replace("\\n", "\n")
    match = PEM_PATTERN.search(key)
    if not match:
        return key
    header, body, footer = match.groups()
    body = "".join(body.split())  # the base64 body, with every space and line break removed
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return "\n".join([header, *lines, footer]) + "\n"


def _key_file() -> Path:
    path = Path(GITHUB_PRIVATE_KEY_PATH)
    return path if path.is_absolute() else BACKEND_DIR / path


def github_private_key() -> str:
    """Return the GitHub App private key.

    From the file at GITHUB_PRIVATE_KEY_PATH when it exists: locally backend/github-app.pem, and on
    Render a Secret File (/etc/secrets/github-app.pem). Otherwise from the GITHUB_PRIVATE_KEY variable.
    """
    path = _key_file()
    if path.is_file():
        return path.read_text()
    key = os.environ.get("GITHUB_PRIVATE_KEY")
    if key:
        return normalize_pem(key)
    raise RuntimeError(f"No GitHub App private key: {path} does not exist and GITHUB_PRIVATE_KEY is not set")


def describe_github_key() -> str:
    """Say where the key comes from and whether it loads, without revealing any of it."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    source = f"file {_key_file()}" if _key_file().is_file() else "GITHUB_PRIVATE_KEY variable"
    try:
        text = github_private_key()
    except RuntimeError as error:
        return f"MISSING: {error}"
    try:
        load_pem_private_key(text.encode(), password=None)
        return f"OK, from {source}"
    except Exception as error:
        markers = ("BEGIN" in text, "END" in text)
        return (f"INVALID, from {source}: {type(error).__name__}; {len(text)} characters, "
                f"BEGIN line {'present' if markers[0] else 'missing'}, END line {'present' if markers[1] else 'missing'}")
