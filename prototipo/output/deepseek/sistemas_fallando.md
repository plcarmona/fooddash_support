# Sistemas con bugs activos

Total de tickets clasificados como **bug**: 13
Bugs conocidos recurrentes: **9** · Bugs nuevos: **4**
Sistemas/componentes afectados: **13**

## Bugs recurrentes (agrupados por `known_bug_id`)

Tickets que matchean el mismo bug en el registro. Esto es la correlacion de causa raiz: usuarios distintos, pedidos distintos, mismo bug subyacente.

### `BUG-002` — Doble cobro por reutilizacion de idempotency_key en reintentos
**Severidad:** critical · **Estado:** open · **Equipo:** Pagos · **Tickets (1):** TCK-1022

- **TCK-1022**: El sistema procesó dos pagos exitosos debido a idempotency_key_reused: fallo de idempotencia en Payment Service.
- **Workaround:** Reembolso automatico del segundo cobro (attempt id=B). Escalar a Pagos para conciliacion.

### `BUG-006` — availability_service con tz_config=UTC muestra todos los restaurantes cerrados en CL
**Severidad:** critical · **Estado:** open · **Equipo:** Catalogo / Plataforma · **Tickets (1):** TCK-1024

- **TCK-1024**: tz_config=UTC when expected America/Santiago causes all restaurants to show as closed: bug masivo de configuración de zona horaria.
- **Workaround:** Hotfix de configuracion: setear tz_config=America/Santiago en el servicio. Incidente activo.

### `BUG-008` — delivery_status acepta DELIVERED sin validar geofencing (courier lejos del cliente)
**Severidad:** high · **Estado:** open · **Equipo:** Logistica / Backend · **Tickets (1):** TCK-1002

- **TCK-1002**: status=DELIVERED con distance_m=780 > 200: validación de geocerca ausente, defecto de plataforma.
- **Workaround:** Reembolsar al cliente. Investigar la entrega: si el courier marco a >200m, marcar como incidente de logica.

### `BUG-001` — Crash NullPointerException al abrir carrito en Android 9 / app 5.2.8
**Severidad:** high · **Estado:** investigating · **Equipo:** Mobile · **Tickets (1):** TCK-1004

- **TCK-1004**: Crash con stacktrace NullPointerException en CartRenderer: defecto de codigo en la app.
- **Workaround:** Sugerir al usuario actualizar a 5.3.0 (donde no se reproduce). Forzar upgrade.

### `INC-001` — Degradacion del api_gateway (p95 muy por sobre baseline) en cl-central
**Severidad:** high · **Estado:** investigating · **Equipo:** Plataforma / SRE · **Tickets (1):** TCK-1014

- **TCK-1014**: p95_latency_ms=4200, muy alto comparado con linea base de 650ms: rendimiento degradado es un bug de plataforma.
- **Workaround:** Incidente activo en Plataforma. Monitorear. Comunicar degradacion a usuarios via banner.

### `BUG-004` — Proveedor SMS sms_gw_2 no alcanza a ciertos carriers (carrier_unreachable)
**Severidad:** high · **Estado:** mitigated · **Equipo:** Cuentas / Plataforma · **Tickets (1):** TCK-1016

- **TCK-1016**: El gateway SMS fallo con carrier_unreachable y todos los reintentos fallaron: es un fallo tecnico del servicio de envio de OTP.
- **Workaround:** Forzar fallback a sms_gw_1 o canal WhatsApp para OTP. Retry con backoff.

### `BUG-007` — Pantalla de confirmacion web en blanco por js_error en build web-5.3.0
**Severidad:** high · **Estado:** investigating · **Equipo:** Web Frontend · **Tickets (1):** TCK-1026

- **TCK-1026**: frontend_error con js_error en pantalla de confirmacion post-pago: la plataforma fallo al mostrar la confirmacion, generando incertidumbre. Defecto del frontend.
- **Workaround:** El pago SI se proceso: confirmar al cliente por email/WhatsApp que el pedido existe. Evitar doble pago.

### `BUG-009` — Geocoding acepta resultados de baja confianza (<0.6) sin alertar al usuario
**Severidad:** medium · **Estado:** open · **Equipo:** Mapas · **Tickets (1):** TCK-1012

- **TCK-1012**: App used low-confidence geocode (0.31) leading to wrong address: validation missing, platform defect.
- **Workaround:** Pedir al usuario que confirme la direccion manualmente. Re-geocodificar con entrada mas especifica.

### `BUG-005` — courier_location_stream se congela en versiones de courier app <= 2.9.x
**Severidad:** medium · **Estado:** open · **Equipo:** Logistica Movil · **Tickets (1):** TCK-1019

- **TCK-1019**: gap_s=1250 indica congelamiento del stream de ubicacion, probable bug en courier app v2.9.4.
- **Workaround:** Forzar upgrade de la courier app a 3.1.0+. Reiniciar el stream manualmente.

## Bugs nuevos 🆕 (no presentes en el registro)

### `Payment System` — TCK-1006 — severidad **high** 🆕
- Sospecha de doble cobro: segun regla 4, es bug aunque no haya logs.
- Hipótesis causa raíz: Duplicate payment processing due to network retry or lack of idempotency in payment API
- Siguientes pasos: Investigate payment logs for duplicate requests; check idempotency keys; if confirmed, issue refund and implement fix to prevent recurrence.

### `delivery_tracking` — TCK-1008 — severidad **high** 🆕
- El usuario reporta que el pedido fue marcado como entregado pero no recibido, lo que sugiere un posible fallo de plataforma (validacion de geocerca ausente). Sin logs, la sospecha fundada del usuario es suficiente para clasificar como bug.
- Hipótesis causa raíz: Possible geofencing validation failure or driver prematurely marking order as delivered
- Siguientes pasos: Investigate order ORD-77145 logs, check driver GPS coordinates at delivery time, contact customer and driver for details

### `order_service` — TCK-1011 — severidad **high** 🆕
- Payment succeeded but order creation failed due to timeout from inventory_service, leaving an inconsistent state (charged but no order). This is a platform bug.
- Hipótesis causa raíz: Timeout from inventory_service during order creation after payment success leads to inconsistent state without compensation/rollback.
- Siguientes pasos: Investigate order creation flow to implement idempotency and rollback mechanism for payment if order fails. Additionally, manually refund the affected user and check if similar cases exist.

### `android_app` — TCK-1017 — severidad **critical** 🆕
- El usuario reporta que el mismo problema del carrito sigue ocurriendo, confirmado previamente como bug con NullPointerException.
- Hipótesis causa raíz: NullPointerException en la lógica de inicialización o actualización del carrito en Android 5.3.0
- Siguientes pasos: Verificar si la corrección del ticket anterior fue publicada; si no, priorizar el parche y lanzar una actualización; si ya existe, verificar la versión de la app del usuario y sugerir actualización.

## Resumen por sistema

| # | Sistema | Severidad | Tickets | Bug conocido | Estado | Equipo |
|---|---------|-----------|---------|--------------|--------|--------|
| 1 | `delivery-platform` | **critical** | TCK-1002 | BUG-008 | open | Logistica / Backend |
| 2 | `api_gateway` | **critical** | TCK-1014 | INC-001 | investigating | Plataforma / SRE |
| 3 | `notification_service` | **critical** | TCK-1016 | BUG-004 | mitigated | Cuentas / Plataforma |
| 4 | `android_app` | **critical** | TCK-1017 | **NUEVO** 🆕 | — | — |
| 5 | `Payment Service` | **critical** | TCK-1022 | BUG-002 | open | Pagos |
| 6 | `availability_service` | **critical** | TCK-1024 | BUG-006 | open | Catalogo / Plataforma |
| 7 | `android-app-cart` | **high** | TCK-1004 | BUG-001 | investigating | Mobile |
| 8 | `Payment System` | **high** | TCK-1006 | **NUEVO** 🆕 | — | — |
| 9 | `delivery_tracking` | **high** | TCK-1008 | **NUEVO** 🆕 | — | — |
| 10 | `order_service` | **high** | TCK-1011 | **NUEVO** 🆕 | — | — |
| 11 | `mapping_geocoding` | **high** | TCK-1012 | BUG-009 | open | Mapas |
| 12 | `courier_app` | **high** | TCK-1019 | BUG-005 | open | Logistica Movil |
| 13 | `web_frontend` | **medium** | TCK-1026 | BUG-007 | investigating | Web Frontend |

## Detalle por sistema

### `delivery-platform` — severidad **critical**
- **TCK-1002**: status=DELIVERED con distance_m=780 > 200: validación de geocerca ausente, defecto de plataforma.
  - Hipótesis causa raíz: Missing geofence validation allowing delivery confirmation when courier is far from customer's address
  - Siguientes pasos: Implement geofence check (e.g., within 200m) before allowing courier to mark order as delivered, and retroactively audit orders with large distance discrepancies.
  - Bug conocido: `BUG-008` — delivery_status acepta DELIVERED sin validar geofencing (courier lejos del cliente)
    - Estado: open | Severidad: high | Equipo: Logistica / Backend
    - Workaround: Reembolsar al cliente. Investigar la entrega: si el courier marco a >200m, marcar como incidente de logica.

### `api_gateway` — severidad **critical**
- **TCK-1014**: p95_latency_ms=4200, muy alto comparado con linea base de 650ms: rendimiento degradado es un bug de plataforma.
  - Hipótesis causa raíz: High p95 latency likely due to backend service degradation or insufficient capacity.
  - Siguientes pasos: Investigate backend services, check for resource bottlenecks, and consider scaling.
  - Bug conocido: `INC-001` — Degradacion del api_gateway (p95 muy por sobre baseline) en cl-central
    - Estado: investigating | Severidad: high | Equipo: Plataforma / SRE
    - Workaround: Incidente activo en Plataforma. Monitorear. Comunicar degradacion a usuarios via banner.

### `notification_service` — severidad **critical**
- **TCK-1016**: El gateway SMS fallo con carrier_unreachable y todos los reintentos fallaron: es un fallo tecnico del servicio de envio de OTP.
  - Hipótesis causa raíz: SMS gateway provider returned carrier_unreachable for the user's carrier, and all retries failed, indicating a potential carrier-side outage or misconfiguration.
  - Siguientes pasos: Check SMS provider status for the specific carrier, review if other users are affected, consider fallback to voice OTP or alternative SMS provider, and escalate to provider support if needed.
  - Bug conocido: `BUG-004` — Proveedor SMS sms_gw_2 no alcanza a ciertos carriers (carrier_unreachable)
    - Estado: mitigated | Severidad: high | Equipo: Cuentas / Plataforma
    - Workaround: Forzar fallback a sms_gw_1 o canal WhatsApp para OTP. Retry con backoff.

### `android_app` — severidad **critical**
- **TCK-1017**: El usuario reporta que el mismo problema del carrito sigue ocurriendo, confirmado previamente como bug con NullPointerException.
  - Hipótesis causa raíz: NullPointerException en la lógica de inicialización o actualización del carrito en Android 5.3.0
  - Siguientes pasos: Verificar si la corrección del ticket anterior fue publicada; si no, priorizar el parche y lanzar una actualización; si ya existe, verificar la versión de la app del usuario y sugerir actualización.
  - 🆕 **Bug no presente en el registro**: alta prioridad, registrar y investigar.

### `Payment Service` — severidad **critical**
- **TCK-1022**: El sistema procesó dos pagos exitosos debido a idempotency_key_reused: fallo de idempotencia en Payment Service.
  - Hipótesis causa raíz: Idempotency key not properly enforced, allowing duplicate payment processing
  - Siguientes pasos: Investigate idempotency key generation and validation logic in Payment Service; add unique constraint on idempotency key; review payment flow for race conditions.
  - Bug conocido: `BUG-002` — Doble cobro por reutilizacion de idempotency_key en reintentos
    - Estado: open | Severidad: critical | Equipo: Pagos
    - Workaround: Reembolso automatico del segundo cobro (attempt id=B). Escalar a Pagos para conciliacion.

### `availability_service` — severidad **critical**
- **TCK-1024**: tz_config=UTC when expected America/Santiago causes all restaurants to show as closed: bug masivo de configuración de zona horaria.
  - Hipótesis causa raíz: Time zone configuration incorrectly set to UTC instead of America/Santiago for the Santiago region in the availability service, causing all restaurants to appear closed.
  - Siguientes pasos: Immediately correct the time zone configuration for Santiago to America/Santiago, verify with a test query, and deploy the fix. Also audit other regions for similar misconfigurations.
  - Bug conocido: `BUG-006` — availability_service con tz_config=UTC muestra todos los restaurantes cerrados en CL
    - Estado: open | Severidad: critical | Equipo: Catalogo / Plataforma
    - Workaround: Hotfix de configuracion: setear tz_config=America/Santiago en el servicio. Incidente activo.

### `android-app-cart` — severidad **high**
- **TCK-1004**: Crash con stacktrace NullPointerException en CartRenderer: defecto de codigo en la app.
  - Hipótesis causa raíz: Null pointer en CartRenderer por falta de inicialización de un objeto en Android 9
  - Siguientes pasos: Reproducir en dispositivo con Android 9, inspeccionar CartRenderer línea 88 y agregar null-safety
  - Bug conocido: `BUG-001` — Crash NullPointerException al abrir carrito en Android 9 / app 5.2.8
    - Estado: investigating | Severidad: high | Equipo: Mobile
    - Workaround: Sugerir al usuario actualizar a 5.3.0 (donde no se reproduce). Forzar upgrade.

### `Payment System` — severidad **high**
- **TCK-1006**: Sospecha de doble cobro: segun regla 4, es bug aunque no haya logs.
  - Hipótesis causa raíz: Duplicate payment processing due to network retry or lack of idempotency in payment API
  - Siguientes pasos: Investigate payment logs for duplicate requests; check idempotency keys; if confirmed, issue refund and implement fix to prevent recurrence.
  - 🆕 **Bug no presente en el registro**: alta prioridad, registrar y investigar.

### `delivery_tracking` — severidad **high**
- **TCK-1008**: El usuario reporta que el pedido fue marcado como entregado pero no recibido, lo que sugiere un posible fallo de plataforma (validacion de geocerca ausente). Sin logs, la sospecha fundada del usuario es suficiente para clasificar como bug.
  - Hipótesis causa raíz: Possible geofencing validation failure or driver prematurely marking order as delivered
  - Siguientes pasos: Investigate order ORD-77145 logs, check driver GPS coordinates at delivery time, contact customer and driver for details
  - 🆕 **Bug no presente en el registro**: alta prioridad, registrar y investigar.

### `order_service` — severidad **high**
- **TCK-1011**: Payment succeeded but order creation failed due to timeout from inventory_service, leaving an inconsistent state (charged but no order). This is a platform bug.
  - Hipótesis causa raíz: Timeout from inventory_service during order creation after payment success leads to inconsistent state without compensation/rollback.
  - Siguientes pasos: Investigate order creation flow to implement idempotency and rollback mechanism for payment if order fails. Additionally, manually refund the affected user and check if similar cases exist.
  - 🆕 **Bug no presente en el registro**: alta prioridad, registrar y investigar.

### `mapping_geocoding` — severidad **high**
- **TCK-1012**: App used low-confidence geocode (0.31) leading to wrong address: validation missing, platform defect.
  - Hipótesis causa raíz: Low-confidence geocode (0.31) accepted without validation, leading to incorrect address mapping.
  - Siguientes pasos: Investigate and add confidence threshold validation in geocoding pipeline; implement fallback or manual correction prompt for low-confidence results.
  - Bug conocido: `BUG-009` — Geocoding acepta resultados de baja confianza (<0.6) sin alertar al usuario
    - Estado: open | Severidad: medium | Equipo: Mapas
    - Workaround: Pedir al usuario que confirme la direccion manualmente. Re-geocodificar con entrada mas especifica.

### `courier_app` — severidad **high**
- **TCK-1019**: gap_s=1250 indica congelamiento del stream de ubicacion, probable bug en courier app v2.9.4.
  - Hipótesis causa raíz: Location streaming failure in courier app v2.9.4 causing extended gaps in location pings.
  - Siguientes pasos: Investigate courier C-901 logs for app crash or network issues; check if other couriers on v2.9.4 have similar gaps; consider rollback or hotfix for location service.
  - Bug conocido: `BUG-005` — courier_location_stream se congela en versiones de courier app <= 2.9.x
    - Estado: open | Severidad: medium | Equipo: Logistica Movil
    - Workaround: Forzar upgrade de la courier app a 3.1.0+. Reiniciar el stream manualmente.

### `web_frontend` — severidad **medium**
- **TCK-1026**: frontend_error con js_error en pantalla de confirmacion post-pago: la plataforma fallo al mostrar la confirmacion, generando incertidumbre. Defecto del frontend.
  - Bug conocido: `BUG-007` — Pantalla de confirmacion web en blanco por js_error en build web-5.3.0
    - Estado: investigating | Severidad: high | Equipo: Web Frontend
    - Workaround: El pago SI se proceso: confirmar al cliente por email/WhatsApp que el pedido existe. Evitar doble pago.
