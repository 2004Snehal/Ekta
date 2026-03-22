"""
Single-query smoke test for all 3 pipelines.
Runs one question through each pipeline against our live PostgreSQL DB,
logs full results to evaluation/logs/test_<pipeline>.txt and a combined summary.

Usage:
    cd C:\\Users\\Hp\\Desktop\\Ekta
    python -m evaluation.test_pipelines
"""
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Paths
EVAL_ROOT    = Path(__file__).parent
BACKEND_ROOT = EVAL_ROOT.parent / "backend"
LOGS_DIR     = EVAL_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(EVAL_ROOT.parent))
sys.path.insert(0, str(BACKEND_ROOT))

TEST_QUERY    = "Show total published videos by channel for the last 3 months"
CLIENT_ID     = int(os.getenv("EVAL_CLIENT_ID", "1"))
RUN_TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── DB connection ──────────────────────────────────────────────────────────────

def get_conn():
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv(BACKEND_ROOT / ".env")
    db_url = os.getenv("DATABASE_URL") or os.getenv("EVAL_DB_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set in .env")
    return psycopg2.connect(db_url)


# ── Logger ─────────────────────────────────────────────────────────────────────

def write_log(pipeline_name: str, result, extra_notes: str = "") -> Path:
    log_path = LOGS_DIR / f"test_{pipeline_name}.txt"
    lines = [
        f"{'='*60}",
        f"PIPELINE TEST LOG — {pipeline_name}",
        f"Run at : {RUN_TIMESTAMP}",
        f"{'='*60}",
        f"",
        f"QUESTION",
        f"  {result.question}",
        f"",
        f"GENERATED SQL",
        f"  {result.sql or '(none)'}",
        f"",
        f"EXECUTION",
        f"  success          : {result.success}",
        f"  first_shot_success: {result.first_shot_success}",
        f"  heal_attempts    : {result.heal_attempts}",
        f"  latency_ms       : {result.latency_ms}",
        f"  row_count        : {len(result.rows)}",
        f"",
        f"ERROR",
        f"  {result.error or 'none'}",
        f"",
        f"ANSWER",
        f"  {result.answer or '(no answer generated)'}",
        f"",
        f"SAMPLE ROWS (first 5)",
    ]
    for i, row in enumerate(result.rows[:5], 1):
        lines.append(f"  [{i}] {json.dumps(row, default=str)}")
    if not result.rows:
        lines.append("  (no rows)")

    if extra_notes:
        lines += ["", "NOTES", f"  {extra_notes}"]

    lines += ["", f"{'='*60}", ""]
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return log_path


def write_summary(results: list[dict]) -> Path:
    summary_path = LOGS_DIR / "test_summary.txt"
    lines = [
        f"{'='*60}",
        f"PIPELINE SMOKE TEST — SUMMARY",
        f"Run at   : {RUN_TIMESTAMP}",
        f"Question : {TEST_QUERY}",
        f"{'='*60}",
        f"",
        f"{'Pipeline':<25} {'Success':<10} {'1st-shot':<10} {'Heals':<8} {'Rows':<8} {'Latency':>10}",
        f"{'-'*25} {'-'*10} {'-'*10} {'-'*8} {'-'*8} {'-'*10}",
    ]
    for r in results:
        lines.append(
            f"{r['name']:<25} "
            f"{'YES' if r['success'] else 'NO':<10} "
            f"{'YES' if r['first_shot'] else 'NO':<10} "
            f"{r['heals']:<8} "
            f"{r['rows']:<8} "
            f"{r['latency_ms']:>9.0f}ms"
        )
    lines += ["", f"Full logs → {LOGS_DIR}", f"{'='*60}", ""]
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


# ── Run each pipeline ──────────────────────────────────────────────────────────

def run_test():
    from evaluation.pipelines.our_pipeline    import OurPipeline
    from evaluation.pipelines.simple_baseline import SimpleBaselinePipeline
    from intelligence.nlq.context             import fetch_live_schema

    conn = get_conn()
    schema_str = fetch_live_schema(conn)

    pipelines = [
        ("ours_rag_healing", OurPipeline(conn=conn),      {}),
        ("simple_baseline",  SimpleBaselinePipeline(),    {}),
    ]

    summary_rows = []

    for name, pipeline, _ in pipelines:
        print(f"\n{'-'*50}")
        print(f"  Testing: {name}")
        print(f"  Query  : {TEST_QUERY}")
        print(f"{'-'*50}")

        t0 = time.perf_counter()
        result = pipeline.run(
            question  = TEST_QUERY,
            conn      = conn,
            schema_str= schema_str,
            client_id = CLIENT_ID,
        )
        elapsed = round((time.perf_counter() - t0) * 1000, 1)

        # Print to terminal
        status = "OK  SUCCESS" if result.success else f"XX FAILED -- {result.error}"
        print(f"  Status       : {status}")
        print(f"  SQL          : {(result.sql or '')[:120]}{'...' if result.sql and len(result.sql) > 120 else ''}")
        print(f"  Rows         : {len(result.rows)}")
        print(f"  Latency      : {result.latency_ms:.0f} ms")
        if result.heal_attempts:
            print(f"  Heal attempts: {result.heal_attempts}")
        if result.answer:
            print(f"  Answer       : {result.answer[:200]}")

        # Write per-pipeline log
        log_path = write_log(name, result)
        print(f"  Log saved -> {log_path}")

        summary_rows.append({
            "name":        name,
            "success":     result.success,
            "first_shot":  result.first_shot_success,
            "heals":       result.heal_attempts,
            "rows":        len(result.rows),
            "latency_ms":  result.latency_ms,
        })

    # Write summary
    summary_path = write_summary(summary_rows)
    print(f"\n{'='*50}")
    print(f"  Summary saved -> {summary_path}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    run_test()
