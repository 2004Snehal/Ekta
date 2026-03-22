"""
BIRD-specific RAG: few-shot retrieval from gold Q->SQL examples.

Creates a separate ChromaDB (evaluation/bird_chroma/) that holds BIRD gold examples.
Retrieval uses leave-one-out: the test question's exact gold pair is excluded.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_CHROMA_PATH = str(Path(__file__).parent / "bird_chroma")
_bird_db = None


def _get_db():
    global _bird_db
    if _bird_db is None:
        import chromadb
        from chromadb.config import Settings
        from chromadb.utils import embedding_functions

        ef = embedding_functions.DefaultEmbeddingFunction()
        client = chromadb.PersistentClient(
            path=_CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        _bird_db = {
            "client": client,
            "ef": ef,
            "sql": client.get_or_create_collection(name="bird_sql", embedding_function=ef),
        }
    return _bird_db


def _det_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def train_bird_rag(records: list[dict]) -> None:
    """
    Ingest BIRD gold (question, gold_sql) pairs into bird_chroma.
    Idempotent — skips duplicates via deterministic IDs.
    """
    db = _get_db()
    col = db["sql"]

    added = 0
    for r in records:
        doc = json.dumps({"question": r["question"], "sql": r["gold_sql"]}, ensure_ascii=False)
        uid = _det_id(doc)
        try:
            col.add(documents=[doc], ids=[uid])
            added += 1
        except Exception:
            pass  # already exists

    total = col.count()
    print(f"[bird_rag] Trained: {added} new, {total} total examples in bird_chroma.")


def retrieve_bird_examples(question: str, n: int = 3) -> list[dict]:
    """
    Retrieve top-n similar gold Q->SQL examples.
    Excludes exact question match (leave-one-out for fair eval).
    """
    db = _get_db()
    col = db["sql"]

    if col.count() == 0:
        return []

    # Retrieve n+2 to allow filtering out exact match
    results = col.query(
        query_texts=[question],
        n_results=min(n + 2, col.count()),
    )

    examples = []
    for doc_str in results.get("documents", [[]])[0]:
        try:
            ex = json.loads(doc_str)
        except Exception:
            continue
        # Leave-one-out: skip if question is identical
        if ex["question"].strip().lower() == question.strip().lower():
            continue
        examples.append(ex)
        if len(examples) >= n:
            break

    return examples
