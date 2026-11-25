import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import config
from app.extract import normalize
from app.main import app, plan_job

client = TestClient(app)

HUMAN = {"type": "User"}


def pr_event(action, draft=False, number=7):
    return {"action": action, "sender": HUMAN, "pull_request": {"number": number, "draft": draft}}


@pytest.mark.parametrize(
    "event, payload, expected",
    [
        ("pull_request", pr_event("opened"), ("check", 7)),
        ("pull_request", pr_event("synchronize"), ("check", 7)),
        ("pull_request", pr_event("opened", draft=True), None),
        ("pull_request", pr_event("closed"), ("extract", 7)),
        ("pull_request", pr_event("labeled"), None),
        ("pull_request", {**pr_event("opened"), "sender": {"type": "Bot"}}, None),
        ("pull_request_review_comment", pr_event("created"), ("extract", 7)),
        ("pull_request_review", {**pr_event("submitted"), "review": {"body": ""}}, None),
        ("pull_request_review", {**pr_event("submitted"), "review": {"body": "LGTM, but always..."}}, ("extract", 7)),
        ("issue_comment", {"action": "created", "sender": HUMAN, "issue": {"number": 3, "pull_request": {}}}, ("extract", 3)),
        ("issue_comment", {"action": "created", "sender": HUMAN, "issue": {"number": 3}}, None),
        ("push", {"sender": HUMAN}, None),
    ],
)
def test_plan_job(event, payload, expected):
    assert plan_job(event, payload) == expected


def test_webhook_rejects_missing_and_bad_signatures():
    body = json.dumps({"action": "opened"}).encode()
    headers = {"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "test-1"}
    assert client.post("/webhooks/github", content=body, headers=headers).status_code == 401
    bad = {**headers, "X-Hub-Signature-256": "sha256=" + "0" * 64}
    assert client.post("/webhooks/github", content=body, headers=bad).status_code == 401


def test_webhook_signature_matches_github_scheme():
    from app.main import verify_signature

    body = b'{"zen": "hi"}'
    signature = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    verify_signature(body, signature)  # does not raise


def test_api_requires_token():
    assert client.get("/api/summary").status_code == 401
    assert client.get("/api/summary", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_api_is_locked_when_token_unset(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "")
    assert client.get("/api/summary", headers={"Authorization": "Bearer "}).status_code == 503


def test_api_rejects_unknown_status():
    response = client.patch(
        "/api/decisions/1", json={"status": "deleted"}, headers={"Authorization": "Bearer test-token"}
    )
    assert response.status_code == 422


def test_normalize_ignores_case_and_trailing_period():
    assert normalize("  Use UTC everywhere. ") == normalize("use utc everywhere")


def test_evidence_is_rendered_on_one_line():
    from app.check import one_line_code

    assert one_line_code('@app.get("/x")\ndef f(a):') == '`@app.get("/x") ⏎ def f(a):`'
    assert one_line_code("") == "(not given)"
