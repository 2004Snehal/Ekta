# NLQ Evaluation — Metric Glossary

This document defines all metrics used across two evaluation tracks. **Track 1** benchmarks two pipelines against BIRD mini_dev, a standard Text-to-SQL dataset with gold SQL and SQLite databases. **Track 2** evaluates only our pipeline on domain-specific queries against the live PostgreSQL database, prioritising operational metrics and LLM-as-Judge quality assessment.

---

## Track 1: BIRD Evaluation

### EX — Execution Accuracy

- **Formula:** `EX = (1/N) * Σ 1[result_set(pred_sql) == result_set(gold_sql)]`
- **Range:** 0–1
- **What it catches:** Whether the predicted SQL returns the same result set as the gold SQL, regardless of syntactic form. The primary correctness signal for Text-to-SQL.
- **Implementation:** `evaluation/metrics/ex_accuracy.py` → `ex_score()`, `compute_ex_metrics()`

### First-shot EX vs. Healed EX

- **Formula:** First-shot EX counts only queries where the first generated SQL was correct (no healing). Healed EX counts queries where healing was required and ultimately succeeded.
- **Range:** 0–1 each
- **What it catches:** Separates generation quality from error-recovery quality.

### VES — Valid Efficiency Score

- **Formula:** `VES = (1/N) * Σ [EX_i * sqrt(R_i)]` where `R_i = T_gold / T_pred` (execution time ratio, capped at 1).
- **Range:** 0–1
- **What it catches:** Penalises correct but slow queries.
- **Implementation:** `evaluation/metrics/ves.py` → `compute_ves_bird()`

### Error Breakdown

- **Formula:** Categorical count of failure modes: `syntax_error`, `wrong_table`, `empty_result`, `timeout`, `type_error`, `other`.
- **Range:** Non-negative integers; `error_rate = total_errors / N`.
- **Implementation:** `evaluation/metrics/error_breakdown.py` → `compute_error_breakdown()`

---

## Track 2: Own Query Evaluation (ours only)

### ESR — Execution Success Rate

- **Formula:** `ESR = (number of queries where SQL executed without error) / N`
- **Range:** 0–1
- **Implementation:** `evaluation/metrics/healing.py` → `compute_healing_metrics()`

### Healing Efficiency

- **Formula:** `HE = (queries_healed_successfully) / (queries_that_needed_healing)`
- **Range:** 0–1; `None` if no queries needed healing.
- **Implementation:** `evaluation/metrics/healing.py` → `compute_healing_efficiency()`

### P50 / P95 Latency

- **Formula:** 50th and 95th percentile of `result.latency_ms` across all queries.
- **Range:** Milliseconds, unbounded above.
- **Implementation:** `evaluation/metrics/latency.py` → `compute_latency_percentiles()`

### VES Static

- **Formula:** Starts at 1.0, deductions for SELECT *, missing LIMIT, wrong table for aggregates, no client_id filter, cartesian joins.
- **Range:** 0–1
- **What it catches:** Structural SQL quality heuristic when no gold SQL is available.
- **Implementation:** `evaluation/metrics/ves.py` → `ves_static()`

### LLM Judge (G-Eval Style, 4 Criteria)

Post-hoc quality assessment using the same Qwen Coder model, scoring four dimensions with chain-of-thought reasoning:

| Criterion | Weight | What It Measures |
|---|:---:|---|
| **Temporal Precision** | 30% | Does the SQL correctly capture every time constraint implied by the question? |
| **Schema Alignment** | 25% | Are the right tables, columns, and aggregations used for the stated intent? |
| **Faithfulness** | 30% | Is every factual claim in the answer grounded in the result rows? (No hallucination) |
| **Completeness** | 15% | Does the answer address ALL parts of the question? |

- **Composite:** `judge_score = 0.30 * temporal + 0.25 * schema + 0.30 * faith + 0.15 * complete`
- **Range:** 0–1
- **Implementation:** `evaluation/metrics/llm_judge.py` → `judge_result()`, `aggregate_judge_scores()`

---

## Comparison Table

| Metric              | ours_rag_healing | simple_baseline | Track        |
|---------------------|:----------------:|:---------------:|--------------|
| EX                  | yes              | yes             | BIRD         |
| First-shot EX       | yes              | yes             | BIRD         |
| Healed EX           | yes              | no              | BIRD         |
| VES (timed)         | yes              | yes             | BIRD         |
| Error Breakdown     | yes              | yes             | BIRD         |
| ESR                 | yes              | yes             | Own queries  |
| Healing Efficiency  | yes              | —               | Own queries  |
| P50 / P95 Latency   | yes              | yes             | Own queries  |
| VES Static          | yes              | yes             | Own queries  |
| LLM Judge           | yes              | yes             | Own queries  |
