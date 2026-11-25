"""Extract engineering decisions from one pull request's review discussion.

Usage (from the backend folder):
    python -m app.extract OWNER/REPO PR_NUMBER
    python -m app.extract OWNER/REPO PR_NUMBER --show    # also print what is sent to the model
"""
import argparse
import threading
import time
from contextlib import contextmanager

import psycopg

from app import config
from app.github_client import fetch_pr_discussion, installation_token
from app.llm import embed_documents, extract_decisions


@contextmanager
def progress(label: str):
    """Print a running timer while a slow step works, then how long it took."""
    start = time.monotonic()
    done = threading.Event()

    def tick():
        while not done.wait(5):
            print(f"    ...still {label} ({time.monotonic() - start:.0f}s)", flush=True)

    print(f"[{label}]", flush=True)
    thread = threading.Thread(target=tick, daemon=True)
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join()
        print(f"    done in {time.monotonic() - start:.1f}s", flush=True)


def build_transcript(discussion: dict) -> tuple[str, dict[int, dict]]:
    """Turn a PR's comments into tagged text the model can cite, plus a lookup by comment id."""
    by_id: dict[int, dict] = {}
    sections: list[str] = []

    # 1. Inline review threads: a first comment on a line of code, plus its replies.
    threads: dict[int, list[dict]] = {}
    for comment in sorted(discussion["review_comments"], key=lambda c: c["created_at"]):
        root_id = comment.get("in_reply_to_id") or comment["id"]
        threads.setdefault(root_id, []).append(comment)

    for comments in threads.values():
        first = comments[0]
        lines = [
            f"## Review thread on {first['path']}",
            "Code under discussion:",
            first.get("diff_hunk", ""),
            "",
        ]
        for comment in comments:
            by_id[comment["id"]] = comment
            lines.append(f"[comment {comment['id']}] {comment['user']['login']}: {comment['body']}")
        sections.append("\n".join(lines))

    # 2. General conversation: PR comments and review summaries, in time order.
    conversation = list(discussion["issue_comments"]) + [
        review for review in discussion["reviews"] if review.get("body")
    ]
    conversation.sort(key=lambda c: c.get("created_at") or c.get("submitted_at") or "")

    if conversation:
        lines = ["## General PR conversation"]
        for comment in conversation:
            by_id[comment["id"]] = comment
            lines.append(f"[comment {comment['id']}] {comment['user']['login']}: {comment['body']}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections), by_id


def to_vector(values: list[float]) -> str:
    """pgvector accepts vectors written as text like '[0.1,0.2,...]'."""
    return "[" + ",".join(str(v) for v in values) + "]"


def save_decisions(repo: str, number: int, decisions, embeddings, by_id) -> None:
    with psycopg.connect(config.DATABASE_URL) as conn:
        # NEW: several webhook jobs for the same PR can run at once; make them take turns.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{repo}#{number}",))
        # Re-running on the same PR replaces its unreviewed decisions instead of duplicating them.
        conn.execute(
            "DELETE FROM decisions WHERE repo = %s AND pr_number = %s AND status = 'proposed'",
            (repo, number),
        )
        for decision, embedding in zip(decisions, embeddings):
            source = by_id[decision.source_comment_id]
            conn.execute(
                """
                INSERT INTO decisions (repo, pr_number, statement, rationale, scope,
                                       source_comment_id, source_url, author, confidence, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                """,
                (
                    repo,
                    number,
                    decision.statement,
                    decision.rationale,
                    decision.scope,
                    decision.source_comment_id,
                    source["html_url"],
                    source["user"]["login"],
                    decision.confidence,
                    to_vector(embedding),
                ),
            )


def extract_pr(repo: str, number: int, show: bool = False) -> int:
    total_start = time.monotonic()
    print(f"Precedent: extracting decisions from {repo}#{number}  (model: {config.GEMINI_MODEL})\n")

    with progress("fetching comments from GitHub"):
        token = installation_token(repo)
        discussion = fetch_pr_discussion(repo, number, token)
        transcript, by_id = build_transcript(discussion)
    print(f"    found {len(by_id)} comments")

    if not by_id:
        print("This PR has no comments.")
        return 0

    if show:
        print("\n----- sent to the model -----")
        print(transcript)
        print("----- end -----\n")

    with progress("asking Gemini for decisions"):
        decisions = extract_decisions(transcript)
    print(f"    model returned {len(decisions)} decision(s)")

    # Guard against made-up citations: keep only decisions that point to a real comment.
    valid = [d for d in decisions if d.source_comment_id in by_id]
    dropped = len(decisions) - len(valid)
     # The same rule stated twice (e.g. a repeated comment) should be stored once.
    seen: set[str] = set()
    unique = []
    for d in valid:
        key = d.statement.strip().lower().rstrip(".")
        if key not in seen:
            seen.add(key)
            unique.append(d)
    valid = unique

    embeddings = []
    if valid:
        with progress("creating embeddings"):
            embeddings = embed_documents([d.statement for d in valid])

    with progress("saving to the database"):
        save_decisions(repo, number, valid, embeddings, by_id)

    print(f"\nSaved {len(valid)} decision(s):")
    for d in valid:
        print(f"  - {d.statement}  (confidence {d.confidence:.2f})")
        print(f"    source: {by_id[d.source_comment_id]['html_url']}")
    if dropped:
        print(f"Dropped {dropped} decision(s) that cited a comment not in this PR.")
    print(f"\nTotal time: {time.monotonic() - total_start:.1f}s")
    return len(valid)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract decisions from a pull request.")
    parser.add_argument("repo", help="OWNER/REPO, e.g. yaswanthkumardamarla-dev/precedent-sandbox")
    parser.add_argument("number", type=int, help="pull request number")
    parser.add_argument("--show", action="store_true", help="print the text sent to the model")
    args = parser.parse_args()
    extract_pr(args.repo, args.number, show=args.show)