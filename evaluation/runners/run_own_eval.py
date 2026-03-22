"""
Part 2 — Own query evaluation runner.
Runs both pipelines (ours_rag_healing, simple_baseline) against own domain queries.
Measures: ESR, Healing Efficiency, P50/P95 Latency, VES static, LLM Judge.

Both pipelines run in parallel via asyncio + ThreadPoolExecutor.
Each thread gets its own DB connection (thread-safe).

Resilience guarantees:
  - Any exception in a single query is caught; evaluation continues.
  - Every completed result is appended to a JSONL file immediately (never lost).
  - A full checkpoint JSON is rewritten every CHECKPOINT_EVERY completions.

Usage:
    cd C:\\Users\\Hp\\Desktop\\Ekta
    python -m evaluation.runners.run_own_eval [--out results_own.json] [--limit 100] [--no-judge]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from evaluation.config import OWN_QUERIES_PATH, DEFAULT_CLIENT_ID, MAX_WORKERS
from evaluation.datasets.bird_loader import load_own_queries
from evaluation.pipelines.our_pipeline import OurPipeline
from evaluation.pipelines.simple_baseline import SimpleBaselinePipeline
from evaluation.metrics.healing import compute_healing_metrics
from evaluation.metrics.latency import compute_latency_percentiles
from evaluation.metrics.ves import ves_static
from evaluation.metrics.llm_judge import judge_result, aggregate_judge_scores
from evaluation.runners.report import print_own_report, save_json_report

LOGS_DIR         = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
CHECKPOINT_EVERY = 10

_log_lock   = threading.Lock()
_print_lock = threading.Lock()
_thread_local = threading.local()


# ---------------------------------------------------------------------------
# DB connection (thread-safe: one connection per thread)
# ---------------------------------------------------------------------------

def _get_db_url() -> str:
    db_url = os.getenv("EVAL_DB_URL")
    if db_url:
        return db_url
    from backend_config import DATABASE_URL
    return DATABASE_URL


def _get_thread_conn(db_url: str):
    conn = getattr(_thread_local, "conn", None)
    if conn is None or conn.closed:
        import psycopg2
        conn = psycopg2.connect(db_url)
        _thread_local.conn = conn
    return conn


# ---------------------------------------------------------------------------
# Logging / persistence helpers
# ---------------------------------------------------------------------------

def _open_query_log(path: Path):
    f = open(path, "w", encoding="utf-8")
    f.write("OWN QUERY EVALUATION LOG\n")
    f.write(f"Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("=" * 70 + "\n\n")
    f.flush()
    return f


def _log_query(f, done: int, total: int, record: dict) -> None:
    status  = "SUCCESS" if record["success"] else "FAILED"
    healing = f"healed x{record['heal_attempts']}" if record.get("heal_attempts") else "no healing"
    judge   = record.get("llm_judge_score")
    judge_s = f" | Judge={judge:.2f}" if judge is not None else ""
    f.write(f"[{done}/{total}] [{record['pipeline']}] {status} | {healing}"
            f" | {record['latency_ms']:.0f}ms | VES={record['ves_static']:.2f}{judge_s}\n")
    f.write(f"Q  : {record['question']}\n")
    f.write(f"SQL: {record.get('sql') or '(none)'}\n")
    if record.get("error"):
        f.write(f"ERR: {record['error']}\n")
    if judge is not None:
        tp = record.get("temporal_precision_score")
        sa = record.get("schema_alignment_score")
        fa = record.get("faithfulness_score")
        co = record.get("completeness_score")
        f.write(f"JUDGE: temporal={tp if tp is not None else '?'}"
                f" schema={sa if sa is not None else '?'}"
                f" faith={fa if fa is not None else '?'}"
                f" complete={co if co is not None else '?'}\n")
    f.write(f"ROWS: {record['row_count']}\n")
    f.write("-" * 70 + "\n\n")
    f.flush()


def _append_jsonl(jsonl_path: Path, record: dict) -> None:
    safe = {k: v for k, v in record.items() if k != "_result_obj"}
    with open(jsonl_path, "a", encoding="utf-8") as jf:
        jf.write(json.dumps(safe, default=str) + "\n")


def _write_checkpoint(ckpt_path: Path, all_raw: dict, pipeline_names: list) -> None:
    snapshot = {
        "checkpoint_at": datetime.now().isoformat(),
        "raw": {
            name: [{k: v for k, v in r.items() if k != "_result_obj"} for r in all_raw[name]]
            for name in pipeline_names
        },
    }
    tmp = ckpt_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    tmp.replace(ckpt_path)


# ---------------------------------------------------------------------------
# Blocking helpers (run inside thread pool)
# ---------------------------------------------------------------------------

def _run_one(pipeline, question: str, db_url: str, schema_str: str):
    """Run one query with a thread-local DB connection. Never raises."""
    try:
        conn = _get_thread_conn(db_url)
        return pipeline.run(question, conn=conn, schema_str=schema_str, client_id=DEFAULT_CLIENT_ID)
    except Exception:
        from evaluation.pipelines.base import EvalResult
        return EvalResult(
            question=question,
            pipeline_name=getattr(pipeline, "name", "unknown"),
            success=False,
            error=f"Unhandled: {traceback.format_exc(limit=3)}",
        )


def _run_judge(res, schema_str: str = "") -> dict:
    try:
        return judge_result(res, schema_hint=schema_str)
    except Exception as e:
        from evaluation.metrics.llm_judge import _null_judgment
        return _null_judgment(f"Judge wrapper error: {e}")


# ---------------------------------------------------------------------------
# Async pipeline runner (per pipeline, same as bird_eval pattern)
# ---------------------------------------------------------------------------

async def _run_pipeline_async(
    pipeline,
    queries: list[str],
    log_f,
    counters: dict,
    all_raw: dict,
    jsonl_path: Path,
    ckpt_path: Path,
    executor: ThreadPoolExecutor,
    sem: asyncio.Semaphore,
    db_url: str,
    schema_str: str,
    judge_enabled: bool,
    judge_outs: dict,
) -> None:
    loop  = asyncio.get_running_loop()
    total = len(queries)
    pipeline_names = list(all_raw.keys())

    async def _one(idx: int, question: str) -> None:
        async with sem:
            res = await loop.run_in_executor(
                executor, _run_one, pipeline, question, db_url, schema_str
            )

            ves = ves_static(res.sql) if res.sql else 0.0

            if judge_enabled:
                judge = await loop.run_in_executor(executor, _run_judge, res, schema_str)
            else:
                from evaluation.metrics.llm_judge import _null_judgment
                judge = _null_judgment("Judge disabled")

        record = {
            "i":                  idx,
            "pipeline":           pipeline.name,
            "question":           res.question,
            "sql":                res.sql,
            "success":            res.success,
            "error":              res.error,
            "first_shot_success": res.first_shot_success,
            "heal_attempts":      res.heal_attempts,
            "latency_ms":         res.latency_ms,
            "complexity":         getattr(res, "complexity", None),
            "row_count":          len(res.rows),
            "ves_static":         ves,
            "_result_obj":        res,
            **judge,
        }

        with _log_lock:
            counters[pipeline.name] += 1
            done = counters[pipeline.name]

            _log_query(log_f, done, total, record)
            _append_jsonl(jsonl_path, record)
            all_raw[pipeline.name].append(record)
            judge_outs[pipeline.name].append(judge)

            if done % CHECKPOINT_EVERY == 0 or done == total:
                _write_checkpoint(ckpt_path, all_raw, pipeline_names)

        status = "OK" if res.success else f"XX ({(res.error or '?')[:40]})"
        heal   = f" [healed x{res.heal_attempts}]" if res.heal_attempts else ""
        jscore = f"  Judge={judge['llm_judge_score']:.2f}" if judge.get("llm_judge_score") is not None else ""
        if done % 10 == 0 or not res.success:
            with _print_lock:
                print(f"  [{done:3d}/{total}] {pipeline.name:<22} | {status}{heal}  {res.latency_ms:.0f}ms  VES={ves:.2f}{jscore}")

    await asyncio.gather(*[_one(i, q) for i, q in enumerate(queries, 1)])


# ---------------------------------------------------------------------------
# Metrics (per pipeline)
# ---------------------------------------------------------------------------

def compute_pipeline_metrics(all_raw: dict, judge_outs: dict, pipeline_name: str) -> dict:
    raw = all_raw[pipeline_name]
    result_objs = [r["_result_obj"] for r in raw if "_result_obj" in r]

    heal_m = compute_healing_metrics(result_objs)
    lat_m  = compute_latency_percentiles(result_objs)

    ves_scores = [r["ves_static"] for r in raw]
    valid_ves  = [s for s in ves_scores if s is not None]
    mean_ves   = sum(valid_ves) / len(valid_ves) if valid_ves else 0.0

    judge_agg = aggregate_judge_scores(judge_outs[pipeline_name])

    return {
        "n_total":         len(result_objs),
        **heal_m,
        "p50_ms":          lat_m.get("p50"),
        "p95_ms":          lat_m.get("p95"),
        "mean_latency_ms": lat_m.get("mean"),
        "mean_ves_static": round(mean_ves, 4),
        "n_ves_perfect":   sum(1 for s in valid_ves if s == 1.0),
        "n_ves_penalised": sum(1 for s in valid_ves if s < 1.0),
        **judge_agg,
    }


# ---------------------------------------------------------------------------
# Async main
# ---------------------------------------------------------------------------

async def _main_async(args: argparse.Namespace) -> None:
    queries = load_own_queries(OWN_QUERIES_PATH)
    if args.limit:
        queries = queries[:args.limit]
    total = len(queries)
    print(f"[own_eval] Loaded {total} queries from own_queries.txt")

    db_url = _get_db_url()

    # Init: fetch schema once, init RAG for our pipeline
    import psycopg2
    init_conn = psycopg2.connect(db_url)
    from intelligence.nlq.context import fetch_live_schema
    schema_str = fetch_live_schema(init_conn)

    pipelines = [OurPipeline(conn=init_conn), SimpleBaselinePipeline()]
    init_conn.close()

    pipeline_names = [p.name for p in pipelines]

    ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path   = LOGS_DIR / f"own_eval_{ts}.txt"
    jsonl_path = LOGS_DIR / f"own_eval_{ts}.jsonl"
    ckpt_path  = LOGS_DIR / f"own_eval_{ts}_checkpoint.json"

    log_f = _open_query_log(log_path)
    judge_enabled = not args.no_judge
    print(f"[own_eval] Txt log     -> {log_path}")
    print(f"[own_eval] Live JSONL  -> {jsonl_path}")
    print(f"[own_eval] Checkpoint  -> {ckpt_path}  (rewritten every {CHECKPOINT_EVERY} queries)")
    print(f"[own_eval] Pipelines   -> {pipeline_names}")
    print(f"[own_eval] LLM Judge   -> {'enabled' if judge_enabled else 'disabled'}")
    print(f"[own_eval] Running {len(pipelines)} pipelines in parallel...\n")

    all_raw    = {p.name: [] for p in pipelines}
    counters   = {p.name: 0  for p in pipelines}
    judge_outs = {p.name: [] for p in pipelines}

    n_workers = MAX_WORKERS * len(pipelines)
    sem = asyncio.Semaphore(MAX_WORKERS)

    def _save_results(interrupted: bool = False):
        label = "INTERRUPTED" if interrupted else "complete"
        log_f.write(f"\n{'='*70}\nEvaluation {label}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_f.close()
        _write_checkpoint(ckpt_path, all_raw, pipeline_names)

        pipeline_metrics = {}
        for p in pipelines:
            if all_raw[p.name]:
                pipeline_metrics[p.name] = compute_pipeline_metrics(all_raw, judge_outs, p.name)

        if not interrupted and pipeline_metrics:
            print_own_report(pipeline_metrics)
        elif interrupted:
            done_total = sum(counters.values())
            expected   = total * len(pipelines)
            print(f"\n[own_eval] Interrupted -- {done_total}/{expected} results saved.")

        # Strip _result_obj before saving
        for name in all_raw:
            for r in all_raw[name]:
                r.pop("_result_obj", None)

        save_json_report({"metrics": pipeline_metrics, "raw": all_raw}, args.out)
        print(f"[own_eval] Log saved   -> {log_path}")

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        try:
            await asyncio.gather(*[
                _run_pipeline_async(
                    p, queries, log_f, counters, all_raw,
                    jsonl_path, ckpt_path, executor, sem,
                    db_url, schema_str, judge_enabled, judge_outs,
                )
                for p in pipelines
            ])
        except (KeyboardInterrupt, asyncio.CancelledError):
            _save_results(interrupted=True)
            return

    _save_results(interrupted=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Own query evaluation runner")
    parser.add_argument("--out",      type=str,  default="results_own.json")
    parser.add_argument("--limit",    type=int,  default=100)
    parser.add_argument("--no-judge", action="store_true",
                        help="Skip LLM judge (faster, no extra LLM calls)")
    args = parser.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
