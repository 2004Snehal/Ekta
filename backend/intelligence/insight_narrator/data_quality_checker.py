"""
Phase 1 Analyzer — Data Quality Checker.

Checks the fact_sample for:
  - NULL / missing fields (team, platform, publish_url)
  - "Unknown" values
  - Duplicate video_ids
  - Invalid publish URLs (published but no URL)
Also builds the DQScorecard (always-populated data for Data Governance tab).
"""

import logging
from collections import Counter
from intelligence.insight_narrator.schemas import (
    FlaggedMetric, DQScorecard, FieldCompleteness,
)
from intelligence.insight_narrator.data_loader import HydratedDataBundle

log = logging.getLogger("narrator.dq")

# Fields to check completeness for
DQ_FIELDS = [
    ("team_id", "team_name"),
    ("platform_id", "platform"),
    ("published_url", "published_url"),
    ("language_id", "language"),
    ("input_type_id", "input_type"),
    ("output_type_id", "output_type"),
]

# Threshold: flag if >10% of records have issues
ISSUE_THRESHOLD = 0.10


def check_data_quality(bundle: HydratedDataBundle) -> tuple[list[FlaggedMetric], DQScorecard]:
    """
    Returns:
      - signals: FlaggedMetric[] for fields with high missing rates
      - scorecard: DQScorecard (always populated)
    """
    signals: list[FlaggedMetric] = []
    total = len(bundle.fact_sample)

    if total == 0:
        return signals, DQScorecard(
            overall_score=100, total_rows=0, fields=[],
            duplicate_video_ids=0, invalid_publish_urls=0,
        )

    period = bundle.monthly_kpis[0].get("month", "") if bundle.monthly_kpis else ""

    # ── Field completeness ─────────────────────────────────────────────────
    fields: list[FieldCompleteness] = []
    field_scores: list[float] = []

    for col_name, display_name in DQ_FIELDS:
        null_count = 0
        unknown_count = 0

        for row in bundle.fact_sample:
            val = row.get(col_name)
            if val is None:
                null_count += 1
            elif isinstance(val, str) and val.lower() in ("unknown", "", "none", "null"):
                unknown_count += 1

        non_null = total - null_count
        pct_complete = round(non_null / total * 100, 1)
        field_scores.append(pct_complete)

        fields.append(FieldCompleteness(
            field_name=display_name,
            total_rows=total,
            non_null_count=non_null,
            null_count=null_count,
            pct_complete=pct_complete,
            unknown_count=unknown_count,
        ))

        # Flag if above threshold
        missing_pct = (null_count + unknown_count) / total
        if missing_pct >= ISSUE_THRESHOLD:
            signals.append(FlaggedMetric(
                entity_type="fleet",
                entity_id=f"dq_{col_name}",
                entity_label=f"Data Quality — {display_name}",
                metric_name=f"missing_{col_name}",
                current_value=round(missing_pct * 100, 1),
                reference_value=ISSUE_THRESHOLD * 100,
                delta_pct=round((missing_pct - ISSUE_THRESHOLD) / ISSUE_THRESHOLD * 100, 1),
                severity="high" if missing_pct >= 0.25 else "medium",
                period=period,
                insight_source="dq",
                suggested_action=(
                    f"{null_count + unknown_count} records ({missing_pct*100:.1f}%) have "
                    f"missing or unknown {display_name}. "
                    f"Prioritize data enrichment for this field."
                ),
            ))

    # ── Duplicate video IDs ────────────────────────────────────────────────
    video_ids = [r.get("video_id") for r in bundle.fact_sample if r.get("video_id")]
    id_counts = Counter(video_ids)
    duplicates = sum(1 for v in id_counts.values() if v > 1)

    if duplicates > 0:
        dup_pct = duplicates / max(len(video_ids), 1) * 100
        if dup_pct >= 1:
            signals.append(FlaggedMetric(
                entity_type="fleet",
                entity_id="dq_duplicates",
                entity_label="Data Quality — Duplicates",
                metric_name="duplicate_video_ids",
                current_value=duplicates,
                reference_value=0,
                delta_pct=100,
                severity="medium" if duplicates < 50 else "high",
                period=period,
                insight_source="dq",
                suggested_action=(
                    f"{duplicates} duplicate video IDs detected. "
                    f"Likely re-ingestion. Consider dedup in the data pipeline."
                ),
            ))

    # ── Invalid publish URLs ───────────────────────────────────────────────
    invalid_urls = 0
    for row in bundle.fact_sample:
        if row.get("published_flag") and not row.get("published_url"):
            invalid_urls += 1

    if invalid_urls > 0:
        inv_pct = invalid_urls / total * 100
        if inv_pct >= 5:
            signals.append(FlaggedMetric(
                entity_type="fleet",
                entity_id="dq_publish_url",
                entity_label="Data Quality — Publish URLs",
                metric_name="missing_publish_url",
                current_value=invalid_urls,
                reference_value=0,
                delta_pct=100,
                severity="medium",
                period=period,
                insight_source="dq",
                suggested_action=(
                    f"{invalid_urls} videos are marked published but have no publish URL. "
                    f"These may be false positives or missing metadata."
                ),
            ))

    # ── Build scorecard ────────────────────────────────────────────────────
    overall = round(sum(field_scores) / max(len(field_scores), 1), 0)
    # Penalize for duplicates and invalid URLs
    penalty = min(10, duplicates * 0.1 + invalid_urls * 0.05)
    overall = max(0, int(overall - penalty))

    scorecard = DQScorecard(
        overall_score=overall,
        total_rows=total,
        fields=fields,
        duplicate_video_ids=duplicates,
        invalid_publish_urls=invalid_urls,
    )

    log.info(f"[DQ] Score: {overall}/100, {len(signals)} issues flagged")
    return signals, scorecard
