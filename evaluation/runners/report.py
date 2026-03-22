"""
Terminal report renderer for evaluation results.
Produces formatted tables for both BIRD and own-query evaluation.
"""
from __future__ import annotations


def _bar(value: float, width: int = 20) -> str:
    filled = round(value * width)
    return "#" * filled + "." * (width - filled)


def _pct(v, fmt="{:6.1f}%"):
    if v is None:
        return "   N/A"
    return fmt.format(v * 100)


def print_bird_report(pipeline_metrics: dict[str, dict]) -> None:
    print("\n" + "=" * 70)
    print("  BIRD EVALUATION REPORT")
    print("=" * 70)

    for name, m in pipeline_metrics.items():
        print(f"\n  Pipeline: {name}")
        print(f"  {'-' * 50}")
        ex = m.get("ex", 0)
        fs_ex = m.get("first_shot_ex", 0)
        healed = m.get("healed_ex")
        ves = m.get("ves", 0)
        n = m.get("n_total", 0)

        print(f"  EX (Execution Accuracy) : {ex*100:6.1f}%  {_bar(ex)}")
        print(f"  First-shot EX           : {fs_ex*100:6.1f}%  {_bar(fs_ex)}")
        if healed is not None:
            print(f"  Healed EX               : {healed*100:6.1f}%  {_bar(healed)}")
        print(f"  VES                     : {ves*100:6.1f}%  {_bar(ves)}")
        print(f"  Queries evaluated       : {n}")

        eb = m.get("error_breakdown", {})
        if eb:
            print(f"  Error breakdown:")
            for etype, count in eb.items():
                if etype not in ("total_errors", "error_rate"):
                    print(f"    {etype:<22}: {count}")

    print("\n" + "=" * 70)


def print_own_report(pipeline_metrics: dict[str, dict]) -> None:
    """
    pipeline_metrics: {pipeline_name: {esr, healing_efficiency, p50_ms, ...}}
    Multi-pipeline comparison.
    """
    print("\n" + "=" * 70)
    print("  OWN QUERY EVALUATION REPORT")
    print("=" * 70)

    for name, m in pipeline_metrics.items():
        print(f"\n  Pipeline: {name}")
        print(f"  {'-' * 50}")

        esr = m.get("esr", 0)
        he  = m.get("healing_efficiency")
        p50 = m.get("p50_ms", 0)
        p95 = m.get("p95_ms", 0)
        mean_ves = m.get("mean_ves_static", 0)
        n   = m.get("n_total", 0)

        print(f"  ESR                     : {esr*100:6.1f}%  {_bar(esr)}")
        if he is not None:
            print(f"  Healing Efficiency      : {he*100:6.1f}%  {_bar(he)}")
        else:
            print(f"  Healing Efficiency      :    N/A  (no healing)")
        print(f"  P50 Latency             : {p50:7.1f} ms")
        print(f"  P95 Latency             : {p95:7.1f} ms")
        print(f"  VES (static, mean)      : {mean_ves*100:6.1f}%  {_bar(mean_ves)}")
        print(f"  Queries evaluated       : {n}")

        n_perfect = m.get("n_ves_perfect", 0)
        n_pen     = m.get("n_ves_penalised", 0)
        print(f"  VES perfect SQL         : {n_perfect}")
        print(f"  VES penalised SQL       : {n_pen}")

        judge_score = m.get("mean_llm_judge_score")
        if judge_score is not None:
            print(f"\n  -- LLM Judge (G-Eval, Qwen) --")
            print(f"  Composite Judge Score   : {judge_score*100:6.1f}%  {_bar(judge_score)}")
            tp = m.get("mean_temporal_precision")
            sa = m.get("mean_schema_alignment")
            fa = m.get("mean_faithfulness")
            co = m.get("mean_completeness")
            if tp is not None: print(f"    Temporal Precision    : {tp*100:6.1f}%  {_bar(tp)}")
            if sa is not None: print(f"    Schema Alignment      : {sa*100:6.1f}%  {_bar(sa)}")
            if fa is not None: print(f"    Faithfulness          : {fa*100:6.1f}%  {_bar(fa)}")
            if co is not None: print(f"    Completeness          : {co*100:6.1f}%  {_bar(co)}")
            n_judged = m.get("n_judged", 0)
            n_jerr   = m.get("n_judge_errors", 0)
            print(f"  Judged / errors         : {n_judged} / {n_jerr}")

    # Comparison table if multiple pipelines
    names = list(pipeline_metrics.keys())
    if len(names) >= 2:
        print(f"\n  {'='*50}")
        print(f"  PIPELINE COMPARISON")
        print(f"  {'='*50}")

        # Header
        col_w = 14
        header = f"  {'Metric':<26}"
        for n in names:
            header += f" {n:>{col_w}}"
        print(header)
        print(f"  {'-'*26}" + f" {'-'*col_w}" * len(names))

        # Rows
        rows = [
            ("ESR",              "esr",              True),
            ("Healing Eff.",     "healing_efficiency",True),
            ("P50 Latency (ms)", "p50_ms",           False),
            ("P95 Latency (ms)", "p95_ms",           False),
            ("VES Static",       "mean_ves_static",  True),
            ("Judge Composite",  "mean_llm_judge_score", True),
            ("  Temporal",       "mean_temporal_precision", True),
            ("  Schema Align",   "mean_schema_alignment", True),
            ("  Faithfulness",   "mean_faithfulness", True),
            ("  Completeness",   "mean_completeness", True),
        ]

        for label, key, is_pct in rows:
            line = f"  {label:<26}"
            for n in names:
                v = pipeline_metrics[n].get(key)
                if v is None:
                    line += f" {'N/A':>{col_w}}"
                elif is_pct:
                    line += f" {v*100:>{col_w-1}.1f}%"
                else:
                    line += f" {v:>{col_w}.1f}"
            print(line)

    print("\n" + "=" * 70)


def save_json_report(data: dict, path: str) -> None:
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"[report] saved -> {path}")
