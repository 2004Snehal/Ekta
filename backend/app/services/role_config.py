"""
Role-based personalization configuration.

Defines how each user persona affects SQL generation focus,
answer tone, and LIDA insight framing.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RoleConfig:
    key: str
    display_name: str
    sql_focus: str          # Appended to Vanna prompt to bias SQL generation
    answer_persona: str     # System prompt for LLM answer generation
    lida_context: str       # Context injected into LIDA goal generation
    suggested_questions: list[str]


ROLE_CONFIGS: dict[str, RoleConfig] = {
    "founder": RoleConfig(
        key="founder",
        display_name="Founder / CEO",
        sql_focus=(
            "Prioritise high-level business metrics: overall publish rates, month-over-month "
            "growth trends, top-performing channels and clients, revenue-relevant output volumes, "
            "and company-wide KPI comparisons."
        ),
        answer_persona=(
            "You are a data analyst presenting findings to a company founder or CEO. "
            "Lead with the single most important business insight. Focus on growth, efficiency, "
            "and strategic implications. Use percentages and comparisons. Keep it under 4 sentences."
        ),
        lida_context=(
            "Generate insights relevant to a founder: business growth trends, overall publish rates, "
            "top-performing channels, and month-over-month performance comparisons."
        ),
        suggested_questions=[
            "What is our overall publish rate this month?",
            "Show month-over-month growth in published videos",
            "Which channel is performing best?",
            "Top 5 clients by output volume",
        ],
    ),

    "client_success": RoleConfig(
        key="client_success",
        display_name="Client Success",
        sql_focus=(
            "Focus on per-client delivery metrics: videos created and published per client, "
            "time-to-publish, client-level publish rates, delivery backlogs, and SLA indicators. "
            "Always segment results by client where possible."
        ),
        answer_persona=(
            "You are a data analyst supporting a client success team. "
            "Frame insights around client health and delivery performance. "
            "Flag any clients with low publish rates or delivery delays. "
            "Be action-oriented — what should the team follow up on?"
        ),
        lida_context=(
            "Generate insights relevant to client success: per-client delivery rates, "
            "publish performance by client, and clients that may need attention."
        ),
        suggested_questions=[
            "Which clients have the lowest publish rate?",
            "Show published vs created videos per client",
            "Which clients have the most unpublished videos?",
            "Average time to publish by client",
        ],
    ),

    "operations": RoleConfig(
        key="operations",
        display_name="Operations Team",
        sql_focus=(
            "Focus on operational efficiency: throughput volumes, upload-to-publish duration, "
            "team output rates, workflow bottlenecks, processing performance, and quality issues. "
            "Highlight where work is accumulating or delayed."
        ),
        answer_persona=(
            "You are a data analyst supporting an operations team. "
            "Focus on efficiency, throughput, and identifying bottlenecks. "
            "Highlight process metrics and operational KPIs. "
            "Be specific about volumes, timings, and where improvements can be made."
        ),
        lida_context=(
            "Generate insights relevant to operations: workflow throughput, upload durations, "
            "team output rates, processing efficiency, and bottleneck indicators."
        ),
        suggested_questions=[
            "What is the average upload duration by channel?",
            "Show total uploaded hours by team",
            "Which content type takes longest to publish?",
            "Daily upload volume trend this month",
        ],
    ),

    "editorial": RoleConfig(
        key="editorial",
        display_name="Editorial / Production",
        sql_focus=(
            "Focus on content metrics: output breakdown by language, channel, content type, "
            "and output type. Highlight team contributions, publish success rates by content category, "
            "and editorial performance patterns."
        ),
        answer_persona=(
            "You are a data analyst supporting an editorial and production team. "
            "Frame insights around content performance, language and format breakdowns, "
            "and team productivity. Highlight which content types or languages perform best "
            "and where editorial focus should be directed."
        ),
        lida_context=(
            "Generate insights relevant to editorial/production: content type distribution, "
            "language performance, channel output, team contributions, and publish success by format."
        ),
        suggested_questions=[
            "Show created vs published videos by language",
            "Which content type has the highest publish rate?",
            "Top 10 users by output count",
            "Compare publish rate across channels",
        ],
    ),

    "tech": RoleConfig(
        key="tech",
        display_name="Tech / Product",
        sql_focus=(
            "Focus on technical and system metrics: query logs, data quality issues, "
            "processing performance indicators, usage patterns, system health signals, "
            "and anomalies in the data pipeline."
        ),
        answer_persona=(
            "You are a data analyst supporting a tech and product team. "
            "Be precise with numbers. Focus on system performance, data quality, "
            "usage patterns, and technical KPIs. Flag any anomalies or data inconsistencies. "
            "Use technical language where appropriate."
        ),
        lida_context=(
            "Generate insights relevant to tech/product: system usage patterns, "
            "data quality distributions, processing performance, and technical anomalies."
        ),
        suggested_questions=[
            "Show data quality issue counts by type",
            "Monthly trend of uploads over the last 6 months",
            "Which channels have missing language data?",
            "Show billable vs non-billable video distribution",
        ],
    ),
}


def get_role_config(user_role: Optional[str]) -> Optional[RoleConfig]:
    """Return RoleConfig for a given role key, or None if not found / not set."""
    if not user_role:
        return None
    return ROLE_CONFIGS.get(user_role.lower())


def get_all_roles() -> list[dict]:
    """Return a list of all roles with key and display_name for the frontend."""
    return [
        {"key": rc.key, "display_name": rc.display_name, "suggested_questions": rc.suggested_questions}
        for rc in ROLE_CONFIGS.values()
    ]
