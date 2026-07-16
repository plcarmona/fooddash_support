# Cross-validation: LOOCV-KNN con embeddings (k=5, deepseek-v4-flash)

## Metodologia

- **Leave-one-out + KNN:** cada ticket se evalua con los k mas parecidos de los otros 25.
- **Recuperacion deterministica:** snowflake-arctic-embed2 (1024 dims) + cosine similarity.
  La recuperacion no varia entre corridas (solo la prediccion del LLM tiene varianza).
- **Prompt minimo:** solo definiciones de categoria. Sin reglas hand-craftadas.
- **Few-shot:** los k tickets recuperados + su etiqueta y razonamiento golden.

## Resultado

| Metrica | Valor |
|---|---|
| **LOOCV-KNN accuracy** | **23/26 (88.5%)** |
| Gold label en top-5 recuperados | 24/26 (92%) |
| Known-set (full prompt) | 26/26 (100.0%) |

## Recall por etiqueta

| Etiqueta | Recall | TP | FN |
|---|---|---|---|
| bug | 85% | 11 | 2 |
| config | 100% | 7 | 0 |
| operacion | 75% | 3 | 1 |
| comercial | 100% | 1 | 0 |
| none | 100% | 1 | 0 |

## Recuperacion por ticket (top-5)

| Ticket | Gold | Pred | ¿Correcto? | Gold∈top5 | Top recuperados (similitud) |
|---|---|---|---|---|---|
| TCK-1001 | config | config | ✓ | ✓ | TCK-1025(con,0.58), TCK-1011(bug,0.50), TCK-1007(con,0.49), TCK-1026(bug,0.46), TCK-1009(con,0.45) |
| TCK-1002 | bug | bug | ✓ | ✓ | TCK-1008(bug,0.67), TCK-1005(ope,0.67), TCK-1019(bug,0.63), TCK-1007(con,0.61), TCK-1023(ope,0.57) |
| TCK-1003 | config | config | ✓ | ✓ | TCK-1013(ope,0.45), TCK-1007(con,0.44), TCK-1009(con,0.44), TCK-1018(ope,0.44), TCK-1024(bug,0.44) |
| TCK-1004 | bug | bug | ✓ | ✓ | TCK-1017(bug,0.77), TCK-1026(bug,0.34), TCK-1014(bug,0.33), TCK-1025(con,0.30), TCK-1009(con,0.30) |
| TCK-1005 | operacion | operacion | ✓ | ✓ | TCK-1002(bug,0.67), TCK-1008(bug,0.58), TCK-1009(con,0.56), TCK-1019(bug,0.55), TCK-1018(ope,0.54) |
| TCK-1006 | bug | bug | ✓ | ✓ | TCK-1022(bug,0.55), TCK-1015(com,0.45), TCK-1001(con,0.41), TCK-1018(ope,0.41), TCK-1008(bug,0.40) |
| TCK-1007 | config | config | ✓ | ✓ | TCK-1002(bug,0.61), TCK-1025(con,0.61), TCK-1019(bug,0.54), TCK-1018(ope,0.54), TCK-1008(bug,0.51) |
| TCK-1008 | bug | none | ✗ | ✓ | TCK-1002(bug,0.67), TCK-1023(ope,0.59), TCK-1005(ope,0.58), TCK-1018(ope,0.55), TCK-1025(con,0.53) |
| TCK-1009 | config | config | ✓ | ✓ | TCK-1025(con,0.61), TCK-1024(bug,0.59), TCK-1005(ope,0.56), TCK-1013(ope,0.53), TCK-1018(ope,0.53) |
| TCK-1010 | config | config | ✓ | ✓ | TCK-1023(ope,0.45), TCK-1025(con,0.43), TCK-1001(con,0.42), TCK-1013(ope,0.41), TCK-1009(con,0.41) |
| TCK-1011 | bug | bug | ✓ | ✓ | TCK-1022(bug,0.55), TCK-1023(ope,0.54), TCK-1001(con,0.50), TCK-1026(bug,0.46), TCK-1008(bug,0.46) |
| TCK-1012 | bug | bug | ✓ | ✓ | TCK-1002(bug,0.52), TCK-1019(bug,0.48), TCK-1008(bug,0.42), TCK-1014(bug,0.41), TCK-1018(ope,0.41) |
| TCK-1013 | operacion | operacion | ✓ | ✓ | TCK-1018(ope,0.58), TCK-1023(ope,0.54), TCK-1008(bug,0.53), TCK-1009(con,0.53), TCK-1005(ope,0.52) |
| TCK-1014 | bug | bug | ✓ | ✓ | TCK-1024(bug,0.49), TCK-1005(ope,0.43), TCK-1012(bug,0.41), TCK-1001(con,0.41), TCK-1019(bug,0.40) |
| TCK-1015 | comercial | comercial | ✓ | ✗ | TCK-1006(bug,0.45), TCK-1001(con,0.30), TCK-1012(bug,0.27), TCK-1025(con,0.26), TCK-1008(bug,0.24) |
| TCK-1016 | bug | bug | ✓ | ✓ | TCK-1008(bug,0.39), TCK-1011(bug,0.38), TCK-1002(bug,0.38), TCK-1019(bug,0.36), TCK-1023(ope,0.35) |
| TCK-1017 | bug | bug | ✓ | ✓ | TCK-1004(bug,0.77), TCK-1025(con,0.40), TCK-1010(con,0.39), TCK-1020(con,0.39), TCK-1019(bug,0.38) |
| TCK-1018 | operacion | operacion | ✓ | ✓ | TCK-1013(ope,0.58), TCK-1002(bug,0.57), TCK-1008(bug,0.55), TCK-1005(ope,0.54), TCK-1007(con,0.54) |
| TCK-1019 | bug | bug | ✓ | ✓ | TCK-1002(bug,0.63), TCK-1005(ope,0.55), TCK-1007(con,0.54), TCK-1008(bug,0.49), TCK-1012(bug,0.48) |
| TCK-1020 | config | config | ✓ | ✓ | TCK-1007(con,0.45), TCK-1008(bug,0.45), TCK-1025(con,0.43), TCK-1003(con,0.40), TCK-1017(bug,0.39) |
| TCK-1021 | none | none | ✓ | ✗ | TCK-1006(bug,0.21), TCK-1008(bug,0.18), TCK-1013(ope,0.16), TCK-1017(bug,0.16), TCK-1010(con,0.14) |
| TCK-1022 | bug | bug | ✓ | ✓ | TCK-1011(bug,0.55), TCK-1006(bug,0.55), TCK-1018(ope,0.48), TCK-1013(ope,0.47), TCK-1023(ope,0.46) |
| TCK-1023 | operacion | config | ✗ | ✓ | TCK-1008(bug,0.59), TCK-1002(bug,0.57), TCK-1013(ope,0.54), TCK-1011(bug,0.54), TCK-1018(ope,0.52) |
| TCK-1024 | bug | config | ✗ | ✓ | TCK-1009(con,0.59), TCK-1014(bug,0.49), TCK-1003(con,0.44), TCK-1025(con,0.43), TCK-1013(ope,0.39) |
| TCK-1025 | config | config | ✓ | ✓ | TCK-1009(con,0.61), TCK-1007(con,0.61), TCK-1001(con,0.58), TCK-1008(bug,0.53), TCK-1018(ope,0.50) |
| TCK-1026 | bug | bug | ✓ | ✓ | TCK-1011(bug,0.46), TCK-1001(con,0.46), TCK-1007(con,0.43), TCK-1025(con,0.41), TCK-1002(bug,0.40) |

## Analisis de errores

### TCK-1008 — gold=bug pred=none
- Razonamiento: Customer follow-up on previous bug ticket ORD-77145; no new evidence of system failure or actionable issue.
- Recuperados ({'config': 1, 'operacion': 3, 'bug': 1}):
  - TCK-1002 [bug] sim=0.6713
  - TCK-1023 [operacion] sim=0.5877
  - TCK-1005 [operacion] sim=0.583
  - TCK-1018 [operacion] sim=0.5466
  - TCK-1025 [config] sim=0.5339
- **El gold estaba en los recuperados** pero el modelo predijo mal → problema del LLM, no de recuperacion.

### TCK-1023 — gold=operacion pred=config
- Razonamiento: El sistema no incluyo la orden en el lote de ganancias porque se entrego despues del cutoff configurado, comportamiento 
- Recuperados ({'operacion': 2, 'bug': 3}):
  - TCK-1008 [bug] sim=0.5877
  - TCK-1002 [bug] sim=0.5655
  - TCK-1013 [operacion] sim=0.5408
  - TCK-1011 [bug] sim=0.5371
  - TCK-1018 [operacion] sim=0.5157
- **El gold estaba en los recuperados** pero el modelo predijo mal → problema del LLM, no de recuperacion.

### TCK-1024 — gold=bug pred=config
- Razonamiento: timezone config error: UTC instead of America/Santiago causes all restaurants shown closed.
- Recuperados ({'config': 3, 'operacion': 1, 'bug': 1}):
  - TCK-1009 [config] sim=0.5941
  - TCK-1014 [bug] sim=0.4914
  - TCK-1003 [config] sim=0.4414
  - TCK-1025 [config] sim=0.4303
  - TCK-1013 [operacion] sim=0.3922
- **El gold estaba en los recuperados** pero el modelo predijo mal → problema del LLM, no de recuperacion.

## Interpretacion

La recuperacion por embeddings encontro tickets con la misma etiqueta golden en el top-5 para 24/26 (92%) de los tickets. Cuando la etiqueta correcta esta en los recuperados y el modelo aun falla, el problema es del LLM (no razona bien con buenos ejemplos). Cuando la etiqueta correcta no esta en los recuperados, el problema es de recuperacion (los embeddings no capturan la similitud relevante).