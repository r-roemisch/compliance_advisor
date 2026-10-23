# Evaluation log

Each run of `compliance-advisor-eval` appends one line to `evaluation/results.jsonl`; this page is
regenerated from it. The Golden Set is `config/golden_set.yaml`.

**Metrics.** *hit@6*: share of questions where at least one expected Provision is among the six
Passages. *recall@6*: share of the expected Provisions found, averaged. *MRR*: mean of 1/rank of
the first expected Provision (1.0 = always first). For answers: *citations valid*: no citation
points to a Passage that does not exist; *cites expected*: the answer cites an expected Provision.

## Retrieval

| Run | Label | Golden Set | Set-up | Questions | hit@6 | recall@6 | MRR |
|---|---|---|---|---|---|---|---|
| 2026-10-23T07:18 | baseline vs per provision (draft Golden Set) | draft | naive (seed) | 12 | 0.83 | 0.83 | 0.73 |
| 2026-10-23T07:18 | baseline vs per provision (draft Golden Set) | draft | provision (seed) | 12 | 1.00 | 0.96 | 0.74 |
| 2026-10-23T07:18 | baseline vs per provision (draft Golden Set) | draft | provision (all) | 24 | 0.88 | 0.81 | 0.70 |
| 2026-10-23T07:18 | baseline vs per provision (draft Golden Set) | draft | app (seed) | 12 | 0.92 | 0.89 | 0.72 |
| 2026-10-23T07:18 | baseline vs per provision (draft Golden Set) | draft | app (all) | 24 | 0.88 | 0.80 | 0.74 |
| 2026-10-23T07:19 | cap and lookup measured separately (draft Golden Set) | draft | lookup (seed) | 12 | 1.00 | 0.96 | 0.74 |
| 2026-10-23T07:19 | cap and lookup measured separately (draft Golden Set) | draft | lookup (all) | 24 | 0.92 | 0.85 | 0.74 |
| 2026-10-23T07:19 | cap and lookup measured separately (draft Golden Set) | draft | cap (seed) | 12 | 0.92 | 0.89 | 0.72 |
| 2026-10-23T07:19 | cap and lookup measured separately (draft Golden Set) | draft | cap (all) | 24 | 0.83 | 0.76 | 0.69 |
| 2026-10-23T07:20 | all set-ups incl. crowding case (draft Golden Set) | draft | naive (seed) | 13 | 0.77 | 0.77 | 0.67 |
| 2026-10-23T07:20 | all set-ups incl. crowding case (draft Golden Set) | draft | provision (seed) | 13 | 1.00 | 0.96 | 0.69 |
| 2026-10-23T07:20 | all set-ups incl. crowding case (draft Golden Set) | draft | provision (all) | 25 | 0.88 | 0.82 | 0.68 |
| 2026-10-23T07:20 | all set-ups incl. crowding case (draft Golden Set) | draft | lookup (seed) | 13 | 1.00 | 0.96 | 0.69 |
| 2026-10-23T07:20 | all set-ups incl. crowding case (draft Golden Set) | draft | lookup (all) | 25 | 0.92 | 0.86 | 0.72 |
| 2026-10-23T07:20 | all set-ups incl. crowding case (draft Golden Set) | draft | cap (seed) | 13 | 0.92 | 0.90 | 0.69 |
| 2026-10-23T07:20 | all set-ups incl. crowding case (draft Golden Set) | draft | cap (all) | 25 | 0.84 | 0.77 | 0.68 |
| 2026-10-23T07:20 | all set-ups incl. crowding case (draft Golden Set) | draft | app (seed) | 13 | 0.92 | 0.90 | 0.69 |
| 2026-10-23T07:20 | all set-ups incl. crowding case (draft Golden Set) | draft | app (all) | 25 | 0.88 | 0.81 | 0.72 |
| 2026-10-23T07:22 | app with cap 4 (draft Golden Set) | draft | app (seed) | 13 | 0.92 | 0.92 | 0.68 |
| 2026-10-23T07:22 | app with cap 4 (draft Golden Set) | draft | app (all) | 25 | 0.88 | 0.84 | 0.71 |
| 2026-10-23T07:22 | app with cap 5 (draft Golden Set) | draft | app (seed) | 13 | 1.00 | 0.96 | 0.69 |
| 2026-10-23T07:22 | app with cap 5 (draft Golden Set) | draft | app (all) | 25 | 0.92 | 0.86 | 0.72 |
| 2026-10-23T07:23 | answers: naive baseline vs app (draft Golden Set) | draft | naive (seed) | 13 | 0.77 | 0.77 | 0.67 |
| 2026-10-23T07:23 | answers: naive baseline vs app (draft Golden Set) | draft | app (seed) | 13 | 0.92 | 0.90 | 0.69 |
| 2026-10-23T07:23 | answers: naive baseline vs app (draft Golden Set) | draft | app (all) | 25 | 0.88 | 0.81 | 0.72 |
| 2026-10-23T08:02 | app with cap off (draft Golden Set) | draft | app (seed) | 13 | 1.00 | 0.96 | 0.69 |
| 2026-10-23T08:02 | app with cap off (draft Golden Set) | draft | app (all) | 25 | 0.92 | 0.86 | 0.72 |

## Answers

| Run | Label | Set-up | Questions | with citations | citations valid | cites expected | avg s | cost $ |
|---|---|---|---|---|---|---|---|---|
| 2026-10-23T07:23 | answers: naive baseline vs app (draft Golden Set) | naive | 13 | 1.00 | 1.00 | 0.77 | 15.4 | 0.0097 |
| 2026-10-23T07:23 | answers: naive baseline vs app (draft Golden Set) | app | 25 | 1.00 | 1.00 | 0.88 | 13.6 | 0.0238 |

_Regulatory information, not legal advice._
