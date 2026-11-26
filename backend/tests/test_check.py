"""The search for related decisions, against a real pgvector database (no Gemini calls)."""
import psycopg

from app.check import find_candidates
from app.extract import to_vector


def axis(i: int) -> list[float]:
    """A 768-dimension unit vector pointing along axis i."""
    v = [0.0] * 768
    v[i] = 1.0
    return v


def add_decision(conn, repo: str, pr: int, statement: str, i: int, status: str = "proposed") -> None:
    conn.execute(
        """
        INSERT INTO decisions (repo, pr_number, statement, source_comment_id, source_url, status, embedding)
        VALUES (%s, %s, %s, 1, 'https://example.test', %s, %s::vector)
        """,
        (repo, pr, statement, status, to_vector(axis(i))),
    )


def test_each_query_finds_its_nearest_decisions_in_one_search(db):
    with psycopg.connect(db) as conn:
        add_decision(conn, "o/r", 1, "near the first query", 0)
        add_decision(conn, "o/r", 1, "near the second query", 1)
        add_decision(conn, "o/r", 1, "near neither", 2)
        add_decision(conn, "o/r", 1, "retired", 0, status="retired")
        add_decision(conn, "o/r", 9, "made in the PR being checked", 0)
        add_decision(conn, "o/other", 1, "another repository", 0)

    found = find_candidates("o/r", 9, [axis(0), axis(1)])

    assert [d["statement"] for d in found][:2] in (
        ["near the first query", "near the second query"], ["near the second query", "near the first query"]
    )
    assert all(abs(d["distance"]) < 1e-6 for d in found[:2])  # each at its own query's distance
    assert {d["statement"] for d in found} == {"near the first query", "near the second query", "near neither"}
