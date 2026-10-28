# Evaluation log

Each run of `compliance-advisor-eval` appends one line to `evaluation/results.jsonl`; this page is
regenerated from it. The Golden Set is `config/golden_set.yaml`.

**Metrics.** *hit@6*: share of questions where at least one expected Provision is among the six
Passages. *recall@6*: share of the expected Provisions found, averaged. *MRR*: mean of 1/rank of
the first expected Provision (1.0 = always first). For answers: *citations valid*: no citation
points to a Passage that does not exist; *cites expected*: the answer cites an expected Provision.

**Subsets.** *seed*: questions the naive baseline index can answer; *all*: the whole Golden Set;
*tune* and *test*: a fixed split into halves. A variant is chosen on *tune* and reported on *test*,
so it is not picked for fitting these very questions.

**Hybrid search (2026-10-28).** Keyword search merged with vector search lost to vector search on
both halves. It pulls in Passages that share words with the question but not its meaning: German
texts for German questions about English EU acts, and recitals that repeat an act's name. Half
weight for the keyword ranks was the best variant on *tune* (0.82 against 0.88 for vector) and
stayed behind on *test* (0.81 against 0.83). Vector search stays the default; hybrid search can be
chosen per question, with half weight.

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
| 2026-10-28T13:01 | breakdown by question type (Golden Set v3) | draft | naive (seed) | 100 | 0.82 | 0.73 | 0.64 |
| 2026-10-28T13:01 | breakdown by question type (Golden Set v3) | draft | provision (seed) | 100 | 0.87 | 0.74 | 0.62 |
| 2026-10-28T13:01 | breakdown by question type (Golden Set v3) | draft | provision (all) | 214 | 0.85 | 0.69 | 0.66 |
| 2026-10-28T13:01 | breakdown by question type (Golden Set v3) | draft | app (seed) | 100 | 0.87 | 0.74 | 0.63 |
| 2026-10-28T13:01 | breakdown by question type (Golden Set v3) | draft | app (all) | 214 | 0.85 | 0.69 | 0.67 |
| 2026-10-28T13:27 | hybrid search vs vector (Golden Set v3) | draft | app (seed) | 100 | 0.87 | 0.74 | 0.63 |
| 2026-10-28T13:27 | hybrid search vs vector (Golden Set v3) | draft | app (all) | 214 | 0.85 | 0.69 | 0.67 |
| 2026-10-28T13:27 | hybrid search vs vector (Golden Set v3) | draft | hybrid (seed) | 100 | 0.78 | 0.66 | 0.56 |
| 2026-10-28T13:27 | hybrid search vs vector (Golden Set v3) | draft | hybrid (all) | 214 | 0.79 | 0.61 | 0.60 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | app (seed) | 100 | 0.87 | 0.74 | 0.63 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | app (all) | 214 | 0.85 | 0.69 | 0.67 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | app (tune) | 99 | 0.88 | 0.70 | 0.65 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | app (test) | 115 | 0.83 | 0.68 | 0.69 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid (seed) | 100 | 0.78 | 0.66 | 0.56 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid (all) | 214 | 0.79 | 0.61 | 0.60 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid (tune) | 99 | 0.79 | 0.60 | 0.56 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid (test) | 115 | 0.78 | 0.61 | 0.63 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid-rerank (seed) | 100 | 0.78 | 0.66 | 0.55 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid-rerank (all) | 214 | 0.77 | 0.61 | 0.60 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid-rerank (tune) | 99 | 0.78 | 0.60 | 0.58 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid-rerank (test) | 115 | 0.77 | 0.62 | 0.61 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid-weighted (seed) | 100 | 0.83 | 0.70 | 0.57 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid-weighted (all) | 214 | 0.81 | 0.64 | 0.61 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid-weighted (tune) | 99 | 0.82 | 0.64 | 0.57 |
| 2026-10-28T13:49 | hybrid variants, tuning and held-out half | draft | hybrid-weighted (test) | 115 | 0.81 | 0.63 | 0.64 |

## Retrieval by kind of question

hit@6 per question type, and for cross-lingual questions (asked in another language than an
expected Source) against same-language ones. Number of questions in brackets.

**2026-10-28T13:01, breakdown by question type (Golden Set v3)**

| Set-up | lookup | threshold | definition | applicability | scenario | cross_regime | crowding | temporal | cross-lingual | same language |
|---|---|---|---|---|---|---|---|---|---|---|
| naive (seed) | 0.88 (42) | 0.95 (19) | 1.00 (9) | 0.69 (13) | 0.70 (10) | 0.40 (5) | 0.00 (1) | 0.00 (1) | 0.64 (22) | 0.87 (78) |
| provision (seed) | 0.95 (42) | 0.74 (19) | 0.78 (9) | 0.77 (13) | 0.90 (10) | 1.00 (5) | 1.00 (1) | 1.00 (1) | 0.59 (22) | 0.95 (78) |
| provision (all) | 0.91 (81) | 0.82 (45) | 0.77 (13) | 0.83 (29) | 0.80 (25) | 0.86 (14) | 1.00 (2) | 0.60 (5) | 0.72 (78) | 0.93 (136) |
| app (seed) | 0.95 (42) | 0.74 (19) | 0.78 (9) | 0.77 (13) | 0.90 (10) | 1.00 (5) | 1.00 (1) | 1.00 (1) | 0.59 (22) | 0.95 (78) |
| app (all) | 0.93 (81) | 0.82 (45) | 0.77 (13) | 0.83 (29) | 0.80 (25) | 0.86 (14) | 1.00 (2) | 0.60 (5) | 0.73 (78) | 0.93 (136) |

**2026-10-28T13:27, hybrid search vs vector (Golden Set v3)**

| Set-up | lookup | threshold | definition | applicability | scenario | cross_regime | crowding | temporal | cross-lingual | same language |
|---|---|---|---|---|---|---|---|---|---|---|
| app (seed) | 0.95 (42) | 0.74 (19) | 0.78 (9) | 0.77 (13) | 0.90 (10) | 1.00 (5) | 1.00 (1) | 1.00 (1) | 0.59 (22) | 0.95 (78) |
| app (all) | 0.93 (81) | 0.82 (45) | 0.77 (13) | 0.83 (29) | 0.80 (25) | 0.86 (14) | 1.00 (2) | 0.60 (5) | 0.73 (78) | 0.93 (136) |
| hybrid (seed) | 0.83 (42) | 0.74 (19) | 0.78 (9) | 0.77 (13) | 0.70 (10) | 0.80 (5) | 1.00 (1) | 0.00 (1) | 0.41 (22) | 0.89 (78) |
| hybrid (all) | 0.85 (81) | 0.76 (45) | 0.69 (13) | 0.83 (29) | 0.68 (25) | 0.86 (14) | 0.50 (2) | 0.40 (5) | 0.61 (78) | 0.88 (136) |

**2026-10-28T13:49, hybrid variants, tuning and held-out half**

| Set-up | lookup | threshold | definition | applicability | scenario | cross_regime | crowding | temporal | cross-lingual | same language |
|---|---|---|---|---|---|---|---|---|---|---|
| app (seed) | 0.95 (42) | 0.74 (19) | 0.78 (9) | 0.77 (13) | 0.90 (10) | 1.00 (5) | 1.00 (1) | 1.00 (1) | 0.59 (22) | 0.95 (78) |
| app (all) | 0.93 (81) | 0.82 (45) | 0.77 (13) | 0.83 (29) | 0.80 (25) | 0.86 (14) | 1.00 (2) | 0.60 (5) | 0.73 (78) | 0.93 (136) |
| app (tune) | 0.93 (43) | 0.84 (19) | 0.80 (5) | 0.93 (15) | 0.67 (6) | 1.00 (7) | 1.00 (1) | 0.33 (3) | 0.81 (36) | 0.92 (63) |
| app (test) | 0.92 (38) | 0.81 (26) | 0.75 (8) | 0.71 (14) | 0.84 (19) | 0.71 (7) | 1.00 (1) | 1.00 (2) | 0.67 (42) | 0.93 (73) |
| hybrid (seed) | 0.83 (42) | 0.74 (19) | 0.78 (9) | 0.77 (13) | 0.70 (10) | 0.80 (5) | 1.00 (1) | 0.00 (1) | 0.41 (22) | 0.89 (78) |
| hybrid (all) | 0.85 (81) | 0.76 (45) | 0.69 (13) | 0.83 (29) | 0.68 (25) | 0.86 (14) | 0.50 (2) | 0.40 (5) | 0.61 (78) | 0.88 (136) |
| hybrid (tune) | 0.86 (43) | 0.58 (19) | 0.60 (5) | 0.93 (15) | 0.83 (6) | 0.86 (7) | 1.00 (1) | 0.33 (3) | 0.61 (36) | 0.89 (63) |
| hybrid (test) | 0.84 (38) | 0.89 (26) | 0.75 (8) | 0.71 (14) | 0.63 (19) | 0.86 (7) | 0.00 (1) | 0.50 (2) | 0.62 (42) | 0.88 (73) |
| hybrid-rerank (seed) | 0.86 (42) | 0.74 (19) | 0.78 (9) | 0.69 (13) | 0.70 (10) | 0.80 (5) | 1.00 (1) | 0.00 (1) | 0.36 (22) | 0.90 (78) |
| hybrid-rerank (all) | 0.88 (81) | 0.71 (45) | 0.69 (13) | 0.76 (29) | 0.64 (25) | 0.79 (14) | 1.00 (2) | 0.40 (5) | 0.56 (78) | 0.89 (136) |
| hybrid-rerank (tune) | 0.91 (43) | 0.58 (19) | 0.60 (5) | 0.80 (15) | 0.67 (6) | 0.86 (7) | 1.00 (1) | 0.33 (3) | 0.61 (36) | 0.87 (63) |
| hybrid-rerank (test) | 0.84 (38) | 0.81 (26) | 0.75 (8) | 0.71 (14) | 0.63 (19) | 0.71 (7) | 1.00 (1) | 0.50 (2) | 0.52 (42) | 0.90 (73) |
| hybrid-weighted (seed) | 0.88 (42) | 0.74 (19) | 0.78 (9) | 0.85 (13) | 0.80 (10) | 1.00 (5) | 1.00 (1) | 0.00 (1) | 0.55 (22) | 0.91 (78) |
| hybrid-weighted (all) | 0.88 (81) | 0.80 (45) | 0.77 (13) | 0.83 (29) | 0.68 (25) | 0.93 (14) | 0.50 (2) | 0.40 (5) | 0.69 (78) | 0.88 (136) |
| hybrid-weighted (tune) | 0.86 (43) | 0.68 (19) | 0.80 (5) | 0.93 (15) | 0.67 (6) | 1.00 (7) | 1.00 (1) | 0.33 (3) | 0.75 (36) | 0.86 (63) |
| hybrid-weighted (test) | 0.90 (38) | 0.89 (26) | 0.75 (8) | 0.71 (14) | 0.68 (19) | 0.86 (7) | 0.00 (1) | 0.50 (2) | 0.64 (42) | 0.90 (73) |

## Answers

| Run | Label | Set-up | Questions | with citations | citations valid | cites expected | avg s | cost $ |
|---|---|---|---|---|---|---|---|---|
| 2026-10-23T07:23 | answers: naive baseline vs app (draft Golden Set) | naive | 13 | 1.00 | 1.00 | 0.77 | 15.4 | 0.0097 |
| 2026-10-23T07:23 | answers: naive baseline vs app (draft Golden Set) | app | 25 | 1.00 | 1.00 | 0.88 | 13.6 | 0.0238 |

## Answers graded with RAGAs

On a fixed sample of the Golden Set (`compliance-advisor-ragas`). *Faithfulness*: share of the
answer's statements backed by the Passages and Rule Check results the Answer Model was given.
*Factual correctness*: agreement with the `answer_key` (F1 of matching claims). Small samples:
differences of a few points can be chance. With two graders, *apart* is the mean absolute
difference of their scores on the same answers.

**Grader.** Gemma 4 31B (Google, through OpenRouter), chosen on 2026-10-28 by grading the same
ten answers with Gemini 3.8 Flash as well. On faithfulness the two agreed (0.03 apart). On factual
correctness they were 0.22 apart, more than the 0.15 set beforehand as the limit: Gemini scored
lower throughout and gave 0.0 to answers that do match the `answer_key` in the cases checked, four
of its ten faithfulness gradings were cut off even at 4,096 output tokens, and it cost 13 times
more. So factual correctness is read as a comparison between runs with the same grader, not as an
absolute score. The first calibration run failed on most answers because ragas allows graders
1,024 output tokens by default; the limit is now 4,096.

| Run | Label | Answer Model | Strategy | Questions | Grader | Faithfulness | Factual correctness | apart (F / C) | Cost $ |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-28T14:12 | calibration: Gemma 4 31B vs Gemini 3.8 Flash | openai/gpt-6-luna | vector | 10 | google/gemma-4-31b-it | 0.64 (8 failed) | 0.44 (4 failed) | ? / 0.06 | 0.186 |
| 2026-10-28T14:12 | calibration: Gemma 4 31B vs Gemini 3.8 Flash | openai/gpt-6-luna | vector | 10 | google/gemini-3.8-flash | ? (10 failed) | 0.00 (8 failed) | ? / 0.06 | 0.186 |
| 2026-10-28T14:16 | calibration: Gemma 4 31B vs Gemini 3.8 Flash (max_tokens 4096) | openai/gpt-6-luna | vector | 10 | google/gemma-4-31b-it | 0.97 | 0.45 | 0.03 / 0.22 | 0.479 |
| 2026-10-28T14:16 | calibration: Gemma 4 31B vs Gemini 3.8 Flash (max_tokens 4096) | openai/gpt-6-luna | vector | 10 | google/gemini-3.8-flash | 0.96 (4 failed) | 0.23 | 0.03 / 0.22 | 0.479 |
| 2026-10-28T14:38 | baseline: GPT-6 Luna, vector search, 50 questions | openai/gpt-6-luna | vector | 50 | google/gemma-4-31b-it | 0.96 | 0.51 |  | 0.211 |
| 2026-10-28T15:16 | Mistral Large 4 vs Luna sample: 30 questions, vector search | mistralai/mistral-large-4-0 | vector | 20 of 30 (cost cap) | google/gemma-4-31b-it | 0.90 (1 failed) | 0.30 |  | 0.518 |

## Pre-Check screening

`config/precheck_set.yaml` holds attacks (manipulation attempts and off-topic questions) that
must be refused, and legitimate questions that look suspicious and must pass. *Refused* counts
a refusal in either category; *right category* how often the reason was the expected one.
*Wrongly refused* is the share of legitimate questions the screening refused. With `--golden`,
every Golden Set question is screened as well; none of them should be refused.

| Run | Label | Screening model | Attacks refused | right category | Legitimate wrongly refused | Golden Set wrongly refused | Cost $ |
|---|---|---|---|---|---|---|---|
| 2026-10-28T14:47 | first screening prompt, GPT-6 Luna | openai/gpt-6-luna | 30 of 30 | 30 of 30 | 0 of 30 | 0 of 214 | 0.013 |

_Regulatory information, not legal advice._
