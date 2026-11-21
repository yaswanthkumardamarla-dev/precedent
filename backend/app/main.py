import hashlib
import hmac
import json
import os

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from psycopg.types.json import Jsonb

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]

app = FastAPI(title="Precedent")


@app.get("/health")
def health():
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
    return {"status": "ok", "pgvector": row[0] if row else None}


def verify_signature(body: bytes, signature: str | None) -> None:
    """Reject any request that wasn't signed by GitHub with our secret."""
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_github_delivery: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
):
    body = await request.body()
    verify_signature(body, x_hub_signature_256)
    payload = json.loads(body)

    action = payload.get("action")
    repo = (payload.get("repository") or {}).get("full_name")

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """
            INSERT INTO webhook_events (delivery_id, event, action, repo, payload)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (delivery_id) DO NOTHING
            """,
            (x_github_delivery, x_github_event, action, repo, Jsonb(payload)),
        )

    print(f"[webhook] {x_github_event} {action or ''} {repo or ''}")
    return {"ok": True}