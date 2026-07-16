"""Busqueda en el registro de bugs conocidos (tool kb_lookup del agente).

Dado un ticket clasificado como bug, busca coincidencias en data/known_bugs.json
por sistema + sintomas. Es deliberadamente simple y explicable (matching por
tokens), no embeddings: en un dataset de 26 tickets y 10 bugs conocidos, la
transparencia pesa mas que la sofisticacion.

Salida: el mejor match (si supera un umbral) o None (bug nuevo -> alta prioridad).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@dataclass
class BugMatch:
    bug_id: str
    title: str
    system: str
    status: str
    severity: str
    owner_team: str | None
    workaround: str | None
    fix_version: str | None
    score: float
    internal_link: str | None

    def to_dict(self) -> dict:
        return {
            "bug_id": self.bug_id,
            "title": self.title,
            "system": self.system,
            "status": self.status,
            "severity": self.severity,
            "owner_team": self.owner_team,
            "workaround": self.workaround,
            "fix_version": self.fix_version,
            "match_score": round(self.score, 3),
            "internal_link": self.internal_link,
        }


def _load_known_bugs() -> list[dict]:
    data = json.loads((DATA_DIR / "known_bugs.json").read_text())
    return data["bugs"]


def _load_systems() -> list[dict]:
    data = json.loads((DATA_DIR / "systems_catalog.json").read_text())
    return data["systems"]


def _tokenize(s: str) -> set[str]:
    """Tokeniza manteniendo tokens tecnicos (idempotency_key_reused, NaN, etc.)."""
    if not s:
        return set()
    return {t for t in re.split(r"[\s,;:\[\]\(\){}=]+", s.lower()) if len(t) > 1}


def _norm_sid(s: str) -> str:
    """Normaliza un system_id para comparacion (lowercase, guiones bajos)."""
    return (s or "").lower().strip().replace(" ", "_").replace("-", "_")


def map_system(system_id_hint: str | None, ticket_text: str) -> str | None:
    """Mapea un ticket a un sistema del catalogo usando aliases y signals.

    Si el agente ya propuso un system_id, lo respeta (con normalizacion); si
    no, heuristica por coincidencia de signals en el texto del ticket.
    """
    systems = _load_systems()
    if system_id_hint:
        hint = _norm_sid(system_id_hint)
        for s in systems:
            if _norm_sid(s["id"]) == hint:
                return s["id"]
    tokens = _tokenize(ticket_text)
    best, best_score = None, 0
    for s in systems:
        signals = [x.lower() for x in s.get("signals", []) + s.get("aliases", [])]
        score = sum(1 for sig in signals if _phrase_in(sig, tokens, ticket_text.lower()))
        if score > best_score:
            best, best_score = s["id"], score
    return best if best_score > 0 else None


def _phrase_in(phrase: str, tokens: set[str], raw_lower: str) -> bool:
    """Coincidencia de frase multi-word contra el texto crudo (no solo tokens)."""
    if " " in phrase or ">" in phrase or "<" in phrase or "_" in phrase and phrase not in tokens:
        return phrase in raw_lower
    return phrase in tokens


def lookup_known_bug(
    ticket: dict,
    *,
    system_id_hint: str | None = None,
    threshold: float = 1.5,
) -> BugMatch | None:
    """Busca el ticket en el registro de bugs conocidos.

    Score = (sistema coincide ? 2 : 0) + sum(sintoma presente)
    threshold ~1.5 => al menos el sistema o >=2 sintomas.
    """
    text_parts = [
        str(ticket.get("subject") or ""),
        str(ticket.get("body") or ""),
        str(ticket.get("system_logs") or ""),
    ]
    ticket_text = " \n ".join(text_parts)
    raw_lower = ticket_text.lower()
    tokens = _tokenize(ticket_text)

    sys_hint = map_system(system_id_hint, ticket_text)

    bugs = _load_known_bugs()
    best_match: BugMatch | None = None
    best_score = 0.0
    for b in bugs:
        score = 0.0
        if sys_hint and b.get("system") == sys_hint:
            score += 2.0
        for sym in b.get("symptoms", []):
            sym_l = sym.lower()
            if " " in sym_l or sym_l in raw_lower:
                if sym_l in raw_lower:
                    score += 1.0
            elif sym_l in tokens:
                score += 1.0
        if score > best_score:
            best_score = score
            best_match = BugMatch(
                bug_id=b["id"],
                title=b["title"],
                system=b["system"],
                status=b["status"],
                severity=b["severity"],
                owner_team=b.get("owner_team"),
                workaround=b.get("workaround"),
                fix_version=b.get("fix_version"),
                score=score,
                internal_link=b.get("internal_link"),
            )
    if best_match and best_score >= threshold:
        return best_match
    return None
