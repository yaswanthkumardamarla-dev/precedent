"""The evaluation sets are well-formed and the scoring is right (no Gemini calls)."""
from app.check import MAX_CANDIDATES, describe_change
from app.extract import build_transcript
from evals import run


def test_extraction_cases_are_well_formed():
    cases = run.load("extraction")
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        ids = [c["id"] for c in case["comments"]]
        assert len(set(ids)) == len(ids), case["id"]
        transcript, by_id = build_transcript(run.to_discussion(case["comments"]))
        assert set(by_id) == set(ids), case["id"]  # every comment reaches the model, tagged with its id
        for expected in case["expect"]:
            assert expected["sources"] and set(expected["sources"]) <= set(ids), case["id"]
    assert sum(not c["expect"] for c in cases) >= len(cases) // 3  # plenty of cases with nothing to find


def test_conflict_cases_are_well_formed():
    data = run.load("conflicts")
    keys = [d["key"] for d in data["decisions"]]
    assert len(set(keys)) == len(keys) and len(keys) > MAX_CANDIDATES  # so the search has to choose
    cases = data["cases"]
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        assert set(case["expect"]) <= set(keys), case["id"]
        change, queries = describe_change(*run.as_pr(case))
        assert len(queries) == len(case["files"]), case["id"]
    assert sum(not c["expect"] for c in cases) >= len(cases) // 3


def test_replies_join_their_thread():
    discussion = run.to_discussion([
        {"id": 1, "user": "a", "path": "x.py", "hunk": "@@ +1 @@", "body": "rule"},
        {"id": 2, "user": "b", "reply_to": 1, "body": "agreed"},
        {"id": 3, "user": "c", "review": True, "body": "summary"},
        {"id": 4, "user": "d", "body": "chat"},
    ])
    assert [c["id"] for c in discussion["review_comments"]] == [1, 2]
    assert discussion["review_comments"][1]["path"] == "x.py"
    assert [r["id"] for r in discussion["reviews"]] == [3]
    assert [c["id"] for c in discussion["issue_comments"]] == [4]


def test_statements_are_matched_once_most_similar_first():
    similarity = [
        [0.95, 0.90],  # expected 0 is closest to predicted 0
        [0.93, 0.70],  # expected 1 also likes predicted 0, but it's taken; 0.70 is below the threshold
    ]
    assert run.match_statements(similarity, threshold=0.88) == [(0, 0)]


def test_scores():
    score = run.Score(tp=8, fp=2, fn=8)
    assert score.precision == 0.8 and score.recall == 0.5
    assert run.Score().precision == 1.0  # nothing predicted, nothing expected


def test_nearest_ranks_by_cosine_distance():
    pool = [{"id": 1}, {"id": 2}, {"id": 3}]
    vectors = [[1, 0], [0, 1], [1, 1]]
    ranked = run.nearest([1, 0.1], pool, vectors, k=2)
    assert [d["id"] for d in ranked] == [1, 3]
    assert abs(ranked[0]["distance"] - (1 - run.cosine([1, 0.1], [1, 0]))) < 1e-9
