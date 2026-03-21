import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))

from intelligence.recommendation.models import DashboardContext
from intelligence.recommendation.engine import build_recommendation_prompt, _format_context
from intelligence.recommendation.context_expander import expand_context
from intelligence.nlq.llm import call_llm_text
from database.connection import SessionLocal

ctx = DashboardContext(
    client_id=1,
    view="executive_summary",
    entity_type="network",
    entity_name="All Channels",
    user_role="operations",
    metric_in_focus="publish_rate_pct"
)

db = SessionLocal()
expanded = expand_context(ctx, db)
prompt = build_recommendation_prompt(ctx)
msg = _format_context(expanded)

prompt_chars = len(prompt)
msg_chars = len(msg)
total_words = len((prompt + msg).split())

print(f"=== PROMPT SIZE ===")
print(f"System Prompt Chars: {prompt_chars}")
print(f"User Message Chars: {msg_chars}")
print(f"Total Words (approx tokens): {total_words}")
print(f"Rough Token Count: {total_words * 1.3:.0f}")

try:
    res = call_llm_text(msg, system=prompt)
    print("=== LLM RAW ===")
    print(repr(res))
except Exception as e:
    print("=== LLM ERROR ===")
    import traceback
    traceback.print_exc()
