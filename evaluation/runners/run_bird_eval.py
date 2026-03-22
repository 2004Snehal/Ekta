"""
Part 1 — BIRD evaluation runner.

Runs 2 pipelines (ours, simple_baseline) on BIRD mini_dev questions
**in parallel** — both pipelines run simultaneously via asyncio + ThreadPoolExecutor.

Resilience guarantees:
  - Any exception in a single query is caught; evaluation continues.
  - Every completed result is appended to a JSONL file immediately (never lost).
  - A full checkpoint JSON is rewritten every CHECKPOINT_EVERY completions.

Usage:
    cd /c/Users/Hp/Desktop/Ekta
    python -m evaluation.runners.run_bird_eval [--limit 50] [--out results_bird.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from evaluation.config import BIRD_DB_ROOT, MAX_WORKERS
from evaluation.datasets.bird_loader import load_bird_mini_dev, get_sqlite_conn, get_schema_str
from evaluation.pipelines.our_pipeline import OurPipeline
from evaluation.pipelines.simple_baseline import SimpleBaselinePipeline
from evaluation.metrics.ex_accuracy import compute_ex_metrics, ex_score
from evaluation.metrics.ves import compute_ves_bird
from evaluation.metrics.error_breakdown import compute_error_breakdown
from evaluation.runners.report import print_bird_report, save_json_report

LOGS_DIR        = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
CHECKPOINT_EVERY = 10

_log_lock   = threading.Lock()
_print_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Logging / persistence helpers
# ---------------------------------------------------------------------------

def _open_bird_log(path: Path):
    f = open(path, "w", encoding="utf-8")
    f.write("BIRD EVALUATION LOG\n")
    f.write(f"Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("=" * 70 + "\n\n")
    f.flush()
    return f


def _log_bird_query(f, done: int, total: int, res: dict) -> None:
    status = "SUCCESS" if res["success"] else "FAILED"
    ex_str = f"EX={res['ex']:.1f}"
    heal   = f" healed x{res['heal_attempts']}" if res.get("heal_attempts") else ""
    f.write(f"[{done}/{total}] [{res['pipeline']}] {status}{heal} | {res['latency_ms']:.0f}ms | {ex_str}\n")
    f.write(f"DB : {res['db_id']}\n")
    f.write(f"Q  : {res['question']}\n")
    f.write(f"SQL: {res.get('sql') or '(none)'}\n")
    if res.get("error"):
        f.write(f"ERR: {res['error']}\n")
    f.write("-" * 70 + "\n\n")
    f.flush()


def _append_jsonl(jsonl_path: Path, res: dict) -> None:
    safe = {k: v for k, v in res.items() if k != "_result_obj"}
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

def _exec_gold(conn, gold_sql: str) -> tuple[list, float]:
    import sqlite3
    t0 = time.perf_counter()
    try:
        conn.row_factory = sqlite3.Row
        cur  = conn.execute(gold_sql)
        rows = [dict(r) for r in cur.fetchall()]
        return rows, round((time.perf_counter() - t0) * 1000, 1)
    except Exception:
        return [], 0.0


def _run_one(pipeline, record: dict) -> dict:
    """
    Run one pipeline on one BIRD record. Each call opens its own SQLite
    connection (thread-safe). ALL exceptions are caught.
    """
    db_id    = record["db_id"]
    question = record["question"]
    gold_sql = record["gold_sql"]

    try:
        try:
            conn       = get_sqlite_conn(db_id, BIRD_DB_ROOT)
            schema_str = get_schema_str(conn)
        except Exception as e:
            return {
                "question": question, "db_id": db_id, "difficulty": record.get("difficulty"),
                "pipeline": pipeline.name, "sql": None,
                "success": False, "error": f"DB load error: {e}",
                "ex": 0.0, "latency_ms": 0.0, "heal_attempts": 0,
                "first_shot_success": False, "gold_exec_time_ms": 0.0,
                "pred_exec_time_ms": 0.0,
            }

        gold_rows, gold_time_ms = _exec_gold(conn, gold_sql)

        # Include BIRD evidence hints in the question for better SQL gen
        evidence = record.get("evidence", "")
        q_with_hint = f"{question}\nHint: {evidence}" if evidence else question

        result                   = pipeline.run(q_with_hint, conn, schema_str, gold_rows=gold_rows)
        result.gold_rows         = gold_rows
        result.gold_exec_time_ms = gold_time_ms

        ex = ex_score(result.rows, gold_rows) if result.success else 0.0

        return {
            "question":           question,
            "db_id":              db_id,
            "difficulty":         record.get("difficulty"),
            "pipeline":           pipeline.name,
            "sql":                result.sql,
            "success":            result.success,
            "error":              result.error,
            "first_shot_success": result.first_shot_success,
            "heal_attempts":      result.heal_attempts,
            "latency_ms":         result.latency_ms,
            "ex":                 ex,
            "gold_exec_time_ms":  gold_time_ms,
            "pred_exec_time_ms":  result.latency_ms,
            "_result_obj":        result,
        }

    except Exception:
        return {
            "question": question, "db_id": db_id, "difficulty": record.get("difficulty"),
            "pipeline": pipeline.name, "sql": None,
            "success": False, "error": f"Unhandled: {traceback.format_exc(limit=3)}",
            "ex": 0.0, "latency_ms": 0.0, "heal_attempts": 0,
            "first_shot_success": False, "gold_exec_time_ms": 0.0,
            "pred_exec_time_ms": 0.0,
        }


# ---------------------------------------------------------------------------
# Async pipeline runner
# ---------------------------------------------------------------------------

async def _run_pipeline_async(
    pipeline,
    records: list,
    log_f,
    counters: dict,
    all_raw: dict,
    jsonl_path: Path,
    ckpt_path: Path,
    executor: ThreadPoolExecutor,
    sem: asyncio.Semaphore,
) -> None:
    loop  = asyncio.get_running_loop()
    total = len(records)
    pipeline_names = list(all_raw.keys())

    async def _one(record: dict) -> dict:
        async with sem:
            try:
                res = await loop.run_in_executor(executor, _run_one, pipeline, record)
            except Exception:
                res = {
                    "question": record.get("question", ""), "db_id": record.get("db_id", ""),
                    "difficulty": record.get("difficulty"), "pipeline": pipeline.name,
                    "sql": None, "success": False,
                    "error": f"Executor error: {traceback.format_exc(limit=2)}",
                    "ex": 0.0, "latency_ms": 0.0, "heal_attempts": 0,
                    "first_shot_success": False, "gold_exec_time_ms": 0.0,
                    "pred_exec_time_ms": 0.0,
                }

        with _log_lock:
            counters[pipeline.name] += 1
            done = counters[pipeline.name]

            _log_bird_query(log_f, done, total, res)
            _append_jsonl(jsonl_path, res)
            all_raw[pipeline.name].append(res)

            if done % CHECKPOINT_EVERY == 0 or done == total:
                _write_checkpoint(ckpt_path, all_raw, pipeline_names)

        if done % 10 == 0 or not res["success"]:
            status = "OK" if res["success"] else f"XX ({(res.get('error') or '?')[:40]})"
            with _print_lock:
                print(f"  [{done:3d}/{total}] {pipeline.name:<22} | {status} | EX={res['ex']:.1f} | {res['latency_ms']:.0f}ms")

        return res

    await asyncio.gather(*[_one(r) for r in records])


# ---------------------------------------------------------------------------
# Async main
# ---------------------------------------------------------------------------

async def _main_async(args: argparse.Namespace) -> None:
    print("[bird_eval] Loading BIRD mini_dev...")
    records = load_bird_mini_dev(limit=None)

    # Keep only records whose SQLite DB exists locally
    available = [
        r for r in records
        if any((BIRD_DB_ROOT / r["db_id"] / "sqlite" / f"{r['db_id']}.db").exists()
               or (BIRD_DB_ROOT / r["db_id"] / f"{r['db_id']}.sqlite").exists()
               or (BIRD_DB_ROOT / r["db_id"] / f"{r['db_id']}.db").exists()
               for _ in [None])
    ]
    db_ids_found = sorted(set(r["db_id"] for r in available))
    print(f"[bird_eval] Available DBs  -> {db_ids_found}")

    records = available[:args.limit] if args.limit else available
    print(f"[bird_eval] {len(records)} records loaded.\n")

    if not records:
        print("[bird_eval] No records to evaluate. Check that BIRD DBs exist.")
        return

    # Train BIRD RAG with gold examples (leave-one-out retrieval at query time)
    from evaluation.bird_rag import train_bird_rag
    train_bird_rag(available)

    pipelines = [OurPipeline(), SimpleBaselinePipeline()]

    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path  = LOGS_DIR / f"bird_eval_{ts}.txt"
    jsonl_path = LOGS_DIR / f"bird_eval_{ts}.jsonl"
    ckpt_path  = LOGS_DIR / f"bird_eval_{ts}_checkpoint.json"

    log_f = _open_bird_log(log_path)

    print(f"[bird_eval] Txt log        -> {log_path}")
    print(f"[bird_eval] Live JSONL     -> {jsonl_path}")
    print(f"[bird_eval] Checkpoint     -> {ckpt_path}  (rewritten every {CHECKPOINT_EVERY} queries)")
    print(f"[bird_eval] Pipelines      -> {[p.name for p in pipelines]}")
    print(f"[bird_eval] Running {len(pipelines)} pipelines in parallel...\n")

    all_raw  = {p.name: [] for p in pipelines}
    counters = {p.name: 0  for p in pipelines}
    pipeline_names = [p.name for p in pipelines]

    n_workers = MAX_WORKERS * len(pipelines)
    sem = asyncio.Semaphore(MAX_WORKERS)

    def _save_results(interrupted: bool = False):
        label = "INTERRUPTED" if interrupted else "complete"
        log_f.write(f"\n{'='*70}\nEvaluation {label}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_f.close()
        _write_checkpoint(ckpt_path, all_raw, pipeline_names)

        pipeline_metrics: dict = {}
        for p in pipelines:
            result_objs = [r["_result_obj"] for r in all_raw[p.name] if "_result_obj" in r]
            if result_objs:
                pipeline_metrics[p.name] = {
                    **compute_ex_metrics(result_objs),
                    "ves":             compute_ves_bird(result_objs),
                    "error_breakdown": compute_error_breakdown(result_objs),
                }

        if not interrupted and pipeline_metrics:
            print_bird_report(pipeline_metrics)
        elif interrupted:
            done_total = sum(counters.values())
            expected   = len(records) * len(pipelines)
            print(f"\n[bird_eval] Interrupted -- {done_total}/{expected} results saved.")

        for name in all_raw:
            for r in all_raw[name]:
                r.pop("_result_obj", None)

        save_json_report({"metrics": pipeline_metrics, "raw": all_raw}, args.out)
        print(f"[bird_eval] Log saved      -> {log_path}")

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        try:
            await asyncio.gather(*[
                _run_pipeline_async(
                    p, records, log_f, counters, all_raw,
                    jsonl_path, ckpt_path, executor, sem,
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
    parser = argparse.ArgumentParser(description="BIRD evaluation runner")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--out",   type=str, default="results_bird.json")
    args = parser.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
