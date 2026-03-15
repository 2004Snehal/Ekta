"""
Run the Insight Narrator pipeline directly from the command line.

Usage (from backend/ directory):
    python run_narrator.py             # runs for client_id=1
    python run_narrator.py --client 2  # runs for a specific client
    python run_narrator.py --clear     # clears the cache first, then runs
"""

import argparse
import json
import logging
import os
import sys

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_narrator")


def clear_cache(client_id: int) -> None:
    from api.deps import get_conn
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM insight_cache WHERE cache_key = %s", (f"narrator:{client_id}",))
        cur.execute("DELETE FROM pg_insight_history WHERE client_id = %s", (client_id,))
        conn.commit()
    logger.info("cache and dedup history cleared for client %s", client_id)


def main():
    parser = argparse.ArgumentParser(description="Run Insight Narrator pipeline")
    parser.add_argument("--client", type=int, default=1, help="client_id to run for (default: 1)")
    parser.add_argument("--clear", action="store_true", help="clear cache + dedup history before running")
    args = parser.parse_args()

    if args.clear:
        clear_cache(args.client)

    logger.info("starting narrator pipeline for client_id=%s", args.client)

    from intelligence.insight_narrator.pipeline import run_pipeline
    result = run_pipeline(client_id=args.client)

    if result is None:
        logger.error("pipeline returned None — check logs above for the error")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"  INSIGHT NARRATOR — client {result.client_id}  |  period {result.period}")
    print("=" * 60)

    if result.digest:
        print(f"\n[DIGEST]\n{result.digest}\n")

    if not result.insights:
        print("No insights generated this run.\n")
    else:
        for i, card in enumerate(result.insights, 1):
            delta_sign = "+" if card.delta_pct > 0 else ""
            print(f"[{i}] [{card.severity.upper():6}] [{card.category}]  {card.title}")
            print(f"     {card.entity_type}:{card.entity_id}  {card.metric_name}  "
                  f"{delta_sign}{card.delta_pct:.1f}%  "
                  f"(current={card.current_value:.2f}, 3m avg={card.reference_value:.2f})")
            print(f"     {card.body}")
            if card.root_cause_hint:
                print(f"     Hint: {card.root_cause_hint}")
            print()

    print(f"Generated at: {result.generated_at}")
    print(f"Total cards:  {len(result.insights)}")


if __name__ == "__main__":
    main()
