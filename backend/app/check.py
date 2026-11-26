"""Check a pull request against the team's past decisions.

Usage (from the backend folder):
    python -m app.check OWNER/REPO PR_NUMBER           # report conflicts in the terminal
    python -m app.check OWNER/REPO PR_NUMBER --post    # also comment on the pull request
    python -m app.check OWNER/REPO PR_NUMBER --show    # also print what is sent to the model
"""
import argparse
import time

import psycopg

from app import config
from app.extract import progress, to_vector
from app.github_client import fetch_pr, fetch_pr_files, installation_token, upsert_pr_comment
from app.llm import embed_queries, find_conflicts

MARKER = "<!-- precedent:conflict-check -->"  # hidden tag so we can find and edit our own comment
MAX_FILES = 20            # files looked at per PR
MAX_PATCH_CHARS = 4000    # diff text per file, so one huge file can't crowd out the rest
MAX_CANDIDATES = 10       # decisions shown to the model
# Closest decisions fetched per changed file. As many as the model is shown, so a one-file PR gets a full
# set too (with 5, the eval set showed rules ranked 6th-10th being missed).
TOP_K = MAX_CANDIDATES


def describe_change(pr: dict, files: list[dict]) -> tuple[str, list[str]]:
    """The PR as text for the model, plus one search query per changed file."""
    parts = [f"Title: {pr['title']}", f"Description: {pr.get('body') or '(none)'}", ""]
    queries: list[str] = []
    for f in files[:MAX_FILES]:
        patch = (f.get("patch") or "(no text diff)")[:MAX_PATCH_CHARS]
        parts.append(f"### {f['filename']} ({f['status']})\n{patch}\n")
        added = "\n".join(
            line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")
        )
        queries.append(f"{pr['title']}\nFile: {f['filename']}\n{added}"[:2000])
    return "\n".join(parts), queries


def closest_overall(per_query: list[list[dict]]) -> list[dict]:
    """Merge each changed file's nearest decisions: each decision once, at its smallest distance, closest first."""
    best: dict[int, dict] = {}
    for rows in per_query:
        for d in rows:
            if d["id"] not in best or d["distance"] < best[d["id"]]["distance"]:
                best[d["id"]] = d
    return sorted(best.values(), key=lambda d: d["distance"])[:MAX_CANDIDATES]


def find_candidates(repo: str, number: int, vectors: list[list[float]]) -> list[dict]:
    """For each changed file, find the closest past decisions; keep the closest overall."""
    per_query: list[list[dict]] = []
    with psycopg.connect(config.DATABASE_URL) as conn:
        for vector in vectors:
            v = to_vector(vector)
            rows = conn.execute(
                """
                SELECT id, statement, rationale, scope, source_url,
                       embedding <=> %s::vector AS distance
                FROM decisions
                WHERE repo = %s
                  AND pr_number <> %s          -- a PR can't conflict with its own decisions
                  AND status <> 'retired'      -- retired decisions are no longer enforced
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (v, repo, number, v, TOP_K),
            ).fetchall()
            per_query.append([
                {"id": id_, "statement": statement, "rationale": rationale,
                 "scope": scope, "source_url": url, "distance": distance}
                for id_, statement, rationale, scope, url, distance in rows
            ])
    return closest_overall(per_query)


def decisions_as_text(candidates: list[dict]) -> str:
    lines = []
    for d in candidates:
        lines.append(f"[decision {d['id']}] {d['statement']}")
        if d["rationale"]:
            lines.append(f"    why: {d['rationale']}")
        if d["scope"]:
            lines.append(f"    applies to: {d['scope']}")
    return "\n".join(lines)


def save_conflicts(repo: str, number: int, conflicts) -> None:
    with psycopg.connect(config.DATABASE_URL) as conn:
        # Each run replaces the previous result for this PR.
        conn.execute("DELETE FROM conflicts WHERE repo = %s AND pr_number = %s", (repo, number))
        for c in conflicts:
            conn.execute(
                """
                INSERT INTO conflicts (repo, pr_number, decision_id, explanation, evidence, confidence)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (repo, number, c.decision_id, c.explanation, c.evidence, c.confidence),
            )


def one_line_code(text: str) -> str:
    """Show evidence as inline code on one line, so multi-line snippets can't break the bullet list."""
    flat = " ⏎ ".join(line.strip() for line in text.strip().splitlines() if line.strip())
    return f"`{flat.replace('`', 'ʼ')}`" if flat else "(not given)"


def comment_body(conflicts, by_id: dict[int, dict]) -> str:
    if not conflicts:
        return f"{MARKER}\n### ✅ Precedent: no conflicts with past decisions\n"
    lines = [
        MARKER,
        "### ⚠️ Precedent: this PR may go against past decisions",
        "",
    ]
    for c in conflicts:
        d = by_id[c.decision_id]
        lines += [
            f"**{d['statement']}**",
            "",
            c.explanation,
            "",
            f"- Where: {one_line_code(c.evidence)}",
            f"- Decided in: {d['source_url']}",
            "",
        ]
    lines.append("_Automated check by Precedent. If a decision is outdated, it can be retired so it stops being flagged._")
    return "\n".join(lines)


def check_pr(repo: str, number: int, post: bool = False, show: bool = False) -> int:
    total_start = time.monotonic()
    print(f"Precedent: checking {repo}#{number} against past decisions  (model: {config.GEMINI_MODEL})\n")

    with progress("fetching the PR from GitHub"):
        token = installation_token(repo)
        pr = fetch_pr(repo, number, token)
        files = fetch_pr_files(repo, number, token)
        change, queries = describe_change(pr, files)
    print(f"    {len(files)} changed file(s)")

    if not queries:
        print("This PR changes no files.")
        return 0

    with progress("searching past decisions"):
        vectors = embed_queries(queries)
        candidates = find_candidates(repo, number, vectors)
    print(f"    {len(candidates)} related decision(s):")
    for d in candidates:
        print(f"      [{d['id']}] {d['statement']}  (distance {d['distance']:.3f})")

    valid = []
    by_id = {d["id"]: d for d in candidates}
    if candidates:
        decisions_text = decisions_as_text(candidates)
        if show:
            print("\n----- sent to the model -----")
            print("Past decisions:\n" + decisions_text + "\n\nPull request:\n" + change)
            print("----- end -----\n")

        with progress("asking Gemini about conflicts"):
            conflicts = find_conflicts(change, decisions_text)

        # Guard against made-up citations: keep only conflicts with decisions we actually sent.
        valid = [c for c in conflicts if c.decision_id in by_id]
        if len(valid) < len(conflicts):
            print(f"    dropped {len(conflicts) - len(valid)} conflict(s) citing unknown decisions")

    with progress("saving results"):
        save_conflicts(repo, number, valid)

    if valid:
        print(f"\nFound {len(valid)} conflict(s):")
        for c in valid:
            print(f"  - {by_id[c.decision_id]['statement']}  (confidence {c.confidence:.2f})")
            print(f"    {c.explanation}")
            print(f"    where: {c.evidence}")
    else:
        print("\nNo conflicts found.")

    if post:
        with progress("commenting on the PR"):
            # Only create a new comment when there are conflicts; an existing one is always updated.
            url = upsert_pr_comment(repo, number, token, comment_body(valid, by_id), MARKER, create=bool(valid))
        print(f"    {url or 'nothing to post'}")

    print(f"\nTotal time: {time.monotonic() - total_start:.1f}s")
    return len(valid)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check a PR against past decisions.")
    parser.add_argument("repo", help="OWNER/REPO")
    parser.add_argument("number", type=int, help="pull request number")
    parser.add_argument("--post", action="store_true", help="comment on the pull request")
    parser.add_argument("--show", action="store_true", help="print the text sent to the model")
    args = parser.parse_args()
    check_pr(args.repo, args.number, post=args.post, show=args.show)