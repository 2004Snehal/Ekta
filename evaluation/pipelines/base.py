"""
Shared EvalResult dataclass and Pipeline base class.
All pipeline wrappers return EvalResult; runners collect lists of them.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvalResult:
    question: str
    pipeline_name: str
    sql: Optional[str]          = None
    answer: str                 = ""
    rows: list                  = field(default_factory=list)
    latency_ms: float           = 0.0
    success: bool               = False
    error: Optional[str]        = None
    first_shot_success: bool    = False   # True if SQL ran without healing
    heal_attempts: int          = 0       # number of heal calls made
    gold_rows: Optional[list]   = None    # set by BIRD runner after gold SQL execution
    gold_exec_time_ms: float    = 0.0     # set by BIRD runner
    complexity: Optional[str]   = None    # simple/medium/complex (ours only)


class Pipeline:
    """Abstract pipeline wrapper. Subclasses implement run()."""
    name: str = "base"

    def run(
        self,
        question: str,
        conn,                    # DB connection (psycopg2 for ours, sqlite3 for BIRD)
        schema_str: str,
        client_id: int = 1,
    ) -> EvalResult:
        raise NotImplementedError
