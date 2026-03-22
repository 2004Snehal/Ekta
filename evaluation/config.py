"""Central config for evaluation service."""
import os
from pathlib import Path

EVAL_ROOT    = Path(__file__).parent
BACKEND_ROOT = EVAL_ROOT.parent / "backend"

# API (for own-query runner — calls the live backend)
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
NLQ_ENDPOINT    = f"{BACKEND_API_URL}/nlq/query"
DEFAULT_CLIENT_ID = int(os.getenv("EVAL_CLIENT_ID", "1"))

# BIRD dataset paths
BIRD_DB_ROOT  = EVAL_ROOT / "datasets" / "bird_dbs"   # SQLite .db files downloaded here
BIRD_SPLIT    = "dev"                                   # or "train"

# Own queries
OWN_QUERIES_PATH = EVAL_ROOT / "datasets" / "own_queries.txt"

# LLM — same provider as backend (OpenRouter)
LLM_API_KEY  = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = "https://openrouter.ai/api/v1"
SQL_MODEL    = "qwen/qwen3-coder-next"
ANSWER_MODEL = "qwen/qwen3-coder-next"
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS  = 4096

# Metricflow branch name (for dynamic code extraction)
METRICFLOW_BRANCH = "rishit_sql_rag_metricflow"

# Concurrency
MAX_WORKERS = int(os.getenv("EVAL_MAX_WORKERS", "4"))
