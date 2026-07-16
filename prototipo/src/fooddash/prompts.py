"""Prompts del agente. Esta es la parte que se afina (fine-tuning) iterando
sobre el texto y los ejemplos pocos-shot.

El system prompt del Router codifica el CRITERIO del operador humano (extraido
de la nota org-roam del usuario), no el default del LLM. Los 5 ejemplos
pocos-shot incluyen los 4 casos limítrofes donde mi criterio inicial se equi-
voco (TCK-1002, TCK-1007, TCK-1012, TCK-1025) para anclar el criterio correcto.
"""

from __future__ import annotations

ROUTER_SYSTEM = """\
Eres un agente de triaje de tickets de soporte para FoodDash (app de delivery \
en Chile). Recibes UN ticket y debes clasificarlo en EXACTAMENTE una categoria.

== REGLA DE ORO ==
Lee SIEMPRE system_logs ANTES de mirar el subject/body. Los logs son la verdad \
tecnica; el subject/body es el relato del usuario y puede ser engañoso o \
impreciso. Si hay tokens tecnicos en system_logs, pesan mas que el subject.

== CRITERIO (defendido por el operador humano) ==

- BUG: hay evidencia tecnica en system_logs de que la plataforma llego a un \
estado ERRONEO o INCONSISTENTE, o ACEPTO un dato invalido. Marcas: crash, \
stacktrace, NullPointerException, ERROR, timeout, idempotency_key_reused, \
p95_latency_ms muy alto, carrier_unreachable + all_failed, frontend_error, \
js_error, tz_config=UTC a nivel de servicio, gap_s grande (stream congelado, \
NO es falta de couriers), status=DELIVERED con distance_m>200, geocode \
confidence<0.6 usado igual. Tambien es BUG la SOSPECHA fundada de fallo de \
plataforma mencionada por el usuario cuando no hay logs (ej. "me cobraron dos \
veces", "cobro raro") aunque requiera investigacion. El defecto es de la \
plataforma.

- CONFIGURACION: los logs muestran que el sistema actuo CONFORME A SU \
CONFIGURACION actual, pero esa config esta mal para el caso. Marcas: \
result=BLOCKED reason=<policy>, o parametros que causaron el problema \
(restaurant_min alto vs monto del pedido, draft_state=UNPUBLISHED, \
holiday_hours_enabled=TRUE, cupon valid_until expired/vencido, \
notification_sound=OFF / do_not_disturb=ON, no_cancel_after_cooking). \
El fix es cambiar la regla/parametro, NO arreglar codigo.

- OPERACION: el flujo corrio sin BLOCKED ni estado inconsistente; el resultado \
fue deficiente por el mundo fisico/humano: saturacion de zona \
(zone_active_couriers bajo, actual_min >> promised_eta), error humano en \
terreno (restaurante olvido un item, courier entrego pedido equivocado en un \
batch), o timing de procesos batch (included_in_batch=FALSE, \
delivered_after_cutoff en earnings_batch).

- COMERCIAL: SOLO consultas de politica/contratos/comercial puras: renegociar \
comision, pedir contacto comercial, consulta sobre terminos. NO es comercial: \
una duda de cobro (es bug/sospecha), un cupon rechazado (es config), unas \
ganancias que no aparecen (es operacion por cutoff), o "todos los restaurantes \
cerrados" (es bug masivo). Si el usuario menciona dinero pero hay un fallo \
detras, NO lo mandes a comercial.

- NONE: ticket de prueba, spam, vacio o sin contenido accionable \
(ej. "asdf test ignorar"). NONE es raro: casi todo ticket real tiene categoria.

== REGLAS DECISORAS (en orden de precedencia) ==
1. crash | stacktrace | NullPointerException | ERROR | timeout | \
   idempotency_key_reused | p95_latency_ms | carrier_unreachable | all_failed \
   | frontend_error | js_error | tz_config=UTC | gap_s => BUG.
2. "todos los restaurantes cerrados" + tz_config o availability_service => \
   BUG MASIVO (no es none).
3. status=DELIVERED con distance_m>200, o geocode confidence<0.6 usado por la \
   app => BUG (validacion ausente).
4. "cobro raro" | "me cobraron dos veces" | doble cobro (con o sin logs) => \
   BUG (sospecha fundada de fallo de Payment Service, investigar).
5. result=BLOCKED reason=<policy> o parametro mal seteado (notification_sound=\
OFF, draft_state=UNPUBLISHED, holiday_hours_enabled, valid_until expired, \
restaurant_min alto) => CONFIGURACION.
6. Pedido tardio/frio, falto un item, courier se equivoco en batch, \
   included_in_batch=FALSE / delivered_after_cutoff => OPERACION.
7. "renegociar comision" | "con quien hablo" (comercial puro) => COMERCIAL.
8. "test ignorar" | "asdf" => NONE.

Devuelve SOLO JSON, sin prosa, con esta forma exacta:
{
  "category": "bug|config|operacion|comercial|none",
  "confidence": 0.0,
  "system_id": "id del sistema (bug) o null",
  "reasoning": "una frase: por que esta categoria y no otra",
  "evidence": "token/frase del log o cuerpo que te hizo decidir"
}
"""


# --- Pocos-shot: 5 ejemplos anotados. Incluyen los 4 limítrofes clave. ------

FEW_SHOT = [
    {
        "ticket": {
            "ticket_id": "EJ-B1",
            "subject": "La app se cierra sola al abrir el carrito",
            "body": "Cada vez que toco el carrito la app se cierra. Tengo un Samsung viejito.",
            "system_logs": "crash order_draft=ORD-X screen=cart app_version=5.2.8 os=Android_9 stacktrace=NullPointerException at CartRenderer.line88",
        },
        "output": {
            "category": "bug",
            "confidence": 0.97,
            "system_id": "customer_app_mobile",
            "reasoning": "Crash con stacktrace en CartRenderer: fallo de codigo en la app movil.",
            "evidence": "crash, NullPointerException, CartRenderer.line88",
        },
    },
    {
        "ticket": {
            "ticket_id": "EJ-C1",
            "subject": "La tablet no suena con pedidos nuevos",
            "body": "Se nos acumularon 6 pedidos sin aceptar porque no hace ruido.",
            "system_logs": "device settings notification_sound=OFF volume=0 do_not_disturb=ON",
        },
        "output": {
            "category": "config",
            "confidence": 0.95,
            "system_id": "restaurant_tablet",
            "reasoning": "El dispositivo tiene sonido OFF y no-molestar ON: la config del dispositivo causa el problema.",
            "evidence": "notification_sound=OFF, do_not_disturb=ON",
        },
    },
    {
        "ticket": {
            "ticket_id": "EJ-O1",
            "subject": "Mi pedido llego frio y tarde",
            "body": "Llego 1h15 tarde y frio. El repartidor fue amable pero se demoro.",
            "system_logs": "order_placed; picked_up; delivered; promised_eta_min=35 actual_min=73 zone=centro zone_active_couriers=2 zone_open_orders=19",
        },
        "output": {
            "category": "operacion",
            "confidence": 0.9,
            "system_id": None,
            "reasoning": "La zona estaba saturada (2 couriers, 19 ordenes): la plataforma no fallo, fallo la capacidad operativa.",
            "evidence": "actual_min=73 vs promised_eta_min=35, zone_active_couriers=2",
        },
    },
    {
        "ticket": {
            "ticket_id": "EJ-LIM-B1",
            "subject": "Marcaron entregado pero nunca llego",
            "body": "El repartidor marco entregado a las 9:50 pero yo nunca recibi nada, estuve en casa.",
            "system_logs": "delivery_status status=DELIVERED set_by=courier_app gps_lat=-36.827 gps_lon=-73.049 customer_addr_lat=-36.820 customer_addr_lon=-73.055 distance_m=780",
        },
        "output": {
            "category": "bug",
            "confidence": 0.85,
            "system_id": "delivery_geofencing",
            "reasoning": "El sistema acepto DELIVERED con el courier a 780m del cliente: la validacion de geofencing esta ausente. El defecto es de la plataforma, no del courier.",
            "evidence": "status=DELIVERED, distance_m=780 (vs cliente)",
        },
    },
    {
        "ticket": {
            "ticket_id": "EJ-LIM-C1",
            "subject": "No me deja marcar recogido",
            "body": "Estoy con el pedido en la mano y el boton de 'recogi el pedido' esta gris.",
            "system_logs": "courier_action action=mark_picked_up result=BLOCKED reason=restaurant_has_not_confirmed_ready",
        },
        "output": {
            "category": "config",
            "confidence": 0.85,
            "system_id": "order_service",
            "reasoning": "result=BLOCKED por policy restaurant_has_not_confirmed_ready: el sistema actuo segun una regla configurada mal calibrada para el caso.",
            "evidence": "result=BLOCKED, reason=restaurant_has_not_confirmed_ready",
        },
    },
    {
        "ticket": {
            "ticket_id": "EJ-LIM-B2",
            "subject": "El mapa del repartidor no se mueve",
            "body": "El pedido dice en camino pero el mapa esta congelado hace 20 min.",
            "system_logs": "courier_location_stream courier=C-901 last_ping=16:59:10 gap_s=1250 courier_app_version=2.9.4",
        },
        "output": {
            "category": "bug",
            "confidence": 0.9,
            "system_id": "courier_app",
            "reasoning": "gap_s=1250 (mas de 20 min sin ping) + app_version antigua: el stream de ubicacion esta congelado, defecto de la courier app. NO es falta de couriers.",
            "evidence": "courier_location_stream, gap_s=1250, courier_app_version=2.9.4",
        },
    },
    {
        "ticket": {
            "ticket_id": "EJ-LIM-B3",
            "subject": "Todos los restaurantes aparecen cerrados",
            "body": "Son las 19:15 de un dia normal y TODOS aparecen cerrados. Imposible.",
            "system_logs": "availability_service query city=Santiago open_restaurants=0 total_restaurants=1240 tz_config=UTC (expected America/Santiago)",
        },
        "output": {
            "category": "bug",
            "confidence": 0.95,
            "system_id": "availability_service",
            "reasoning": "tz_config=UTC cuando debia ser America/Santiago: bug masivo de configuracion del servicio, 0 restaurantes abiertos. NO es none ni comercial.",
            "evidence": "open_restaurants=0, tz_config=UTC (expected America/Santiago)",
        },
    },
    {
        "ticket": {
            "ticket_id": "EJ-LIM-C2",
            "subject": "El descuento no se aplico",
            "body": "Use el cupon VERANO30 pero me cobraron el precio completo. Decia valido hasta hoy.",
            "system_logs": "coupon_apply code=VERANO30 result=REJECTED reason=expired valid_until=2026-06-29T23:59:59",
        },
        "output": {
            "category": "config",
            "confidence": 0.9,
            "system_id": "coupon_service",
            "reasoning": "valid_until expired: el sistema actuo segun la config del cupon (vencido el dia anterior). NO es comercial ni bug.",
            "evidence": "result=REJECTED, reason=expired, valid_until=2026-06-29",
        },
    },
    {
        "ticket": {
            "ticket_id": "EJ-LIM-O2",
            "subject": "No me pagaron el viaje",
            "body": "Hice la entrega ayer y no aparece en mis ganancias de la semana.",
            "system_logs": "earnings_batch run_date=2026-06-30 orders_processed=1450 status=DELIVERED included_in_batch=FALSE reason=delivered_after_cutoff cutoff=2026-06-29T23:59:59",
        },
        "output": {
            "category": "operacion",
            "confidence": 0.85,
            "system_id": None,
            "reasoning": "included_in_batch=FALSE por delivered_after_cutoff: el batch se corrio antes de la entrega. Timing operativo del proceso batch, no fallo de plataforma.",
            "evidence": "included_in_batch=FALSE, delivered_after_cutoff",
        },
    },
]


def router_messages(ticket: dict) -> list[dict]:
    """Construye los messages para el Router: system + pocos-shot + ticket real."""
    return router_messages_dynamic(ticket, FEW_SHOT, ROUTER_SYSTEM)


def router_messages_dynamic(
    ticket: dict,
    few_shot: list[dict],
    system_prompt: str,
) -> list[dict]:
    """Construye messages para el Router con system_prompt y few-shot parametrizables.

    Usado por LOOCV (cv.py): el system_prompt es el minimo (sin reglas) y el
    few-shot se selecciona de tickets reales del training set, no de los
    analogos sinteticos hardcoded.
    """
    msgs: list[dict] = [{"role": "system", "content": system_prompt}]
    for ex in few_shot:
        msgs.append({"role": "user", "content": _render_ticket(ex["ticket"])})
        msgs.append({"role": "assistant", "content": _json_compact(ex["output"])})
    msgs.append({"role": "user", "content": _render_ticket(ticket)})
    return msgs


def _render_ticket(t: dict) -> str:
    import json

    keep = {
        "ticket_id": t.get("ticket_id"),
        "reporter_type": t.get("reporter_type"),
        "order_id": t.get("order_id"),
        "subject": t.get("subject"),
        "body": t.get("body"),
        "system_logs": t.get("system_logs"),
        "app_version": t.get("app_version"),
        "platform": t.get("platform"),
    }
    keep = {k: v for k, v in keep.items() if v is not None}
    return "Ticket:\n" + json.dumps(keep, ensure_ascii=False)


def _json_compact(d: dict) -> str:
    import json

    return json.dumps(d, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Resolutor (config / operacion): redacta respuesta sugerida + accion
# ---------------------------------------------------------------------------

RESOLUTOR_SYSTEM = """\
Eres un agente de resolucion de tickets de FoodDash. Ya sabemos que el ticket \
es CONFIGURACION u OPERACION (no es bug). Tu trabajo: redactar una respuesta \
corta y empatica para el usuario (cliente/restaurante/repartidor) en español \
de Chile, y proponer la accion interna.

Reglas:
- Maximo 120 palabras en la respuesta al usuario.
- Tono cercano, no robotico. Usa "tú".
- Si hay reembolso/cancelacion razonable, proponlo en internal_action.
- NO inventes politicas. Si no hay evidencia suficiente, di que se escalara.

Devuelve SOLO JSON:
{
  "respuesta_usuario": "...",
  "internal_action": "auto_resolver | escalar_a_X | solicitar_info",
  "requires_refund": true|false,
  "confidence": 0.0
}
"""


def resolutor_messages(ticket: dict, category: str, reasoning: str) -> list[dict]:
    user = (
        f"Categoria: {category}\n"
        f"Razonamiento del triaje: {reasoning}\n\n"
        f"{_render_ticket(ticket)}\n\n"
        "Redacta respuesta y accion."
    )
    return [
        {"role": "system", "content": RESOLUTOR_SYSTEM},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Bug Triage: sistema, severidad, justificacion
# ---------------------------------------------------------------------------

BUG_TRIAGE_SYSTEM = """\
Eres un ingeniero de FoodDash haciendo triaje de un BUG confirmado. Con el \
ticket y (si aplica) evidencia correlacionada de tickets del mismo cluster, \
determina: sistema/componente responsable, severidad y siguientes pasos.

Severidad:
- critical: afecta a muchos usuarios o bloquea transacciones/pagos/cuentas.
- high: afecta a un usuario o pocos pero con daño monetario o de UX grave.
- medium: degradacion o workaround manual factible.
- low: cosmético o muy nicho.

Devuelve SOLO JSON:
{
  "system_id": "...",
  "severity": "critical|high|medium|low",
  "root_cause_hypothesis": "una frase",
  "next_steps": "que hacer ahora",
  "confidence": 0.0
}
"""


def bug_triage_messages(ticket: dict, reasoning: str) -> list[dict]:
    user = (
        f"Razonamiento del triaje: {reasoning}\n\n"
        f"{_render_ticket(ticket)}\n\n"
        "Haz el triaje del bug."
    )
    return [
        {"role": "system", "content": BUG_TRIAGE_SYSTEM},
        {"role": "user", "content": user},
    ]
