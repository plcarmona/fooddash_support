"""Evaluacion del agente contra el golden set (clasificacion humana).

Metrica principal: agreement por categoria (accuracy). Tambien reporta
matriz de confusion compacta y la lista de desacuerdos para inspeccionar.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def load_golden() -> dict[str, dict]:
    data = json.loads((DATA_DIR / "golden.json").read_text())
    return data["labels"]


def evaluate(results: list[dict]) -> dict:
    golden = load_golden()
    by_id = {r["ticket_id"]: r for r in results}

    agree = 0
    total = 0
    disagreements: list[dict] = []
    labels = {"bug", "config", "operacion", "comercial", "none"}

    for tid, g in golden.items():
        if tid not in by_id:
            continue
        total += 1
        pred = (by_id[tid].get("category") or "").lower()
        gold = g["label"]
        if pred == gold:
            agree += 1
        else:
            disagreements.append(
                {
                    "ticket_id": tid,
                    "gold": gold,
                    "pred": pred,
                    "confidence": by_id[tid].get("confidence"),
                    "model_reasoning": by_id[tid].get("reasoning"),
                    "model_evidence": by_id[tid].get("evidence"),
                    "gold_reason": g["reason"],
                }
            )

    accuracy = agree / total if total else 0.0

    # matriz de confusion compacta gold -> pred
    confusion: dict[str, dict[str, int]] = {g: {p: 0 for p in labels} for g in labels}
    for tid, g in golden.items():
        if tid not in by_id:
            continue
        gold = g["label"]
        pred = (by_id[tid].get("category") or "").lower()
        if gold in confusion and pred in confusion[gold]:
            confusion[gold][pred] += 1

    # por-etiqueta recall
    per_label: dict[str, dict] = {}
    for lab in labels:
        tp = confusion[lab][lab]
        fn = sum(confusion[lab][p] for p in labels if p != lab)
        per_label[lab] = {"recall": tp / (tp + fn) if (tp + fn) else None, "tp": tp, "fn": fn}

    return {
        "model": results[0].get("model") if results else "?",
        "n": total,
        "agreement": agree,
        "accuracy": round(accuracy, 4),
        "per_label_recall": per_label,
        "confusion": confusion,
        "disagreements": disagreements,
    }
