# Caso Técnico

**Postulación: AI Solutions Expert · Healthatom**

Este caso busca conocer cómo piensas y cómo resuelves problemas con ayuda de IA. No esperamos una solución perfecta ni un producto terminado: nos interesa tu criterio, tus decisiones y cómo justificas el camino que elegiste. Tienes **2 días** para trabajarlo y luego lo revisaremos juntos en una reunión.

> **Sobre el uso de IA:** queremos que uses IA (ChatGPT, Claude, Copilot, lo que prefieras). Es parte del rol y no es trampa. Pero nos interesa ver tu criterio, no el de la IA: por eso te pediremos una bitácora de cómo la usaste y, en la reunión, te preguntaremos el porqué de tus decisiones. Un buen resultado es aquel donde la IA fue tu copiloto y tú el que decidió el rumbo, no un copy-paste.

## 1. El contexto (ficticio)

**FoodDash** es una app de delivery de comida que opera en varias ciudades. Cada día recibe miles de tickets de soporte de tres tipos de usuarios: **clientes**, **restaurantes** y **repartidores**. Hoy un equipo humano lee cada ticket a mano y trata de entender qué está pasando. Están saturados y las respuestas llegan lentas.

El problema central es que, ante cada ticket, alguien debe determinar la **causa raíz**. En términos generales, suele caer en una de estas familias:

- **Bug técnico:** algo en la plataforma falló.
- **Error de configuración:** alguien configuró algo mal.
- **Problema de efectividad / operación:** nada está "roto", pero la operación no funcionó como debía.

Determinar esto de forma rápida y confiable, y decidir qué hacer con cada ticket, es lo que hoy cuesta caro.

## 2. Tu misión

Diseña (y prototipa de forma ligera) un **agente (o una estructura de varios agentes)** que reciba los tickets entrantes y tome decisiones: qué tipo de problema es, qué tan grave es, qué habría que hacer y a quién escalar. Te entregamos un set de tickets reales-ficticios para que tu prototipo llegue a **ejecutarse** sobre ellos.

## 3. Qué debes entregar

Un repositorio o carpeta con lo siguiente (en español):

1. **Tu criterio.** Explica cómo abordaste el problema y por qué. ¿Qué asumiste? ¿Qué priorizaste? ¿Qué dejaste fuera a propósito? Aquí queremos ver tu forma de pensar.
2. **El algoritmo / arquitectura.** Describe el flujo de tu agente o agentes. Incluye un diagrama (aunque sea simple) y explica qué hace cada parte y cómo se comunican.
3. **Las decisiones de acción.** Para cada tipo de resultado, ¿qué se debería hacer con el ticket?
4. **Cómo decides cuándo algo es un BUG.** Define tu criterio para separar un bug técnico de un error de configuración o de efectividad. No hay una única respuesta correcta: define la tuya y defiéndela.
5. **Análisis técnico de un caso.** Toma al menos 2-3 tickets del set y muestra, paso a paso, cómo tu agente determina si técnicamente ocurrió algo. Explica tu razonamiento.
6. **Los tools del agente.** ¿Qué herramientas debería tener este agente para hacer bien su trabajo? Justifica cada una.
7. **Prototipo funcional.** Algo que efectivamente corra sobre el set de tickets entregado y produzca una salida (clasificación + decisión por ticket). No necesita ser profundo ni bonito; sí necesita ejecutarse. Incluye instrucciones para correrlo.
8. **Bitácora de uso de IA.** Un archivo corto donde cuentes: qué herramientas de IA usaste, 3-5 prompts clave, en qué la IA se equivocó o se quedó corta y qué corregiste tú, y qué decisiones fueron 100% tuyas.

## 4. El set de datos

Te entregamos **26 tickets** en dos formatos equivalentes (usa el que prefieras):

- **tickets.json:** estructurado, ideal para procesar con código.
- **tickets.csv:** el mismo contenido en tabla plana.

Cada ticket trae, cuando aplica: id, fecha, tipo de reportante (cliente/restaurante/repartidor), canal, ciudad, versión de app, plataforma, id de pedido, asunto, cuerpo del mensaje y logs de sistema. No todos los tickets traen todos los campos.

## 5. Reglas del juego y entrega

- **Stack libre:** somos agnósticos a la tecnología. Usa el lenguaje, las APIs y los frameworks que quieras. Solo justifica por qué los elegiste.
- **Usa IA abiertamente** y documéntalo en la bitácora (entregable 8).
- **Tiempo:** 2 días desde que recibes este documento.
- **Entrega:** un link a un repositorio (GitHub/GitLab) o una carpeta comprimida con todo lo anterior.
- **Defensa:** después habrá una reunión (~30-45 min) donde nos mostrarás tu solución y te preguntaremos el porqué de tus decisiones.

> **Cómo evaluamos (para que sepas qué priorizar):** nos importa más la calidad de tu razonamiento y de tus decisiones que la sofisticación del código. Un prototipo simple con criterio claro y bien defendido vale más que uno complejo que no sabes explicar. Sé honesto con lo que no alcanzaste a hacer: eso también suma.
