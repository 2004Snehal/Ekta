# NLQ Evaluation

Benchmarks for the Frammer AI NLQ-to-SQL pipeline. Two tracks:

- **Track 1 (BIRD):** Standard Text-to-SQL benchmark — compares `ours_rag_healing` vs `simple_baseline` on gold SQL.
- **Track 2 (Own Queries):** 100 domain-specific queries against the live PostgreSQL DB — includes LLM-as-Judge (G-Eval).

## Folder Structure

```
evaluation/
  config.py                  # Paths, LLM config, concurrency
  bird_rag.py                # BIRD-specific RAG (leave-one-out)
  test_pipelines.py          # Smoke test — 1 query per pipeline
  METRICS.md                 # Full metric glossary
  datasets/
    bird_loader.py           # HuggingFace BIRD loader + own query parser
    own_queries.txt          # 200 domain queries
    bird_dbs/                # (gitignored) downloaded BIRD SQLite DBs
  pipelines/
    base.py                  # EvalResult dataclass + Pipeline ABC
    our_pipeline.py          # Full RAG + self-healing pipeline
    simple_baseline.py       # Bare 2-call LLM (schema-only, no RAG/healing)
    metricflow_pipeline.py   # Metricflow branch (own queries only)
  metrics/
    ex_accuracy.py           # EX, First-shot EX, Healed EX
    ves.py                   # VES (BIRD timed) + VES static (heuristic)
    healing.py               # ESR, Healing Efficiency
    latency.py               # P50, P95
    error_breakdown.py       # Categorised error counts
    llm_judge.py             # G-Eval: temporal, schema, faithfulness, completeness
  runners/
    run_bird_eval.py         # Track 1 runner (async, parallel pipelines)
    run_own_eval.py          # Track 2 runner (async, parallel pipelines + judge)
    report.py                # Terminal report renderer
  logs/                      # (gitignored) per-run .txt, .jsonl, checkpoint .json
```

## Setup

```bash
cd evaluation
pip install -r requirements.txt
```

The backend `.env` must be configured (LLM API key, DATABASE_URL).

## Download BIRD Databases

Dataset: [`birdsql/bird_mini_dev`](https://huggingface.co/datasets/birdsql/bird_mini_dev) (loaded via HuggingFace `datasets`).

SQLite DBs must be downloaded separately:

1. Go to https://bird-bench.github.io/
2. Download "Mini-Dev Databases" (Google Drive link on the page)
3. Extract into `evaluation/datasets/bird_dbs/` so the structure is:
   ```
   bird_dbs/<db_id>/sqlite/<db_id>.db      (e.g. debit_card_specializing)
   bird_dbs/<db_id>/<db_id>.sqlite          (alternative naming)
   ```

The runner auto-detects which DBs are present and evaluates only those.

## Run

```bash
# From project root (C:\Users\Hp\Desktop\Ekta)

# Track 1 — BIRD (2 pipelines, parallel)
python -m evaluation.runners.run_bird_eval --limit 100 --out results_bird.json

# Track 2 — Own queries (2 pipelines + LLM judge, parallel)
python -m evaluation.runners.run_own_eval --limit 100 --out results_own.json

# Track 2 without judge (faster)
python -m evaluation.runners.run_own_eval --limit 100 --no-judge --out results_own.json

# Smoke test (1 query per pipeline)
python -m evaluation.test_pipelines
```

## Output

Each run produces:
- `results_*.json` — final metrics + per-query raw data
- `logs/*_<timestamp>.txt` — human-readable per-query log
- `logs/*_<timestamp>.jsonl` — machine-readable, one JSON per completed query (append-only, never lost)
- `logs/*_checkpoint.json` — full snapshot rewritten every 10 queries

Ctrl+C at any point saves all completed results.
