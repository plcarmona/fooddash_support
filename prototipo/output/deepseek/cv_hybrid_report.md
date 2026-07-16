# Cross-validation: HIBRIDO (reglas justificadas) — deepseek-v4-flash

## Metodologia

- **Hibrido entre known-set (100%) y LOOCV-KNN minimal (~85–88%).**
- Por cada fold LOOCV, el system prompt = `MINIMAL` (defs de categoria) + **solo las reglas
  que el training set logra trazar** (misma etiqueta golden + keyword de la regla).
- Las reglas que solo se sostenian con el ticket held-out se **dropean** -> se elimina el
  test-set leakage sin tirar las 8 reglas por igual.
- **Few-shot:** KNN top-10 (snowflake-arctic-embed2, recuperacion deterministica).
- **Scope:** los 26 tickets.

## Resultado

| Metrica | Valor |
|---|---|
| **CV-Hibrido accuracy** | **25/26 (96.2%)** |
| Folds con alguna regla dropeada | 3/26 |
| Known-set (full prompt, todas las reglas) | 26/26 (100.0%) |
| LOOCV-KNN minimal (sin reglas) | ~85–88% (22–23/26, varía por LLM) |

## Recall por etiqueta

| Etiqueta | Recall | TP | FN |
|---|---|---|---|
| bug | 92% | 12 | 1 |
| config | 100% | 7 | 0 |
| operacion | 100% | 4 | 0 |
| comercial | 100% | 1 | 0 |
| none | 100% | 1 | 0 |

## Detalle por ticket (reglas incluidas/dropeadas)

| Ticket | Gold | Pred | ¿Correcto? | Reglas | Dropeadas |
|---|---|---|---|---|---|
| TCK-1001 | config | config | ✓ | 8/8 | — |
| TCK-1002 | bug | bug | ✓ | 8/8 | — |
| TCK-1003 | config | config | ✓ | 8/8 | — |
| TCK-1004 | bug | bug | ✓ | 8/8 | — |
| TCK-1005 | operacion | operacion | ✓ | 8/8 | — |
| TCK-1006 | bug | bug | ✓ | 8/8 | — |
| TCK-1007 | config | config | ✓ | 8/8 | — |
| TCK-1008 | bug | bug | ✓ | 8/8 | — |
| TCK-1009 | config | config | ✓ | 8/8 | — |
| TCK-1010 | config | config | ✓ | 8/8 | — |
| TCK-1011 | bug | bug | ✓ | 8/8 | — |
| TCK-1012 | bug | bug | ✓ | 8/8 | — |
| TCK-1013 | operacion | operacion | ✓ | 8/8 | — |
| TCK-1014 | bug | bug | ✓ | 8/8 | — |
| TCK-1015 | comercial | comercial | ✓ | 7/8 | R7 |
| TCK-1016 | bug | bug | ✓ | 8/8 | — |
| TCK-1017 | bug | bug | ✓ | 8/8 | — |
| TCK-1018 | operacion | operacion | ✓ | 8/8 | — |
| TCK-1019 | bug | bug | ✓ | 8/8 | — |
| TCK-1020 | config | config | ✓ | 8/8 | — |
| TCK-1021 | none | none | ✓ | 7/8 | R8 |
| TCK-1022 | bug | bug | ✓ | 8/8 | — |
| TCK-1023 | operacion | operacion | ✓ | 8/8 | — |
| TCK-1024 | bug | config | ✗ | 7/8 | R2 |
| TCK-1025 | config | config | ✓ | 8/8 | — |
| TCK-1026 | bug | bug | ✓ | 8/8 | — |

## Analisis de errores

### TCK-1024 — gold=bug pred=config (dropeadas: R2)
- Tipo: **REGLA AUSENTE**: la regla era unica del ticket held-out y se dropeo. Fallo esperado de generalizacion.
- Razonamiento del modelo: El sistema usa UTC en vez de America/Santiago, causando que los horarios de disponibilidad se malinterpreten y todos los restaurantes aparez

## Interpretacion

El hibrido se ubica entre el known-set (100%, con leakage) y el LOOCV-KNN minimal (~85–88%, sin reglas). Al dropear solo las reglas no trazables desde el training set, se recupera la generalizacion sin tirar el conocimiento codificado: 25/26 (96%). Los errores residuales son de dos tipos: (a) regla ausente (la regla era unica del ticket held-out), y (b) fallos de razonamiento donde las 8 reglas estaban presentes y el modelo las piso.