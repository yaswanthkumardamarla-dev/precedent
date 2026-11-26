# Evaluation results

Written by `python -m evals.run --save`. See [the README](../../README.md#evaluation).

Model `gemini-3.5-flash-lite`, embeddings `gemini-embedding-001`: 3 runs on 2026-11-26, 33981s. Each figure is the mean over the runs, with the range when they disagree.

| Suite | Cases | Precision | Recall | Also measured |
| --- | --- | --- | --- | --- |
| Extraction | 22 | 1.00 | 1.00 | citation accuracy: 1.00; discussions without a decision left empty: 1.00 |
| Conflict check | 24 | 0.94 | 0.92 (0.89-0.94) | retrieval recall: 0.94; clean PRs left alone: 0.87 (0.86-0.88) |

Failures:

```
chk-01 (print and a missing type hint in a new endpoint)  [failed in 3 of 3 runs]
    missed: logging (not retrieved)
chk-02 (new endpoint that follows the rules)  [failed in 3 of 3 runs]
    false alarm: type-hints: The endpoint function get_order is missing a return type hint for its parameters or return value according to the type hints standard.
chk-15 (edits a released migration)  [failed in 1 of 3 runs]
    missed: migrations
```

Not scored, because Gemini was unavailable: ext-17, chk-08, chk-09.
