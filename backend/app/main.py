"""Precedent's web server: a health check and the GitHub webhook."""
import hashlib
import hmac
import json
import os
import traceback
from contextlib import asynccontextmanager

import psycopg
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from psycopg.types.json import Jsonb

from app import config  # loads backend/.env
from app.api import router as api_router
from app.check import check_pr
from app.extract import extract_pr
from app.redeliver import start_background_sweeps

WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]



@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_background_sweeps()
    yield


app = FastAPI(title="Precedent", lifespan=lifespan)
app.include_router(api_router)


@app.get("/health")
def health():
    with psycopg.connect(config.DATABASE_URL) as conn:
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


def plan_job(event: str, payload: dict) -> tuple[str, int] | None:
    """Decide what to do for a webhook event: ("check" or "extract", PR number), or None."""
    sender = payload.get("sender") or {}
    if sender.get("type") == "Bot":
        return None  # ignore bots, including Precedent itself, so we never react to our own comments

    action = payload.get("action")

    if event == "pull_request":
        pr = payload["pull_request"]
        if action in {"opened", "reopened", "synchronize", "ready_for_review"} and not pr.get("draft"):
            return ("check", pr["number"])
        if action == "closed":
            return ("extract", pr["number"])

    if event == "pull_request_review_comment" and action in {"created", "edited"}:
        return ("extract", payload["pull_request"]["number"])

    if event == "pull_request_review" and action == "submitted":
        # Inline comments already arrive as their own events; only a review's summary text adds anything.
        if (payload.get("review") or {}).get("body"):
            return ("extract", payload["pull_request"]["number"])

    if event == "issue_comment" and action in {"created", "edited"}:
        issue = payload.get("issue") or {}
        if "pull_request" in issue:  # a comment on a PR, not on a plain issue
            return ("extract", issue["number"])

    return None


def set_status(delivery_id: str, status: str, error: str | None = None) -> None:
    with psycopg.connect(config.DATABASE_URL) as conn:
        conn.execute(
            "UPDATE webhook_events SET status = %s, error = %s, finished_at = now() WHERE delivery_id = %s",
            (status, error, delivery_id),
        )


def run_job(delivery_id: str, job: str, repo: str, number: int) -> None:
    """Runs in the background after GitHub has already received its reply."""
    print(f"[job] {job} {repo}#{number} starting", flush=True)
    try:
        if job == "check":
            check_pr(repo, number, post=True)
        else:
            extract_pr(repo, number)
        set_status(delivery_id, "done")
        print(f"[job] {job} {repo}#{number} done", flush=True)
    except Exception:
        error = traceback.format_exc()
        print(f"[job] {job} {repo}#{number} FAILED\n{error}", flush=True)
        set_status(delivery_id, "failed", error)


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(...),
    x_github_delivery: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
):
    body = await request.body()
    verify_signature(body, x_hub_signature_256)
    payload = json.loads(body)

    action = payload.get("action")
    repo = (payload.get("repository") or {}).get("full_name")
    planned = plan_job(x_github_event, payload)
    job = planned[0] if planned else None

    with psycopg.connect(config.DATABASE_URL) as conn:
        conn.execute(
            """
            INSERT INTO webhook_events (delivery_id, event, action, repo, payload, job, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (delivery_id) DO UPDATE
                SET job = EXCLUDED.job, status = EXCLUDED.status, error = NULL, finished_at = NULL
            """,
            (x_github_delivery, x_github_event, action, repo, Jsonb(payload),
             job, "queued" if planned else "ignored"),
        )

    print(f"[webhook] {x_github_event} {action or ''} {repo or ''} -> {job or 'ignored'}", flush=True)

    if planned:
        background_tasks.add_task(run_job, x_github_delivery, job, repo, planned[1])

    return {"ok": True, "job": job}