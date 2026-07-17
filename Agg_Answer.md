# FoodDash — Respuesta al caso técnico

Agente de triaje de tickets de soporte para FoodDash (app de delivery). Por cada ticket decide: **qué tipo de problema es**, **qué hacer** y —si es bug— **qué sistema falla**.

> Documento de respuesta (conciso). El detalle técnico vive en [`prototipo/README.md`](prototipo/README.md); el registro de uso de IA en [`prototipo/BITACORA_IA.md`](prototipo/BITACORA_IA.md).

---

## 1. Criterio y exploración del problema

### Cómo abordé el problema
Empecé clasificando los 26 tickets a mano ([`prototipo/data/golden.json`](prototipo/data/golden.json)). Ese es el ground truth: el agente tiene que replicar mi criterio, no el default del LLM. Modelo y prompt se eligen por agreement contra ese set.

### Exploración: modelos de distintos tamaños → elegir uno → CV → mejorar → mejorar
La metodología fue de afuera hacia adentro, acotando la brecha de generalización en cada iteración:

1. **Evaluar modelos de distintos tamaños.** Probé tres perfiles que cubren el espectro costo/capacidad:
   - `ollama-3b` (qwen2.5:3b, local, sin costo) → **92.3%** known-set.
   - `ollama-8b` (granite3.3, local) → **88.5%** known-set.
   - `deepseek` (deepseek-v4-flash, API) → **100%** known-set.
   - **Hallazgo contraintuitivo:** el 8B fue *peor* que el 3B (sobre-generalizó la regla "aceptar dato inválido = bug" a errores humanos). Más grande no es siempre mejor.
2. **Elegir uno.** deepseek-v4-flash ganó por agreement. A partir de acá todo el iterado es sobre ese modelo.
3. **Validación cruzada honesta (LOOCV).** El 100% del known-set tenía *leakage*: las 8 reglas y los pocos-shot derivan de los propios tickets. Corrí leave-one-out con **prompt mínimo** (sin reglas hand-craftadas) + few-shot fijo → **77–89%** (límite inferior, alta varianza). Ahí quedaron expuestos los límites reales.
4. **Mejorar #1 — LOOCV-KNN.** Reemplacé el few-shot genérico por **recuperación determinística por embeddings** (`snowflake-arctic-embed2`, top-5 similares por ticket). Resultado: **~85–88%**. La recuperación *no* varía entre corridas (el gold está en el top-5 para el 92% de los tickets); lo que varía es el razonamiento del LLM. Los 3–4 errores son siempre de razonamiento, no de recuperación.
5. **Mejorar #2 — Híbrido.** Para separar "regla afinada para ese ticket" (leakage) de "límite real del modelo", construí un punto medio: por cada fold incluyo una regla **solo si algún ticket del training set la traza** (misma etiqueta + keyword). Las reglas únicas del held-out se dropean. Resultado: **96.2%** (25/26). Recupera los 3 errores recuperables del KNN y deja **un único fallo legítimo** (TCK-1024, cuya regla de tz-masivo era única del ticket).

**Rendimiento como rango:** 100% known-set (máximo, con información completa) → 96.2% híbrido (mejor intento sin leakage) → 77–89% LOOCV genérico (mínimo, validación cruzada simple).

### Supuestos
- El golden set del operador es correcto (lo construí yo y lo defiendo).
- 26 tickets alcanzan para iterar el *criterio* y la forma de medirlo, pero **no** para fine-tunear pesos.
- Los `system_logs` son la verdad técnica; el relato del usuario pesa menos.

### Qué prioricé
- **Razonamiento y decisiones > sofisticación del código.** Cliente LLM a mano (~150 líneas), sin frameworks de agentes.
- **Medir antes de creer.** El 100% del known-set me obligó a construir el LOOCV para no engañarme.
- **Agregación por causa raíz** (no por `order_id`): tickets que matchean el mismo bug conocido se agrupan → correlaciona usuarios/pedidos distintos con el mismo defecto.

### Qué dejé fuera a propósito
- Correlación de causa raíz para **bugs nuevos** (los del registro se agrupan; los nuevos requerirían matching por señales de log/embeddings). Anotado como mejora.
- Pipeline async/paralelo (26 tickets son instantáneos en serie).
- Integración con un sistema de tickets real (el prototipo lee un JSON local).
- Fine-tuning de pesos (con N=26 no se justifica; prompting bien hecho da 85–100%).

---

## 2. Arquitectura

```
[ Ticket ]
   │
   ▼
┌──────────────────────────────────────────────┐
│ Agente 1 · ROUTER (triaje)                   │
│ Clasifica en bug|config|operacion|comercial|none│
│ Recibe: criterio + 9 ejemplos pocos-shot     │
└──────────┬────────────┬────────────┬─────────┘
           ▼            ▼            ▼
       config/oper /   bug        none/comer
       comercial        │         (descartar/
           │            │         derivar)
           ▼            ▼
┌───────────────┐  ┌──────────────────────────┐
│ RESOLUTOR     │  │ BUG TRIAGE               │
│ Respuesta +   │  │ Sistema + severidad +    │
│ acción        │  │ hipótesis causa raíz     │
└───────────────┘  └──────────┬───────────────┘
                              ▼
                   ┌──────────────────────────┐
                   │ KB_LOOKUP                │
                   │ Registro de bugs conocidos│
                   │ (¿bug nuevo o recurrente?)│
                   └──────────────────────────┘
```

**Flujo y comunicación:**
- **Router** lee el ticket (logs primero, por la regla de oro) y devuelve **JSON estructurado**: categoría, confianza, `system_id`, razonamiento, evidencia. Todo el acoplamiento entre agentes es por ese JSON, no por texto libre.
- **Resolutor** (rama config/operación/comercial): recibe categoría + razonamiento y devuelve respuesta empática al usuario + acción interna (`auto_resolver`/`escalar_a_X`/`solicitar_info`) + flag de reembolso.
- **Bug Triage** (rama bug): recibe el razonamiento y asigna sistema, severidad, hipótesis de causa raíz y siguientes pasos.
- **KB_LOOKUP**: tras el triaje, busca el bug en el registro de bugs conocidos por sistema + síntomas. Si existe → marca `known_bug_id` (recurrente); si no → 🆕 (nuevo, a investigar).

---

## 3. Decisiones de acción (por tipo de resultado)

| Categoría | Qué se hace con el ticket |
|---|---|
| **bug** | → Bug Triage (sistema + severidad) + KB_LOOKUP. Si es conocido: aplicar workaround y agrupar con sus hermanos. Si es nuevo 🆕: escalar a investigar + registrar. |
| **config** | → Resolutor: respuesta sugerida + acción (suele ser `auto_resolver` cambiando el parámetro/regla; ej. publicar platos, ajustar mínimo, reactivar sonido). |
| **operacion** | → Resolutor: respuesta sugerida + reembolso/compensación si aplica (saturación de zona, item faltante, batch equivocado, cutoff). |
| **comercial** | → Derivar a comercial (renegociación de comisión, contratos). |
| **none** | → Descartar (spam / prueba). |

---

## 4. Cómo decido cuándo algo es un BUG

**Definición defendida:** es BUG cuando hay evidencia técnica en los logs de que **la plataforma llegó a un estado erróneo/inconsistente o aceptó un dato inválido**. El defecto es de la plataforma, no del mundo físico/humano.

La distinción entre las tres familias:
- **Bug** = la plataforma llegó a un estado erróneo o aceptó un dato inválido.
- **Config** = el sistema actuó **conforme a su configuración**, pero esa config está mal para el caso. El fix es cambiar un parámetro/regla, no arreglar código.
- **Operación** = el flujo corrió sin bloqueos ni estados inconsistentes; falló el mundo físico/humano (saturación, item faltante, error del courier, cutoff de batch).

**Reglas decisoras (en orden de precedencia):**
1. `crash | stacktrace | NullPointerException | ERROR | timeout | idempotency_key_reused | p95_latency_ms alto | carrier_unreachable | all_failed | frontend_error | js_error | tz_config=UTC | gap_s` → **BUG**.
2. "Todos los restaurantes cerrados" + tz/availability_service → **BUG MASIVO** (no es none).
3. `status=DELIVERED` con `distance_m>200`, o geocode `confidence<0.6` usado igual → **BUG** (validación ausente).
4. "Cobro raro" / "me cobraron dos veces" (con o sin logs) → **BUG** (sospecha fundada de Payment Service).
5. `result=BLOCKED reason=<policy>` o parámetro mal seteado (`notification_sound=OFF`, `draft_state=UNPUBLISHED`, `holiday_hours_enabled`, `valid_until` expired, `restaurant_min` alto) → **CONFIG**.
6. Pedido tardío/frío, faltó un item, courier se equivocó en batch, `included_in_batch=FALSE`/`delivered_after_cutoff` → **OPERACIÓN**.
7. "Renegociar comisión" / "con quién hablo" (comercial puro) → **COMERCIAL**.
8. "test ignorar" / "asdf" → **NONE**.

**Casos limítrofe y por qué los corté así** (ver [`prototipo/BITACORA_IA.md`](prototipo/BITACORA_IA.md) "En qué la IA se equivocó"):
- **TCK-1002** (DELIVERED a 780m) → **bug**, no operación. Mi primer instinto fue "el courier se equivocó"; lo corregí: aceptar un dato inválido (GPS lejos) = validación ausente = defecto de plataforma.
- **TCK-1007 / TCK-1025** (BLOCKED por policy) → **config**, no operación. El sistema actuó según una regla mal calibrada.
- **TCK-1012** (geocode confidence=0.31) → **bug**: la app navegó con un resultado de baja confianza sin alertar.

---

## 5. Análisis técnico de un caso (paso a paso)

### TCK-1002 → BUG
> Subject: "Marcaron entregado pero nunca llegó". Log: `delivery_status status=DELIVERED set_by=courier_app gps_lat=..8270 gps_lon=..0498 customer_addr_lat=..8201 customer_addr_lon=..0550 distance_m=780`

1. **Regla de oro:** leo el log antes que el relato.
2. Token decisivo: `status=DELIVERED` + `distance_m=780`.
3. Aplico **regla 3**: DELIVERED con `distance_m>200`.
4. **Razonamiento:** el sistema permitió marcar entregado con el courier a 780m del cliente → la validación de geofencing está ausente. No es que el courier "se equivocó"; la plataforma aceptó un dato inválido.
5. **Decisión:** BUG → Bug Triage (sistema `delivery_geofencing`, severidad high) → KB_LOOKUP matchea `BUG-008`. Acción: reembolsar + investigar entrega + escalar a Logística/Backend.

### TCK-1007 → CONFIG
> Log: `courier_action action=mark_picked_up result=BLOCKED reason=restaurant_has_not_confirmed_ready`

1. Token decisivo: `result=BLOCKED` + `reason=<policy>`.
2. Aplico **regla 5**: BLOCKED por policy → CONFIG.
3. **Razonamiento:** el sistema **actuó conforme a su configuración** (la policy `restaurant_has_not_confirmed_ready` impide marcar recogido). El courier tiene el pedido en la mano, así que la regla está mal calibrada para el caso, pero no hay estado erróneo ni código roto.
4. **Decisión:** CONFIG → Resolutor. El fix es ajustar la regla/parámetro, no parchar código.

### TCK-1011 → BUG
> Log: `payment result=SUCCESS amount=12500; order_create result=ERROR reason=timeout downstream=inventory_service`

1. Token decisivo: `payment=SUCCESS` seguido de `order_create ERROR timeout`.
2. Aplico **regla 1** (ERROR | timeout → BUG).
3. **Razonamiento:** hay un **estado inconsistente** — el cliente fue cobrado pero el pedido no se creó (timeout del `inventory_service`). La plataforma aceptó el pago sin garantizar la creación del pedido ni hacer rollback/compensación. Eso es defecto de plataforma.
4. **Decisión:** BUG 🆕 (no en el registro) → severidad high → escalar a order_service: implementar idempotencia + rollback del pago si falla la creación, y reembolsar manualmente.

---

## 6. Tools del agente

| Tool / Capability | Qué hace | Por qué la necesita |
|---|---|---|
| `router_messages` | Construye el prompt del Router (criterio + pocos-shot) | Empaqueta el criterio y los ejemplos ancla; es la entrada del triaje. |
| `triage_ticket` | Orquesta Router → rama (Resolutor \| Bug Triage + KB_LOOKUP) | Decide la ruta según la categoría y evita llamar al Resolutor sobre un bug. |
| `lookup_known_bug` | Busca el bug en el registro por sistema + síntomas | **Lo que hace útil el triaje para ingeniería**: separa rutinario (workaround aplicable) de nuevo (investigar). |
| `map_system` | Mapea el error a un componente del catálogo (con normalización) | Para agrupar y enrutar al equipo correcto. |
| `embed_ticket` + `retrieve_top_k` | Recupera los k tickets más similares por cosine similarity | Poder few-shot dinámico y validación (LOOCV-KNN); a futuro, correlación de bugs nuevos. |
| *Leer logs antes que subject* (capability vía prompt) | Los logs pesan más que el relato | Evita que el LLM se deje llevar por el cuerpo del usuario (regla de oro). |
| *Redactar respuesta* (Resolutor) | Respuesta empática + acción interna | Cierra el loop para config/operación sin tocar ingeniería. |
| *Asignar severidad* (Bug Triage) | critical/high/medium/low | Prioriza qué bug investigar primero. |
| *Agrupar por causa raíz* | Tickets con el mismo `known_bug_id` se agrupan | Correlaciona usuarios/pedidos distintos con el mismo defecto (ej. TCK-1006 + TCK-1022 → `BUG-002`). |

---

## 7. Prototipo funcional

Corre sobre los 26 tickets y produce clasificación + decisión por ticket. Stack: **Python + uv**, cliente LLM a mano (~150 líneas, sin frameworks), modelos vía Ollama local y DeepSeek API.

```bash
cd prototipo
uv sync                                   # dependencias
cp .env.example .env                      # poner DEEPSEEK_API_KEY=sk-...
uv run python run.py triage --profile deepseek   # corre sobre los 26 tickets
```

**Resultado:** known-set **100%** (26/26) → híbrido **96.2%** (25/26, sin leakage) → LOOCV-KNN ~85–88%.

**Salidas en `prototipo/output/deepseek/`:** `clasificacion.jsonl` (1 línea por ticket), `respuestas/TCK-XXXX.md` (respuestas sugeridas), `sistemas_fallando.md` (los 13 bugs agrupados por causa raíz, con severidad y equipo).

Instrucciones completas y variantes (comparar modelos, CV) en [`prototipo/README.md`](prototipo/README.md).

---

## 8. Bitácora de uso de IA

👉 [`prototipo/BITACORA_IA.md`](prototipo/BITACORA_IA.md)

Resumen: herramientas usadas (Ollama 3B/8B locales + DeepSeek API), 4 prompts clave, dónde la IA se equivocó (4 desacuerdos iniciales, over-generalización del 8B, leakage del 100% que forzó el LOOCV) y qué decisiones fueron 100% mías (el criterio de clasificación, las 5 categorías, los cortes limítrofes, el golden set como ground truth, sin frameworks de agentes).
