"""Measure how well Precedent's two LLM steps work, on hand-labelled cases.

  extraction.yaml  review discussions, each labelled with the decisions it really contains
  conflicts.yaml   one repository's decisions, plus pull requests labelled with the decisions they break

Both suites run the same code as production (transcript building, prompts, citation checks, the
nearest-decision search), but on these files instead of GitHub and the database. They do call Gemini,
so they need GEMINI_API_KEY and use free-tier quota: about 80 requests for a full run.
The model's answers vary a little even at temperature 0, so compare changes over several runs (--repeat).

Usage (from the backend folder):
    python -m evals.run                     # both suites
    python -m evals.run extraction          # one suite
    python -m evals.run --only chk-04 -v    # one case, with details
    python -m evals.run --repeat 3          # run 3 times and report the mean and range
    python -m evals.run --save              # also write evals/RESULTS.md
"""
import argparse
import math
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from app import config
from app.check import TOP_K, closest_overall, decisions_as_text, describe_change
from app.extract import build_transcript, clean_decisions

HERE = Path(__file__).resolve().parent

# Two statements mean the same decision when their embeddings are at least this similar (cosine).
# Calibrated on these files: paraphrases of one rule scored 0.93 and up; the closest two different rules, 0.84.
MATCH_THRESHOLD = 0.88


def load(name: str):
    return yaml.safe_load((HERE / f"{name}.yaml").read_text(encoding="utf-8"))


# ---------- scoring helpers (no network) ----------

def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def match_statements(similarity: list[list[float]], threshold: float = MATCH_THRESHOLD) -> list[tuple[int, int]]:
    """Pair expected (rows) with predicted (columns) decisions, most similar first, each used once."""
    pairs = sorted(
        ((s, i, j) for i, row in enumerate(similarity) for j, s in enumerate(row) if s >= threshold),
        reverse=True,
    )
    used_i: set[int] = set()
    used_j: set[int] = set()
    matched = []
    for _, i, j in pairs:
        if i not in used_i and j not in used_j:
            used_i.add(i)
            used_j.add(j)
            matched.append((i, j))
    return matched


@dataclass
class Score:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)  # (case id, what went wrong)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0


def to_discussion(comments: list[dict]) -> dict:
    """Turn a case's comments into the shape GitHub's API returns, for build_transcript.

    A comment with `path` is an inline review comment (`reply_to` makes it a reply in that thread),
    one with `review: true` is a review summary, and any other is a comment in the PR conversation.
    """
    discussion: dict[str, list] = {"review_comments": [], "issue_comments": [], "reviews": []}
    paths: dict[int, tuple[str, str]] = {}
    for n, c in enumerate(comments):
        stamp = f"2026-01-01T00:{n // 60:02d}:{n % 60:02d}Z"
        base = {"id": c["id"], "user": {"login": c["user"]}, "body": c["body"]}
        if "path" in c or "reply_to" in c:
            root = c.get("reply_to")
            path, hunk = paths[root] if root else (c["path"], c.get("hunk", ""))
            paths[c["id"]] = (path, hunk)
            discussion["review_comments"].append(
                {**base, "in_reply_to_id": root, "path": path, "diff_hunk": hunk, "created_at": stamp}
            )
        elif c.get("review"):
            discussion["reviews"].append({**base, "submitted_at": stamp})
        else:
            discussion["issue_comments"].append({**base, "created_at": stamp})
    return discussion


def as_pr(case: dict) -> tuple[dict, list[dict]]:
    """A conflict case as the pull request and files GitHub's API would return."""
    files = [{"status": "added" if f["patch"].startswith("@@ -0,0 ") else "modified", **f} for f in case["files"]]
    return {"title": case["title"], "body": case.get("body", "")}, files


def nearest(query: list[float], pool: list[dict], vectors: list[list[float]], k: int = TOP_K) -> list[dict]:
    """The k decisions closest to one query, as pgvector's cosine distance (<=>) would rank them."""
    ranked = sorted(
        ({**d, "distance": 1 - cosine(query, v)} for d, v in zip(pool, vectors)), key=lambda d: d["distance"]
    )
    return ranked[:k]


# ---------- the two suites ----------

def run_extraction(cases: list[dict], verbose: bool) -> tuple[Score, dict]:
    from app.llm import embed_documents, extract_decisions

    score, citations_right, traps = Score(), 0, [0, 0]
    for case in cases:
        transcript, by_id = build_transcript(to_discussion(case["comments"]))
        predicted, _ = clean_decisions(extract_decisions(transcript), by_id)
        expected = case.get("expect") or []

        statements = [e["statement"] for e in expected] + [p.statement for p in predicted]
        vectors = embed_documents(statements) if expected and predicted else []
        exp_v, pred_v = vectors[: len(expected)], vectors[len(expected):]
        similarity = [[cosine(e, p) for p in pred_v] for e in exp_v]
        matched = match_statements(similarity)

        right = sum(predicted[j].source_comment_id in expected[i]["sources"] for i, j in matched)
        citations_right += right
        tp, fp, fn = len(matched), len(predicted) - len(matched), len(expected) - len(matched)
        score.tp, score.fp, score.fn = score.tp + tp, score.fp + fp, score.fn + fn
        if not expected:
            traps[0] += 1
            traps[1] += fp == 0

        lines = []
        matched_i = {i for i, _ in matched}
        matched_j = {j for _, j in matched}
        for i, e in enumerate(expected):
            if i not in matched_i:
                best = max(similarity[i], default=0)
                lines.append(f"    missed: {e['statement']}" + (f"  (closest {best:.2f})" if similarity else ""))
        for j, p in enumerate(predicted):
            if j not in matched_j:
                lines.append(f"    extra:  {p.statement}  (confidence {p.confidence:.2f})")
        for i, j in matched:
            if predicted[j].source_comment_id not in expected[i]["sources"]:
                lines.append(f"    wrong citation: comment {predicted[j].source_comment_id} for: {expected[i]['statement']}")
        ok = not lines
        if not ok:
            score.failures.append((case["id"], f"{case['id']} ({case['note']})\n" + "\n".join(lines)))
        print(f"  {'pass' if ok else 'FAIL'}  {case['id']}  {case['note']}", flush=True)
        if verbose:
            for i, j in matched:
                print(f"        {expected[i]['statement']}\n      = {predicted[j].statement}  (similarity {similarity[i][j]:.2f})")
            print("\n".join(lines))

    extra = {
        "citation accuracy": citations_right / score.tp if score.tp else 1.0,
        "discussions without a decision left empty": traps[1] / traps[0] if traps[0] else 1.0,
    }
    return score, extra


def run_conflicts(data: dict, verbose: bool) -> tuple[Score, dict]:
    from app.llm import embed_documents, embed_queries, find_conflicts

    # Decisions are referred to by name in the YAML file and by number in the prompt, as in production.
    pool = [{"id": n, "key": d["key"], "statement": d["statement"], "rationale": d.get("rationale", ""),
             "scope": d.get("scope", "")} for n, d in enumerate(data["decisions"], start=1)]
    by_key = {d["key"]: d for d in pool}
    pool_vectors = embed_documents([d["statement"] for d in pool])

    score, retrieved, wanted, alarms = Score(), 0, 0, [0, 0]
    for case in data["cases"]:
        change, queries = describe_change(*as_pr(case))
        candidates = closest_overall([nearest(q, pool, pool_vectors) for q in embed_queries(queries)])
        candidate_ids = {d["id"] for d in candidates}

        conflicts = find_conflicts(change, decisions_as_text(candidates))
        predicted = {c.decision_id for c in conflicts if c.decision_id in candidate_ids}
        expected = {by_key[k]["id"] for k in case.get("expect") or []}
        names = {d["id"]: d["key"] for d in pool}

        tp, fp, fn = len(predicted & expected), len(predicted - expected), len(expected - predicted)
        score.tp, score.fp, score.fn = score.tp + tp, score.fp + fp, score.fn + fn
        found = expected & candidate_ids
        retrieved += len(found)
        wanted += len(expected)
        if not expected:
            alarms[0] += 1
            alarms[1] += bool(predicted)

        lines = [f"    missed: {names[i]}" + ("" if i in candidate_ids else " (not retrieved)")
                 for i in sorted(expected - predicted)]
        lines += [f"    false alarm: {names[i]}: "
                  + next(c.explanation for c in conflicts if c.decision_id == i) for i in sorted(predicted - expected)]
        ok = not lines
        if not ok:
            score.failures.append((case["id"], f"{case['id']} ({case['note']})\n" + "\n".join(lines)))
        print(f"  {'pass' if ok else 'FAIL'}  {case['id']}  {case['note']}", flush=True)
        if verbose:
            print("    candidates: " + ", ".join(f"{names[d['id']]} {d['distance']:.2f}" for d in candidates))
            for c in conflicts:
                print(f"    flagged {names.get(c.decision_id, c.decision_id)}: {c.explanation}")
            print("\n".join(lines))

    extra = {
        "retrieval recall": retrieved / wanted if wanted else 1.0,
        "clean PRs left alone": 1 - alarms[1] / alarms[0] if alarms[0] else 1.0,
    }
    return score, extra


# ---------- report ----------

def spread(values: list[float]) -> str:
    """The mean, plus the range when runs disagree: 0.91 (0.86-0.95)."""
    mean = sum(values) / len(values)
    low, high = min(values), max(values)
    return f"{mean:.2f}" if high - low < 0.005 else f"{mean:.2f} ({low:.2f}-{high:.2f})"


def report(results: dict[str, list[tuple[Score, dict]]], cases: dict[str, int], seconds: float) -> str:
    runs = len(next(iter(results.values())))
    lines = [
        f"Model `{config.GEMINI_MODEL}`, embeddings `{config.EMBEDDING_MODEL}`: "
        f"{runs} run{'s' if runs > 1 else ''} on {date.today().isoformat()}, {seconds:.0f}s."
        + (" Each figure is the mean over the runs, with the range when they disagree." if runs > 1 else ""),
        "",
        "| Suite | Cases | Precision | Recall | Also measured |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, scored in results.items():
        other = "; ".join(f"{k}: {spread([extra[k] for _, extra in scored])}" for k in scored[0][1])
        lines.append(
            f"| {name} | {cases[name]} | {spread([s.precision for s, _ in scored])} "
            f"| {spread([s.recall for s, _ in scored])} | {other} |"
        )

    # Each failing case once: how often it failed, and what went wrong the last time.
    failed: dict[str, list[str]] = {}
    for scored in results.values():
        for score, _ in scored:
            for case_id, text in score.failures:
                failed.setdefault(case_id, []).append(text)
    if failed:
        lines += ["", "Failures:", "", "```"]
        for texts in failed.values():
            first, _, rest = texts[-1].partition("\n")
            if runs > 1:
                first += f"  [failed in {len(texts)} of {runs} runs]"
            lines += [first, rest]
        lines.append("```")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score Precedent's extraction and conflict checks.")
    parser.add_argument("suite", nargs="?", choices=["extraction", "conflicts"], help="run only this suite")
    parser.add_argument("--only", help="run only the case with this id")
    parser.add_argument("--repeat", type=int, default=1, help="run each suite this many times (the model varies)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show matches and model output per case")
    parser.add_argument("--save", action="store_true", help="write the report to evals/RESULTS.md")
    args = parser.parse_args()

    extraction = [c for c in load("extraction") if not args.only or c["id"] == args.only]
    conflicts = load("conflicts")
    conflicts["cases"] = [c for c in conflicts["cases"] if not args.only or c["id"] == args.only]
    suites = {
        "Extraction": (len(extraction), lambda: run_extraction(extraction, args.verbose)),
        "Conflict check": (len(conflicts["cases"]), lambda: run_conflicts(conflicts, args.verbose)),
    }
    chosen = {"extraction": ["Extraction"], "conflicts": ["Conflict check"], None: list(suites)}[args.suite]

    start = time.monotonic()
    results: dict[str, list[tuple[Score, dict]]] = {}
    for n in range(args.repeat):
        for name in chosen:
            count, run_suite = suites[name]
            if count:
                print(f"{name}: {count} cases" + (f", run {n + 1} of {args.repeat}" if args.repeat > 1 else ""))
                results.setdefault(name, []).append(run_suite())
    if not results:
        raise SystemExit("No cases matched.")

    text = report(results, {name: suites[name][0] for name in results}, time.monotonic() - start)
    print("\n" + text)
    if args.save:
        header = "# Evaluation results\n\nWritten by `python -m evals.run --save`. See [the README](../../README.md#evaluation).\n\n"
        (HERE / "RESULTS.md").write_text(header + text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
