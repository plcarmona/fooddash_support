# FoodDash — Agente de triaje de tickets

Prototipo para el caso técnico **AI Solutions Expert · Healthatom**.

Un agente que recibe tickets de soporte de FoodDash (app de delivery) y, por cada uno, decide: **qué tipo de problema es**, **qué hacer** y —si es bug— **qué sistema está fallando**.

## Criterio de clasificación (5 categorías)

| Categoría | Cuándo | Acción |
|---|---|---|
| **bug** | Evidencia técnica en logs de fallo/inconsistencia, o el sistema aceptó un dato inválido (GPS lejos, geocode baja confianza, tz mal). Incluye sospecha fundada ("me cobraron dos veces"). | Bug Triage + búsqueda en registro de bugs conocidos |
| **config** | El sistema actuó conforme a su configuración, pero esa config está mal (`BLOCKED reason=<policy>`, `valid_until` expired, `notification_sound=OFF`). | Resolutor: respuesta sugerida |
| **operacion** | El flujo corrió; falló el mundo físico/humano (saturación de zona, item faltante, batch equivocado, cutoff). | Resolutor: respuesta sugerida |
| **comercial** | Consulta puramente comercial (renegociar comisión). | Derivar a comercial |
| **none** | Spam / prueba ("asdf test ignorar"). | Descartar |

La distinción clave **bug vs config vs operacion** se define así: **bug** = la plataforma llegó a un estado erróneo o aceptó un dato inválido; **config** = el sistema actuó según su configuración pero esa config está mal; **operacion** = el flujo corrió y falló el mundo físico/humano. El corte exacto en los casos limítrofes se documenta en `data/golden.json` (clasificación humana ticket por ticket) y se defiende en la bitácora.

## Arquitectura

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

**Modelos comparados:**
| Perfil | Modelo | Backend | Known-set | LOOCV-KNN | LOOCV gen |
|---|---|---|---|---|---|
| `ollama-3b` | qwen2.5:3b | Ollama local | 92.3% | — | — |
| `ollama-8b` | granite3.3:latest | Ollama local | 88.5% | — | — |
| `deepseek` | **deepseek-v4-flash** | API DeepSeek | **100%** | **85–88%** | 77–89% |

### Rendimiento: cuatro estimadores

| Métrica | Valor | Qué mide | Cómo se obtiene |
|---|---|---|---|
| **Known-set** (límite superior) | **100%** (26/26) | Prompt completo + pocos-shot afinados sobre el set. El prompt incluye reglas derivadas de estos tickets; mide el techo de rendimiento. | `run.py triage --profile deepseek` |
| **Híbrido** (reglas justificadas) | **96.2%** (25/26) | Leave-one-out con prompt mínimo + **solo las reglas trazables desde el training set** (las que solo sostenía el ticket held-out se dropean → sin leakage). few-shot KNN top-10. Dropea en 3/26 folds. | `run.py cv-hybrid --profile deepseek --k 10` |
| **LOOCV-KNN** (recuperación por embeddings) | **~85–88%** (22–23/26) | Leave-one-out con recuperación determinística por embeddings (top-5 similares vía `snowflake-arctic-embed2`) + prompt mínimo. **La recuperación no varía** entre corridas: el gold label está en el top-5 para el 92% de los tickets (métrica estable). La *predicción* sí varía (85–88%) por no-determinismo del LLM a temp 0; los errores son siempre de razonamiento (gold en top-5). | `run.py cv-knn --profile deepseek --k 5` |
| **LOOCV genérico** (límite inferior) | **77–89%** (20–23/26) | Leave-one-out con prompt mínimo + 8 pocos-shot fijos balanceados. Alta varianza por no-determinismo del modelo de razonamiento. | `run.py cv --profile deepseek` |

El **Híbrido (96.2%)** es el punto medio honesto entre el known-set (100%, con leakage) y el LOOCV-KNN (~85–88%, sin reglas). Por cada fold, el prompt incluye una regla solo si algún ticket del training set la traza (misma etiqueta golden + keyword de la regla). De los 8 folds donde el held-out dependía de una regla, en 3 la regla era **única** del ticket (R2: tz masivo en TCK-1024; R7: comercial en TCK-1015; R8: spam en TCK-1021) y se dropea. De esos 3, el modelo resuelve TCK-1015 y TCK-1021 sin la regla (desde la definición de categoría); **solo TCK-1024 cae** → única brecha real de generalización. Con few-shot top-10, además recupera todos los errores recuperables del KNN (aquellos cuya regla se aprende del training set), dejando un único fallo. Reporte: [`output/deepseek/cv_hybrid_report.md`](output/deepseek/cv_hybrid_report.md)

El LOOCV-KNN (~85–88%) usa recuperación determinística por embeddings: cada ticket se evalúa con los 5 más parecidos del resto. El **92% de los tickets tiene su etiqueta correcta en esos 5** (métrica estable, no varía); el rango de accuracy viene del LLM.

#### Análisis de errores LOOCV-KNN: recuperación vs razonamiento

El set exacto de errores **varía entre corridas (3–4)** por no-determinismo del LLM, pero el gold label **siempre** está en los top-5 recuperados → los fallos son de razonamiento del LLM, no de recuperación. Tabla de una corrida representativa (4 errores):

| Ticket | Gold | Pred | Gold∈top5 | Top-5 distribution | Diagnóstico |
|---|---|---|---|---|---|
| TCK-1012 | bug | operacion | ✓ | 4 bug, 1 operacion | **LLM**: con 4 ejemplos bug, aún predice operacion. Patrón "aceptó dato inválido = bug" es el más difícil de aprender. |
| TCK-1024 | bug | config | ✓ | 1 bug, 3 config, 1 operacion | **Recuperación+razonamiento**: los embeddings también creen que tz_config se parece a config. Ambos se equivocan. |
| TCK-1023 | operacion | config | ✓ | 3 bug, 2 operacion | **LLM**: los 3 bugs en top-5 confunden al modelo. Cutoff es genuinamente ambiguo. |
| TCK-1010 | config | none | ✓ | 3 config, 2 operacion | **LLM**: con 3 ejemplos config, predice none. El cupón vencido confunde al modelo. |

Reporte completo: [`output/deepseek/cv_knn_report.md`](output/deepseek/cv_knn_report.md) · Datos: [`output/deepseek/cv_knn.json`](output/deepseek/cv_knn.json)

#### Análisis de errores del Híbrido: regla ausente vs razonamiento

El híbrido recupera **3 de los 4** errores del LOOCV-KNN (TCK-1010, TCK-1012 y TCK-1023) y deja **un único fallo**, tipificado por causa:

| Ticket | Gold | Pred | Regla dropeada | Tipo de fallo | Lectura |
|---|---|---|---|---|---|
| TCK-1024 | bug | config | R2 (tz masivo) | **Regla ausente** | R2 era única de 1024 → se dropea. Sin ella el modelo la ve como config de zona horaria. Único fallo esperado y legítimo del LOOCV. |

Los otros 3 errores del KNN se resuelven en el híbrido: TCK-1010 y TCK-1012 porque sus reglas (R5, R3) sí se trazan desde tickets hermanos del training set; y TCK-1023 porque con few-shot top-10 el modelo ve suficientes ejemplos de operacion como para llevar el cutoff a su categoría correcta (a diferencia de k=5, donde fallaba por razonamiento con R6 presente).

Conclusión: de los 8 tickets que dependían de una regla, en 3 la regla era única del held-out (R2/R7/R8). El modelo resolvió 2 de esos 3 (TCK-1015, TCK-1021) **sin** la regla, solo desde la definición de categoría. Solo TCK-1024 es irre recuperable → confirma que es la **única brecha real de generalización**; el resto del criterio es plenamente aprendible del training set.

Reporte completo: [`output/deepseek/cv_hybrid_report.md`](output/deepseek/cv_hybrid_report.md) · Datos: [`output/deepseek/cv_hybrid.json`](output/deepseek/cv_hybrid.json)

#### Patrones que las reglas explícitas aportan (no se aprenden solo del few-shot)

| Patrón | Tickets | Sin la regla explícita, el modelo tiende a... |
|---|---|---|
| Sistema aceptó estado inválido | TCK-1002 (DELIVERED a 780m), TCK-1012 (geocode 0.31) | Clasificar como operacion (error humano) — el concepto "validación ausente = bug" es el más difícil |
| Config del servicio con blast radius masivo | TCK-1024 (tz_config=UTC) | Clasificar como config simple — incluso los embeddings lo ven como config |
| Proveedor externo caído | TCK-1016 (SMS carrier_unreachable) | Clasificar como operacion (problema externo) |
| Policy que bloquea vs timing operativo | TCK-1007 (BLOCKED), TCK-1023 (cutoff) | Confundir config vs operacion — límite genuinamente ambiguo |

Reporte completo: [`output/deepseek/cv_loocv_report.md`](output/deepseek/cv_loocv_report.md) · Datos crudos: [`output/deepseek/cv_loocv.json`](output/deepseek/cv_loocv.json)

## Herramientas (tools) del agente

**Funciones implementadas en código:**

| Función | Archivo | Qué hace |
|---|---|---|
| `router_messages` | prompts.py | Construye el prompt del Router con criterio + 9 pocos-shot |
| `lookup_known_bug` | known_bugs.py | Busca el ticket en el registro de bugs conocidos por sistema + síntomas |
| `map_system` | known_bugs.py | Mapea el error a un componente del catálogo (con normalización) |
| `embed_ticket` + `retrieve_top_k` | embeddings.py | Recupera los k tickets más similares por cosine similarity |
| `triage_ticket` | agents.py | Orquesta: Router → rama (Resolutor \| Bug Triage + kb_lookup) |

**Capabilities del agente (vía prompt, no código):**

| Capability | Qué hace | Cómo se logra |
|---|---|---|
| Clasificar | Clasifica el ticket en 5 categorías con JSON estructurado | Router prompt con criterio + pocos-shot |
| Leer logs antes que subject | Los logs pesan más que el relato del usuario | Regla explícita en el system prompt |
| Redactar respuesta | Respuesta empática al usuario + acción interna | Resolutor prompt (config/operación/comercial) |
| Asignar severidad | critical/high/medium/low para bugs | Bug Triage prompt |
| Agrupar por causa raíz | Tickets con el mismo `known_bug_id` se agrupan en el reporte | `write_systems_report` agrupa por bug_id |

## Cómo correrlo

```bash
# 1. Dependencias
uv sync

# 2. Configurar .env (DeepSeek API key)
cp .env.example .env
#    editar .env y poner DEEPSEEK_API_KEY=sk-...

# 3. Correr el modelo seleccionado (deepseek) sobre los 26 tickets
uv run python run.py triage --profile deepseek

# 4. Comparar los 3 modelos
uv run python run.py compare --router-only

# 5. Cross-validation LOOCV (generalizacion honesta, prompt minimo)
uv run python run.py cv --profile deepseek

# 6. Cross-validation LOOCV-KNN (recuperacion por embeddings, top-5)
uv run python run.py cv-knn --profile deepseek --k 5

# 6b. Híbrido (minimal + solo reglas justificadas por el training set)
uv run python run.py cv-hybrid --profile deepseek --k 10
uv run python run.py cv-hybrid --profile deepseek --failing-only   # solo los 7 propensos a fallar

# 7. Regenerar reportes de un perfil ya corrido
uv run python run.py report --profile deepseek
```

## Salidas (`output/<perfil>/`)

- `clasificacion.jsonl` — 1 línea por ticket: categoría, confianza, sistema, reasoning, evidence, y según la rama: respuesta / severity / known_bug.
- `respuestas/TCK-XXXX.md` — respuestas sugeridas para config/operación/comercial.
- `sistemas_fallando.md` — **la lista de sistemas con bugs**: tabla con severidad, tickets agrupados, bug conocido (o 🆕 nuevo), equipo, workaround, y detalle por sistema.
- `eval.json` — agreement vs golden set (límite superior), matriz de confusión, desacuerdos.
- `cv_loocv.json` / `cv_loocv_report.md` — LOOCV con few-shot genérico (límite inferior).
- `cv_knn.json` / `cv_knn_report.md` — LOOCV-KNN con recuperación por embeddings. Incluye análisis de recuperación por ticket y separación de fallos (recuperación vs razonamiento).
- `cv_hybrid.json` / `cv_hybrid_report.md` — Híbrido: minimal + reglas justificadas por el training set. Tipifica cada error como regla ausente (regla dropeada) vs fallo de razonamiento (8/8 reglas presentes).

## Estructura del repositorio

```
prototipo/
├── data/
│   ├── tickets.json              # set original (26 tickets)
│   ├── golden.json               # clasificación humana (ground truth)
│   ├── systems_catalog.json      # catálogo de 16 sistemas de FoodDash
│   └── known_bugs.json           # registro de 10 bugs conocidos
├── src/fooddash/
│   ├── llm.py                    # cliente unificado (Ollama + DeepSeek)
│   ├── prompts.py                # criterio + pocos-shot (fine-tuneable)
│   ├── agents.py                 # router + resolutor + bug-triage
│   ├── known_bugs.py             # kb_lookup (búsqueda en registro)
│   ├── embeddings.py             # embed_ticket + cosine + retrieve_top_k
│   ├── cv.py                     # LOOCV + LOOCV-KNN + Híbrido (reglas justificadas) + prompt mínimo
│   └── eval.py                   # evaluación vs golden set
├── run.py                        # entry point (triage / compare / report / cv / cv-knn / cv-hybrid)
├── output/                       # salidas (no se commitea)
├── .env.example                  # template de configuración
├── README.md                     # este archivo
└── BITACORA_IA.md                # bitácora de uso de IA
```

## Decisiones clave

1. **Criterio alineado con el operador humano**, no con el default del LLM. El golden set se construyó a mano a partir de la nota del operador y se usa como ground truth.
2. **5 categorías** (no 3). "Comercial" y "none" separan tickets que no encajan en bug/config/operación (TCK-1015 renegociar comisión, TCK-1021 spam).
3. **Registro de bugs conocidos**: el agente busca cada bug en la base y marca los nuevos con 🆕. Esto separa "rutinario" de "investigar".
4. **Agregación por `known_bug_id`**: tickets que matchean el mismo bug conocido se agrupan automáticamente en el reporte. Esto correlaciona causa raíz (usuarios distintos, pedidos distintos, mismo bug) — no por `order_id`. Ej: TCK-1006 (sospecha sin logs) y TCK-1022 (confirmado con logs) ambos → BUG-002.
5. **Sin frameworks de agentes** (no langchain). El cliente LLM son ~150 líneas.
6. **Modelo seleccionado: deepseek-v4-flash** (rango 85–100%). El local 3B (92.3% known-set) es una alternativa válida offline y sin costo.
7. **Rendimiento medido 4 formas.** Known-set (todas las reglas): 100%. **Híbrido** (minimal + solo reglas trazables desde training, KNN top-10): 96.2%. LOOCV-KNN (embeddings top-5, sin reglas): ~85–88% (la recuperación es determinista: 92% gold-en-top-5; la predicción varía). LOOCV genérico (prompt mínimo, few-shot fijo): 77–89%. El híbrido acota la brecha de generalización: de los tickets que dependían de una regla, solo TCK-1024 es irre recuperable cuando su regla se dropea.
