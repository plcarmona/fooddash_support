"""Orquestador de agentes: Router (triaje) -> rama (Resolutor | Bug Triage).

Flujo por ticket:
  1. Router clasifica en bug | config | operacion | comercial | none.
  2. Si config/operacion/comercial -> Resolutor redacta respuesta + accion.
  3. Si bug -> Bug Triage (sistema + severidad) + kb_lookup (bugs conocidos).

Cada ticket se procesa de forma independiente (sin estado global). La
agregacion por causa raiz (agrupar tickets que matchean el mismo known_bug_id)
se hace despues, en el reporte, no durante el triaje individual.

Toda la I/O con el LLM pasa por LLMClient; aqui no hay logica de transporte.
"""

from __future__ import annotations

from .known_bugs import lookup_known_bug
from .llm import LLMClient
from .prompts import bug_triage_messages, resolutor_messages, router_messages


def triage_ticket(
    client: LLMClient,
    ticket: dict,
    *,
    router_only: bool = False,
) -> dict:
    """Procesa un ticket end-to-end y devuelve un dict con todo el resultado.

    Si router_only=True, solo ejecuta el Router (1 llamada LLM). Util para
    iterar prompts/modelos rapido; las ramas Resolutor/Bug-Triage se omiten.
    """
    tid = ticket["ticket_id"]

    # 1) Router ----------------------------------------------------------
    router_resp = client.chat(
        router_messages(ticket),
        json_mode=True,
        temperature=0.0,
    )
    router_json = router_resp.json() or _fallback_router(ticket)
    category = (router_json.get("category") or "none").lower().strip()
    confidence = _safe_float(router_json.get("confidence"), 0.5)
    reasoning = router_json.get("reasoning") or ""
    evidence = router_json.get("evidence") or ""
    system_id = router_json.get("system_id")

    result: dict = {
        "ticket_id": tid,
        "category": category,
        "confidence": confidence,
        "system_id": system_id,
        "reasoning": reasoning,
        "evidence": evidence,
        "model": f"{client.backend}/{client.model}",
    }

    # 2) Rama por categoria ---------------------------------------------
    if router_only:
        return result

    if category in ("config", "operacion", "comercial"):
        res = client.chat(
            resolutor_messages(ticket, category, reasoning),
            json_mode=True,
            temperature=0.2,
        )
        rj = res.json() or {}
        result["respuesta_usuario"] = rj.get("respuesta_usuario") or ""
        result["internal_action"] = rj.get("internal_action") or "escalar_a_soporte"
        result["requires_refund"] = bool(rj.get("requires_refund", False))

    elif category == "bug":
        bt = client.chat(
            bug_triage_messages(ticket, reasoning),
            json_mode=True,
            temperature=0.0,
        )
        bj = bt.json() or {}
        # el bug triage puede refinar el system_id
        if bj.get("system_id"):
            system_id = bj["system_id"]
            result["system_id"] = system_id
        result["severity"] = bj.get("severity") or "medium"
        result["root_cause_hypothesis"] = bj.get("root_cause_hypothesis") or ""
        result["next_steps"] = bj.get("next_steps") or ""
        # kb_lookup contra el registro de bugs conocidos
        known = lookup_known_bug(ticket, system_id_hint=system_id)
        result["known_bug"] = known.to_dict() if known else None
        result["is_new_bug"] = known is None  # bug no en la base -> alta prioridad

    elif category == "none":
        result["internal_action"] = "descartar"

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BUG_TOKENS = (
    "crash", "stacktrace", "error", "timeout", "idempotency", "failed",
    "exception", "js_error", "frontend_error", "unreachable",
)


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _fallback_router(ticket: dict) -> dict:
    """Si el LLM devuelve algo no-JSON, heuristica basica para no caer."""
    text = f"{ticket.get('subject','')} {ticket.get('body','')} {ticket.get('system_logs','')}".lower()
    if "test ignorar" in text or "asdf" in text:
        cat = "none"
    elif any(t in text for t in _BUG_TOKENS):
        cat = "bug"
    elif "blocked" in text:
        cat = "config"
    elif "renegociar" in text or "comision" in text:
        cat = "comercial"
    else:
        cat = "operacion"
    return {"category": cat, "confidence": 0.3, "reasoning": "fallback heuristico", "evidence": ""}
