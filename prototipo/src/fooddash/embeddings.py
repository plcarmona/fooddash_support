"""Recuperacion por embeddings para LOOCV-KNN.

Usa snowflake-arctic-embed2 (Ollama local, 1024 dims) para embeber tickets y
recuperar los k mas similares por cosine similarity. La recuperacion es
deterministica (los embeddings no varian entre corridas), lo que elimina una
fuente de varianza vs el LOOCV con few-shot generico.

Sin numpy: 26 vectores de 1024 dimensiones, Python puro es instantaneo.
"""

from __future__ import annotations

import math
import os

import httpx

OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "snowflake-arctic-embed2")


def embed_text(text: str, model: str = EMBED_MODEL) -> list[float]:
    """Embebe un texto via Ollama /api/embed."""
    r = httpx.post(
        f"{OLLAMA_BASE}/api/embed",
        json={"model": model, "input": text},
        timeout=30.0,
    )
    r.raise_for_status()
    data = r.json()
    return data["embeddings"][0]


def embed_ticket(ticket: dict) -> list[float]:
    """Embebe subject + body + system_logs de un ticket."""
    parts = [
        str(ticket.get("subject") or ""),
        str(ticket.get("body") or ""),
        str(ticket.get("system_logs") or ""),
    ]
    text = " \n ".join(p for p in parts if p.strip())
    if not text.strip():
        text = ticket.get("ticket_id", "empty")
    return embed_text(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity en Python puro."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_top_k(
    query_embedding: list[float],
    candidate_embeddings: dict[str, list[float]],
    k: int = 5,
) -> list[tuple[str, float]]:
    """Devuelve los top-k (ticket_id, similarity) ordenados por similitud desc."""
    scores = [
        (tid, cosine_similarity(query_embedding, emb))
        for tid, emb in candidate_embeddings.items()
    ]
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:k]
