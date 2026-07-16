"""Cross-validation (LOOCV) con prompt minimo para estimar generalizacion honesta.

El problema: el prompt actual (ROUTER_SYSTEM + FEW_SHOT) fue afinado mirando los
26 tickets del set. Las 8 "reglas decisionales" y los 9 ejemplos pocos-shot son
derivados de tickets especificos. Reportar 100% de accuracy sobre el mismo set
que se uso para disenar el prompt es sobreajuste (test-set leakage).

Solucion: leave-one-out (LOOCV). Por cada ticket T:
  1. Se separa T (test).
  2. Los otros 25 tickets (con etiquetas golden) son el training set.
  3. Los pocos-shot se seleccionan de tickets REALES del training set
     (no analogos sinteticos de T).
  4. Se usa un prompt MINIMO: solo definiciones de categoria + "lee logs
     antes que subject". Sin las 8 reglas especificas.
  5. Se clasifica T y se registra correcto/incorrecto.

La accuracy LOOCV es la estimacion honesta de generalizacion. La diferencia
entre known-set (100%) y LOOCV (??) revela cuanto depende el resultado de las
reglas hand-craftadas vs de la capacidad del modelo de aprender del criterio.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Iterator, NamedTuple

from .embeddings import embed_ticket, retrieve_top_k

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# ---------------------------------------------------------------------------
# Prompt minimo: definiciones de categoria + principio general, SIN reglas
# especificas derivadas de tickets concretos.
# ---------------------------------------------------------------------------

MINIMAL_ROUTER_SYSTEM = """\
Eres un agente de triaje de tickets de soporte para FoodDash (app de delivery \
en Chile). Recibes UN ticket y debes clasificarlo en EXACTAMENTE una categoria.

PRINCIPIO: Lee SIEMPRE system_logs ANTES de mirar el subject/body. Los logs son \
la verdad tecnica; el relato del usuario puede ser impreciso. Si hay tokens \
tecnicos en system_logs, pesan mas que el subject.

== Categorias ==

- BUG: hay evidencia tecnica en system_logs de que la plataforma llego a un \
estado ERRONEO o INCONSISTENTE, o ACEPTO un dato que no debia. Incluye \
crash, stacktrace, ERROR, timeout, fallo de proveedor externo, degradacion \
de rendimiento, o que el sistema permitiera un estado invalido sin validar. \
Tambien es BUG la sospecha fundada de fallo de plataforma (ej. "me cobraron \
dos veces") aunque no haya logs. El defecto es de la plataforma.

- CONFIGURACION: los logs muestran que el sistema actuo CONFORME A SU \
CONFIGURACION, pero esa config esta mal para el caso. Marcas tipicas: \
result=BLOCKED por una policy, o un parametro que causo el problema (minimo \
de pedido, estado de borrador, horario/override, cupon vencido, ajustes de \
notificacion del dispositivo). El fix es cambiar la regla/parametro, no \
arreglar codigo.

- OPERACION: el flujo corrio sin BLOCKED ni estado inconsistente; el \
resultado fue deficiente por el mundo fisico/humano: saturacion de zona, \
error humano del restaurante o repartidor, o timing de un proceso batch.

- COMERCIAL: consulta puramente comercial o de politica (renegociar \
comision, pedir contacto). No es un fallo del sistema.

- NONE: ticket de prueba, spam, vacio o sin contenido accionable.

Devuelve SOLO JSON, sin prosa, con esta forma exacta:
{
  "category": "bug|config|operacion|comercial|none",
  "confidence": 0.0,
  "system_id": "id del sistema (bug) o null",
  "reasoning": "una frase: por que esta categoria y no otra",
  "evidence": "token/frase del log o cuerpo que te hizo decidir"
}
"""


# ---------------------------------------------------------------------------
# Carga de golden labels
# ---------------------------------------------------------------------------

def load_golden() -> dict[str, dict]:
    data = json.loads((DATA_DIR / "golden.json").read_text())
    return data["labels"]


# ---------------------------------------------------------------------------
# Leave-one-out
# ---------------------------------------------------------------------------

def leave_one_out(tickets: list[dict]) -> Iterator[tuple[list[dict], dict]]:
    """Genera (train_tickets, test_ticket) para cada uno de los N tickets."""
    for i, test in enumerate(tickets):
        train = tickets[:i] + tickets[i + 1 :]
        yield train, test


# ---------------------------------------------------------------------------
# Leave-one-out con recuperacion por embeddings (KNN)
# ---------------------------------------------------------------------------

def embed_all_tickets(tickets: list[dict]) -> dict[str, list[float]]:
    """Pre-computa embeddings para todos los tickets. Retorna {ticket_id: vector}."""
    embeddings: dict[str, list[float]] = {}
    for t in tickets:
        embeddings[t["ticket_id"]] = embed_ticket(t)
    return embeddings


def leave_one_out_knn(
    tickets: list[dict],
    golden: dict[str, dict],
    embeddings: dict[str, list[float]],
    k: int = 5,
) -> Iterator[tuple[dict, list[dict], list[dict]]]:
    """LOOCV con recuperacion deterministica por embeddings.

    Para cada ticket T:
      1. Calcula cosine similarity contra los otros 25.
      2. Recupera los top-k mas parecidos.
      3. Convierte esos k en few-shot (con golden labels).
      4. Yields (test_ticket, few_shot, retrieved_info).

    La recuperacion es deterministica (embeddings fijos). Solo el paso de
    prediccion del LLM tiene varianza.
    """
    by_id = {t["ticket_id"]: t for t in tickets}

    for test in tickets:
        tid = test["ticket_id"]
        # candidatos: todos excepto el test
        candidates = {cid: emb for cid, emb in embeddings.items() if cid != tid}
        top_k = retrieve_top_k(embeddings[tid], candidates, k=k)

        # construir few-shot desde los top-k
        few_shot: list[dict] = []
        retrieved_info: list[dict] = []
        for cid, sim in top_k:
            train_ticket = by_id[cid]
            g = golden.get(cid)
            if not g:
                continue
            few_shot.append(_format_few_shot_item(train_ticket, g))
            retrieved_info.append(
                {"ticket_id": cid, "label": g["label"], "similarity": round(sim, 4)}
            )

        yield test, few_shot, retrieved_info


# ---------------------------------------------------------------------------
# Seleccion de pocos-shot desde tickets reales del training set
# ---------------------------------------------------------------------------

def _has_clear_signal(ticket: dict) -> bool:
    """True si el ticket tiene system_logs con contenido tecnico instructivo."""
    logs = ticket.get("system_logs") or ""
    return len(logs) > 20


def select_few_shot(
    train_tickets: list[dict],
    golden: dict[str, dict],
    n_per_cat: int = 2,
) -> list[dict]:
    """Selecciona pocos-shot balanceados de tickets reales del training set.

    Estrategia:
    - Agrupa por etiqueta golden.
    - Por categoria, toma hasta n_per_cat tickets que tengan system_logs claros
      (mas instructivos para el modelo).
    - Dentro de bug, prioriza diversidad de system_id (no dos crash si hay
      tambien un bug de pago disponible).
    - Formato de salida: mismo que prompts.FEW_SHOT ({ticket, output}).
    """
    by_label: dict[str, list[dict]] = defaultdict(list)
    for t in train_tickets:
        tid = t["ticket_id"]
        g = golden.get(tid)
        if not g:
            continue
        by_label[g["label"]].append(t)

    few_shot: list[dict] = []
    for label in ["bug", "config", "operacion", "comercial", "none"]:
        candidates = by_label.get(label, [])
        # prioriza tickets con logs claros
        with_logs = [t for t in candidates if _has_clear_signal(t)]
        without_logs = [t for t in candidates if not _has_clear_signal(t)]
        ordered = with_logs + without_logs

        if label == "bug":
            # diversidad: no repetir el mismo system_id si hay alternativas
            seen_systems: set[str] = set()
            diverse: list[dict] = []
            for t in ordered:
                g = golden[t["ticket_id"]]
                # heuristica: el system_id lo inferimos del reasoning del golden
                sid = _infer_system_id(t)
                if sid not in seen_systems or len(diverse) < 1:
                    diverse.append(t)
                    seen_systems.add(sid)
                if len(diverse) >= n_per_cat:
                    break
            ordered = diverse[:n_per_cat]

        for t in ordered[:n_per_cat]:
            g = golden[t["ticket_id"]]
            few_shot.append(_format_few_shot_item(t, g))

    return few_shot


def _infer_system_id(ticket: dict) -> str:
    """Heuristica simple para inferir el system_id de un ticket (para diversidad)."""
    text = f"{ticket.get('subject','')} {ticket.get('body','')} {ticket.get('system_logs','')}".lower()
    if "cart" in text or "carrito" in text:
        return "customer_app_mobile"
    if "payment" in text or "cobro" in text or "idempotency" in text:
        return "payment_service"
    if "courier" in text or "repartidor" in text or "gap_s" in text:
        return "courier_app"
    if "delivery" in text or "entregado" in text or "distance_m" in text:
        return "delivery"
    if "geocode" in text or "direccion" in text:
        return "geocoding"
    if "tz_config" in text or "availability" in text or "cerrados" in text:
        return "availability"
    if "sms" in text or "otp" in text:
        return "sms_otp"
    if "api_gateway" in text or "latencia" in text or "lent" in text:
        return "api_gateway"
    if "inventory" in text or "order_create" in text:
        return "inventory"
    if "frontend" in text or "js_error" in text or "blanco" in text:
        return "frontend_web"
    if "coupon" in text or "cupon" in text:
        return "coupon"
    return "other"


def _format_few_shot_item(ticket: dict, golden_entry: dict) -> dict:
    """Formatea un ticket real + su etiqueta golden como item pocos-shot."""
    keep = {
        "ticket_id": ticket.get("ticket_id"),
        "reporter_type": ticket.get("reporter_type"),
        "order_id": ticket.get("order_id"),
        "subject": ticket.get("subject"),
        "body": ticket.get("body"),
        "system_logs": ticket.get("system_logs"),
    }
    keep = {k: v for k, v in keep.items() if v is not None}
    return {
        "ticket": keep,
        "output": {
            "category": golden_entry["label"],
            "confidence": 0.9,
            "system_id": _infer_system_id(ticket) if golden_entry["label"] == "bug" else None,
            "reasoning": golden_entry["reason"],
            "evidence": (ticket.get("system_logs") or ticket.get("body") or "")[:80],
        },
    }


# ---------------------------------------------------------------------------
# Hibrido: reglas justificadas por el training set (cv-hybrid)
# ---------------------------------------------------------------------------
#
# Idea: el prompt de produccion (ROUTER_SYSTEM) codifica 8 reglas decisionales
# derivadas de tickets especificos. Reportar 100% sobre el mismo set que sirvio
# para derivarlas es sobreajuste. El LOOCV-KNN (84.6%) usa un prompt MINIMAL
# sin reglas. El hibrido es el punto medio: por cada fold LOOCV, incluye en el
# prompt SOLO las reglas que el training set (los otros 25 tickets) logra trazar
# (misma etiqueta golden + keyword de la regla presente). Las reglas que solo se
# sostenian con el ticket held-out se dropean -> se elimina el leakage sin
# tirar todas las reglas por igual.
#
# Las 8 reglas y su texto son verbatim de prompts.py (seccion REGLAS DECISORAS);
# los keywords son la firma con la que se traza cada regla en los tickets.

class RuleDef(NamedTuple):
    id: str
    category: str               # categoria gold cuando la regla dispara
    keywords: tuple[str, ...]   # tokens cuya presencia (en ticket de esa categoria) traza la regla
    text: str                   # linea verbatim de prompts.py para el prompt


RULE_DEFINITIONS: list[RuleDef] = [
    RuleDef(
        "R1", "bug",
        ("crash", "stacktrace", "nullpointer", "error", "timeout", "idempotency",
         "p95", "carrier_unreachable", "all_failed", "frontend_error", "js_error", "gap_s"),
        "1. crash | stacktrace | NullPointerException | ERROR | timeout | "
        "idempotency_key_reused | p95_latency_ms | carrier_unreachable | all_failed | "
        "frontend_error | js_error | tz_config=UTC | gap_s => BUG.",
    ),
    RuleDef(
        "R2", "bug",
        ("tz_config", "availability_service", "open_restaurants=0"),
        '2. "todos los restaurantes cerrados" + tz_config o availability_service => '
        "BUG MASIVO (no es none).",
    ),
    RuleDef(
        "R3", "bug",
        ("distance_m", "geocode", "confidence"),
        "3. status=DELIVERED con distance_m>200, o geocode confidence<0.6 usado por "
        "la app => BUG (validacion ausente).",
    ),
    RuleDef(
        "R4", "bug",
        ("cobraron dos veces", "doble cobro", "cobro raro", "sospecha"),
        '4. "cobro raro" | "me cobraron dos veces" | doble cobro (con o sin logs) '
        "=> BUG (sospecha fundada de fallo de Payment Service, investigar).",
    ),
    RuleDef(
        "R5", "config",
        ("blocked", "unpublished", "holiday_hours", "valid_until", "expired",
         "notification_sound", "do_not_disturb", "restaurant_min", "draft_state"),
        "5. result=BLOCKED reason=<policy> o parametro mal seteado "
        "(notification_sound=OFF, draft_state=UNPUBLISHED, holiday_hours_enabled, "
        "valid_until expired, restaurant_min alto) => CONFIGURACION.",
    ),
    RuleDef(
        "R6", "operacion",
        ("saturacion", "zone_active_couriers", "falto", "item", "equivocado",
         "batch", "cutoff", "included_in_batch"),
        "6. Pedido tardio/frio, falto un item, courier se equivoco en batch, "
        "included_in_batch=FALSE / delivered_after_cutoff => OPERACION.",
    ),
    RuleDef(
        "R7", "comercial",
        ("comision", "renegociar", "comercial"),
        '7. "renegociar comision" | "con quien hablo" (comercial puro) => COMERCIAL.',
    ),
    RuleDef(
        "R8", "none",
        ("asdf", "test ignorar"),
        '8. "test ignorar" | "asdf" => NONE.',
    ),
]


# Tickets propensos a fallar (focus del cv-hybrid --failing-only):
# los 4 divergentes de la bitacora (de donde nacieron las reglas R3 y R5) +
# los errores residuales del LOOCV-KNN.
FAILING_PRONE: list[str] = [
    "TCK-1002",  # GPS 780m -> bug (divergencia bitacora, R3)
    "TCK-1007",  # BLOCKED policy -> config (divergencia bitacora, R5)
    "TCK-1012",  # geocode 0.31 -> bug (divergencia bitacora, R3)
    "TCK-1025",  # no_cancel_after_cooking -> config (divergencia bitacora, R5)
    "TCK-1010",  # cupon expired -> config (error KNN)
    "TCK-1023",  # cutoff -> operacion (error KNN, limite config/operacion)
    "TCK-1024",  # tz_config=UTC -> bug masivo (error KNN, R2 unica)
]


def _ticket_blob(ticket: dict, golden_entry: dict) -> str:
    """Texto lowercase sobre el que se traza la presencia de keywords de una regla."""
    parts = [
        str(ticket.get("subject") or ""),
        str(ticket.get("body") or ""),
        str(ticket.get("system_logs") or ""),
        golden_entry.get("reason") or "",
    ]
    return " ".join(parts).lower()


def trace_rule(
    rule: RuleDef, train_tickets: list[dict], golden: dict[str, dict]
) -> list[str]:
    """Tickets del training set que TRAZAN la regla.

    Un ticket traza la regla si su etiqueta golden coincide con la categoria
    objetivo de la regla Y algun keyword de la regla aparece en
    subject+body+system_logs+razon golden.
    """
    traced: list[str] = []
    for t in train_tickets:
        tid = t["ticket_id"]
        g = golden.get(tid)
        if not g or g["label"] != rule.category:
            continue
        blob = _ticket_blob(t, g)
        if any(kw.lower() in blob for kw in rule.keywords):
            traced.append(tid)
    return traced


def build_justified_rules(
    train_tickets: list[dict], golden: dict[str, dict]
) -> tuple[list[RuleDef], list[RuleDef]]:
    """Separa las 8 reglas en (justificadas, dropeadas) para un fold LOOCV.

    Una regla es justificada si >=1 ticket del training set la traza. Las
    dropeadas son las que solo se sostenian con el ticket held-out (leakage).
    """
    justified: list[RuleDef] = []
    dropped: list[RuleDef] = []
    for rule in RULE_DEFINITIONS:
        if trace_rule(rule, train_tickets, golden):
            justified.append(rule)
        else:
            dropped.append(rule)
    return justified, dropped


def build_hybrid_system(justified: list[RuleDef]) -> str:
    """Prompt hibrido: minimal (defs de categoria) + solo las reglas justificadas."""
    if not justified:
        return MINIMAL_ROUTER_SYSTEM
    rules_block = "\n".join(r.text for r in justified)
    return (
        MINIMAL_ROUTER_SYSTEM
        + "\n\n== REGLAS DECISORAS (derivadas del training set) ==\n"
        + rules_block
    )
