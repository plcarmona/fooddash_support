# Cross-validation: LOOCV con prompt minimo (deepseek-v4-flash)

## Metodologia

- **Leave-one-out (LOOCV):** cada ticket se evalua con los otros 25 como training.
- **Prompt minimo:** solo definiciones de categoria + 'lee logs antes que subject'.
  SIN las 8 reglas especificas del prompt de produccion.
- **Few-shot:** tickets reales del training set (no analogos sinteticos).
  Hasta 2 ejemplos por categoria, con diversidad de sistema dentro de bug.

## Resultado

| Metrica | Valor |
|---|---|
| **LOOCV accuracy** | **22/26 (84.6%)** |
| Known-set accuracy (full prompt) | 26/26 (100.0%) |

## Recall por etiqueta

| Etiqueta | Recall | TP | FN |
|---|---|---|---|
| bug | 69% | 9 | 4 |
| config | 100% | 7 | 0 |
| operacion | 100% | 4 | 0 |
| comercial | 100% | 1 | 0 |
| none | 100% | 1 | 0 |

## Analisis de errores

| Ticket | Gold | Pred | Confianza | Razonamiento del modelo |
|---|---|---|---|---|
| TCK-1002 | bug | operacion | 0.95 | El repartidor marco entregado a 780m de la direccion del cliente, probable error |
| TCK-1008 | bug | none | 0.9 | Cliente solicita actualizacion de ticket previo. No es un nuevo fallo ni evidenc |
| TCK-1012 | bug | operacion | 0.7 | Direccion incorrecta ingresada por el cliente; geocoding con baja confianza pero |
| TCK-1024 | bug | config | 0.95 | Todos los restaurantes aparecen cerrados por un error de configuracion de timezo |

## Interpretacion

El modelo se equivoca en 4 ticket(s) sin las reglas hand-craftadas. Estos revelan que patrones el modelo NO aprende solo del few-shot y requieren ya sea mas ejemplos o reglas explicitas en el prompt de produccion.