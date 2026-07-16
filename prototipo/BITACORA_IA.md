# Bitácora de uso de IA

## Herramientas usadas

- **Ollama (qwen2.5:3b, granite3.3:latest)**: modelos locales para comparar. Corren en GPU RTX 3060.
- **DeepSeek API (deepseek-v4-flash)**: modelo de razonamiento vía API OpenAI-compatible, seleccionado como ganador.

## Decisiones 100% mías (no de la IA)

1. **El criterio de clasificación bug/config/operación.** Lo definí yo a mano ticket por ticket ANTES de que el agente existiera. La IA no decidió las etiquetas; yo las puse y el agente intenta replicarlas.
2. **5 categorías en vez de 3.** Decidí separar "comercial" y "none" del triángulo del enunciado porque TCK-1015 (renegociar comisión) y TCK-1021 (spam) no encajan en bug/config/operación.
3. **El corte en los casos limítrofes.** TCK-1002 (GPS 780m → bug, no operación), TCK-1007 (BLOCKED policy → config, no operación), TCK-1012 (geocode confidence 0.31 → bug). En cada uno, mi primer instinto fue "operación" y lo corregí al razonarlo mejor.
4. **Usar el golden set como ground truth de evaluación.** Medir agreement es lo que hace que la elección de modelo sea objetiva.
5. **Sin frameworks de agentes.** Escribir el cliente LLM a mano (~150 líneas) en vez de langchain.
6. **El registro de bugs conocidos.** Decidí añadir una base de búsqueda para que el agente diferencie bugs nuevos de recurrentes. Es lo que hace el triaje útil para ingeniería, no solo para soporte.
7. **Selección del modelo final (deepseek-v4-flash).** known-set 100% (prompt completo sobre el set), **híbrido 92.3%** (minimal + solo reglas trazables desde el training set), LOOCV-KNN 84.6% (recuperación por embeddings, prompt mínimo), LOOCV genérico 77–89% (prompt mínimo, few-shot fijo).
8. **Validación cruzada con dos metodologías.** Primero LOOCV genérico (prompt mínimo + 8 pocos-shot fijos balanceados). Luego LOOCV-KNN (recuperación determinística por embeddings snowflake-arctic-embed2, top-5 similares por ticket). El KNN tiene recuperación determinística: no varía entre corridas y encuentra el gold label en el top-5 para el 92% de los tickets. Los 4 errores residuales son de razonamiento del LLM, no de recuperación.
9. **El híbrido como tercer estimador (4º en total).** Decidí construir un punto medio honesto entre el known-set (100%, con leakage) y el LOOCV-KNN (84.6%, sin reglas). Por cada fold LOOCV, el prompt incluye una de las 8 reglas solo si algún ticket del training set la **traza** (misma etiqueta golden + keyword de la regla presente). Las reglas que solo sostenía el ticket held-out se dropean. Resultado: 92.3% (24/26). De los 3 folds donde una regla era única (R2 en 1024, R7 en 1015, R8 en 1021), el modelo resolvió 1015 y 1021 **sin la regla** (desde la definición de categoría) — solo **TCK-1024** cayó. Eso acota la brecha de generalización a un único ticket, en vez de a 4.

## Prompts clave (3-5)

### Prompt 1 — Diseño inicial del criterio
> "Lee estos 26 tickets de FoodDash y clasifícalos en bug técnico / error de configuración / problema de operación. Para cada uno explica tu razonamiento basándote en los system_logs."

Uso: generar la primera pasada de clasificación que después corregí a mano.

### Prompt 2 — System prompt del Router (versión final, después de 2 iteraciones)
> "Eres un agente de triaje de tickets de soporte para FoodDash... REGLA DE ORO: Lee SIEMPRE system_logs ANTES de mirar el subject/body... [criterio completo con 5 categorías y 8 reglas decisionales]"

Uso: es el prompt que recibe el Router. Se afino 2 veces (ver "En qué la IA se equivocó").

### Prompt 3 — Refinamiento del prompt tras el primer run
> "El modelo granite 8B clasifica TCK-1002 como operación en vez de bug. El log muestra status=DELIVERED con distance_m=780 (780m entre courier y cliente). El sistema permitió marcar entregado sin validar geofencing. Refuerza el prompt para que 'aceptar un dato inválido' cuente como bug, e incluye este caso como pocos-shot."

Uso: iteración de fine-tuning del prompt.

### Prompt 4 — Construcción del registro de bugs conocidos
> "Crea un registro JSON de bugs conocidos para FoodDash. Para cada bug: id, título, sistema, severidad, estado, síntomas (tokens de logs), workaround, equipo. Deriva los bugs de los patrones que ves en los 26 tickets, pero escríbelos como si fueran una base de conocimiento interna preexistente con IDs JIRA ficticios."

Uso: poblar `data/known_bugs.json`.

## En qué la IA se equivocó o se quedó corta (y qué corregí yo)

### 1. Divergencia entre clasificación inicial y criterio del operador en 4 tickets
La primera clasificación, al contrastar mi clasificación vs IA, presentó 4 desacuerdos:
- **TCK-1002**: clasificado inicialmente como "operación" (courier se equivocó). El operador lo cataloga como bug: el sistema permitió DELIVERED a 780m. Criterio 
corregido: aceptar un dato inválido (GPS lejos) = bug de validación ausente.
- **TCK-1007**: clasificado como "operación". El operador lo cataloga como config: `BLOCKED reason=<policy>`. Criterio 
corregido: policy que bloquea = config.
- **TCK-1012**: clasificado como "operación" (dirección ambigua). El operador lo cataloga como bug: `confidence=0.31` aceptada sin alertar.
- **TCK-1025**: clasificado como "operación" (política frustrante). El operador lo cataloga como config: `no_cancel_after_cooking`.

De estos 4 casos se derivaron 2 reglas que se codificaron en el prompt: (a) aceptar dato inválido = bug; (b) `BLOCKED reason=<policy>` = config.

### 2. El prompt v1 producía 76.9% en granite (6 desacuerdos)
El modelo sobre-usaba "comercial" y "none" cuando veía menciones de dinero/cupón/ganancias/cierre, ignorando los logs técnicos. **Mi corrección**: estrechar la definición de comercial ("SOLO consultas de política/contratos"), añadir la "REGLA DE ORO" (lee logs antes que subject), y 4 pocos-shot nuevos para los casos donde fallaba.

### 3. El prompt v2 produjo 88.5% en granite pero 92.3% en el 3B
El 8B sobre-generalizó la regla nueva "aceptar dato inválido = bug" a errores humanos (TCK-1013: faltó la bebida; TCK-1018: courier entregó pedido equivocado). **El 3B no cometió ese error**. Hallazgo contraintuitivo: más grande no es siempre mejor. No lo corregí en el 8B porque el 3B ya funcionaba mejor y deepseek ganó con 100%.

### 4. Validación con prompt mínimo
Al reportar 100% de accuracy noté que el prompt se había afinado mirando los 26 tickets: las 8 reglas decisionales y los 9 pocos-shot sintéticos derivan de tickets específicos del set. Implementé LOOCV (leave-one-out) con prompt mínimo (solo defs de categoría, sin reglas hand-craftadas) y few-shot de tickets reales del training set.

Se reportaron tres estimadores que se complementan (ver README para la tabla completa). Adicionalmente, implementé **LOOCV-KNN**: recuperación determinística por embeddings (`snowflake-arctic-embed2`, top-5 más similares) que reemplaza el few-shot genérico por ejemplos relevantes a cada ticket. El LOOCV-KNN (84.6%) tiene recuperación determinística: no varía entre corridas, y el gold label aparece en el top-5 para el 92% de los tickets. Los 4 errores residuales son todos de razonamiento del LLM (el gold estaba en los recuperados), no de recuperación.

Los 4 errores del KNN son casos donde el modelo no infiere el criterio del few-shot solo: validación ausente (TCK-1012), blast radius masivo (TCK-1024), ambigüedad config/operación (TCK-1023, TCK-1010). El análisis detallado está en el README y en `output/deepseek/cv_knn_report.md`.

### 5. Híbrido: separar "brecha honesta" de "fallo de razonamiento"
Para saber cuáles de los 4 errores del KNN eran leakage (la regla estaba afinada para ese ticket) y cuáles eran límites reales del modelo, construí un híbrido: por cada fold, el prompt incluye una regla solo si el training set la traza. Resultado 92.3% (24/26) — recupera TCK-1010 y TCK-1012 (sus reglas R3/R5 se aprenden de tickets hermanos), y deja solo 2 fallos **tipificados**:
- **TCK-1024 (brecha honesta):** su regla R2 (tz masivo) era única del ticket → se dropea → el modelo la ve como config. Único fallo legítimo del LOOCV.
- **TCK-1023 (fallo de razonamiento):** la regla R6 estaba presente (8/8) y el modelo la pisó aplicando la definición de config al cutoff. Límite config/operación ya documentado.

Hallazgo no obvio: aunque R1 sigue listando `tz_config=UTC` como marca BUG, dropear R2 rompe 1024 igual — el modelo necesita el framing explícito "BUG MASIVO" de R2, no le basta el token suelto en R1. Reporte: `output/deepseek/cv_hybrid_report.md`.

## Qué dejó fuera a propósito

- **Correlación de causa raíz para bugs nuevos.** La agregación actual por `known_bug_id` funciona para bugs ya en el registro. Para bugs nuevos (no registrados), la correlación requeriría matching por señales de log (tokens técnicos compartidos) o embeddings de subject+body. Lo anoto como mejora futura.
- **Pipeline async/paralelo.** Los tickets se procesan en serie. Para 26 tickets es instantáneo.
- **Integración con un sistema de tickets real** (SQL, etc.). El prototipo lee un JSON local.
- **Fine-tuning de pesos del modelo.** Se evaluó solo prompting (zero-shot + pocos-shot), no entrenamiento. Para el alcance del caso, prompting bien hecho con deepseek-v4-flash da un rango de 85–100% (LOOCV-KNN a known-set). Con un dataset más grande (cientos de tickets) valdría la pena fine-tunear, pero con N=26 no se justifica.
