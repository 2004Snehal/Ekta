"""
Centralized logging configuration for the NLQ analytics backend.
All modules import `logger` from here to ensure consistent formatting.
"""

import logging
import sys
from typing import Optional


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Returns a configured logger instance.
    Uses the root 'nlq' logger so all child loggers share the same handlers.
    """
    log = logging.getLogger(name or "nlq")

    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False

    return log


# Module-level convenience logger used by most services
logger = get_logger("nlq")
