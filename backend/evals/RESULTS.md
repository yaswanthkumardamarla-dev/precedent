# Evaluation results

Written by `python -m evals.run --repeat 3`. See [the README](../../README.md#evaluation). The third run stopped when Gemini's daily free-tier quota ran out, so these figures are from the 2 runs that finished.

Model `gemini-3.5-flash-lite`, embeddings `gemini-embedding-001`: 2 runs on 2026-11-27, 692s. Each figure is the mean over the runs, with the range when they disagree.

| Suite | Cases | Precision | Recall | Also measured |
| --- | --- | --- | --- | --- |
| Extraction | 22 | 1.00 | 1.00 | citation accuracy: 1.00; discussions without a decision left empty: 1.00 |
| Conflict check | 24 | 0.97 (0.95-1.00) | 1.00 | retrieval recall: 1.00; clean PRs left alone: 1.00 |

Failures:

```
chk-22 (blocking database call in an async endpoint)  [failed in 1 of 2 runs]
    false alarm: sql-params: The code executes a raw SQL string instead of using parameterized queries.
```
