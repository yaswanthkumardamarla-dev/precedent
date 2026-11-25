"""Who sees what, and what the webhook does with private repos, limits and uninstalls (against a real database)."""
import hashlib
import hmac
import json
import uuid

import psycopg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import access, api, config
from app import main as main_module
from app.access import Repo, Viewer
from app.extract import to_vector

client = TestClient(main_module.app)
API = {"Authorization": "Bearer test-token"}

ALICE = Viewer(login="alice", repos=(Repo("alice/app", private=False, can_write=True),
                                     Repo("bob/lib", private=False, can_write=False)))


@pytest.fixture
def people(monkeypatch):
    """Token 'alice' belongs to alice; token 'expired' has been revoked on GitHub."""
    def lookup(token):
        if token == "alice":
            return ALICE
        raise HTTPException(status_code=401, detail="GitHub sign-in expired")

    access._cache.clear()
    monkeypatch.setattr(access, "lookup_viewer", lookup)
    monkeypatch.setattr(config, "DEMO_REPOS", ["demo/repo"])
    monkeypatch.setattr(api, "app_slug", lambda: "precedent-test")


def add_decision(url: str, repo: str, statement: str) -> int:
    with psycopg.connect(url) as conn:
        return conn.execute(
            """
            INSERT INTO decisions (repo, pr_number, statement, source_comment_id, source_url, embedding)
            VALUES (%s, 1, %s, 1, 'https://example.com', %s::vector) RETURNING id
            """,
            (repo, statement, to_vector([0.0] * config.EMBEDDING_DIM)),
        ).fetchone()[0]


def as_user(token: str | None) -> dict:
    return {**API, "X-GitHub-Token": token} if token else API


# --- who sees what -------------------------------------------------------------------------------

def test_each_person_sees_only_their_repositories(db, people):
    add_decision(db, "alice/app", "A")
    add_decision(db, "bob/lib", "B")
    add_decision(db, "carol/secret", "C")

    mine = client.get("/api/decisions", headers=as_user("alice")).json()
    assert sorted((d["repo"], d["can_edit"]) for d in mine) == [("alice/app", True), ("bob/lib", False)]
    assert client.get("/api/summary", headers=as_user("alice")).json()["decisions"]["proposed"] == 2

    demo = client.get("/api/decisions", headers=as_user(None)).json()
    assert demo == []  # nothing stored for demo/repo, and nobody else's data leaks into the demo


def test_changing_a_decision_needs_write_access(db, people):
    own = add_decision(db, "alice/app", "A")
    read_only = add_decision(db, "bob/lib", "B")
    other = add_decision(db, "carol/secret", "C")
    demo = add_decision(db, "demo/repo", "D")

    def patch(decision_id, token):
        return client.patch(f"/api/decisions/{decision_id}", json={"status": "accepted"}, headers=as_user(token))

    assert patch(own, "alice").status_code == 200
    assert patch(read_only, "alice").status_code == 403
    assert patch(other, "alice").status_code == 404  # not even revealed to exist
    assert patch(demo, None).status_code == 403  # the demo is read-only


def test_expired_github_sign_in_is_reported(db, people):
    assert client.get("/api/summary", headers=as_user("expired")).status_code == 401


def test_me_describes_the_viewer(db, people):
    me = client.get("/api/me", headers=as_user("alice")).json()
    assert me["login"] == "alice" and not me["demo"]
    assert [r["name"] for r in me["repos"]] == ["alice/app", "bob/lib"]
    assert me["install_url"] == "https://github.com/apps/precedent-test/installations/new"
    visitor = client.get("/api/me", headers=as_user(None)).json()
    assert visitor["demo"] and visitor["login"] is None and visitor["repos"][0]["name"] == "demo/repo"


# --- webhook rules -------------------------------------------------------------------------------

@pytest.fixture
def jobs_run(monkeypatch):
    """Record jobs instead of running them (no GitHub or Gemini in tests)."""
    ran = []
    monkeypatch.setattr(main_module, "run_job", lambda *args: ran.append(args))
    return ran


def send(event: str, payload: dict) -> dict:
    body = json.dumps({"sender": {"type": "User"}, **payload}).encode()
    signature = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    response = client.post("/webhooks/github", content=body, headers={
        "X-GitHub-Event": event, "X-GitHub-Delivery": str(uuid.uuid4()), "X-Hub-Signature-256": signature,
    })
    assert response.status_code == 200
    return response.json()


def pr_opened(repo: str, private: bool = False, number: int = 1) -> dict:
    return {"action": "opened", "repository": {"full_name": repo, "private": private},
            "pull_request": {"number": number, "draft": False}}


def test_private_repositories_are_skipped_and_not_stored(db, jobs_run):
    assert send("pull_request", pr_opened("alice/private", private=True))["status"] == "skipped"
    assert jobs_run == []
    with psycopg.connect(db) as conn:
        payload, note = conn.execute("SELECT payload, error FROM webhook_events").fetchone()
    assert payload == {} and "Private" in note


def test_daily_limits(db, jobs_run, monkeypatch):
    monkeypatch.setattr(config, "REPO_DAILY_JOB_LIMIT", 2)
    monkeypatch.setattr(config, "OWNER_DAILY_JOB_LIMIT", 3)
    statuses = [send("pull_request", pr_opened("alice/app"))["status"] for _ in range(3)]
    assert statuses == ["queued", "queued", "limited"]  # per repository
    assert send("pull_request", pr_opened("alice/other"))["status"] == "queued"
    assert send("pull_request", pr_opened("alice/third"))["status"] == "limited"  # per owner
    assert send("pull_request", pr_opened("bob/lib"))["status"] == "queued"  # others unaffected
    assert len(jobs_run) == 4


def test_removing_a_repository_deletes_its_data(db, jobs_run):
    add_decision(db, "alice/app", "A")
    add_decision(db, "alice/keep", "K")
    send("installation_repositories", {"action": "removed", "repositories_removed": [{"full_name": "alice/app"}]})
    with psycopg.connect(db) as conn:
        assert [r[0] for r in conn.execute("SELECT repo FROM decisions")] == ["alice/keep"]


def test_uninstalling_deletes_the_whole_account(db, jobs_run):
    add_decision(db, "alice/app", "A")
    add_decision(db, "alice/other", "B")
    add_decision(db, "bob/lib", "C")
    send("installation", {"action": "deleted", "installation": {"account": {"login": "alice"}}})
    with psycopg.connect(db) as conn:
        assert [r[0] for r in conn.execute("SELECT repo FROM decisions")] == ["bob/lib"]
