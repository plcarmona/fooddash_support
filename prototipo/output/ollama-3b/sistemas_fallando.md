# Sistemas con bugs activos

Total de tickets clasificados como **bug**: 10
Bugs conocidos recurrentes: **8** · Bugs nuevos: **2**
Sistemas/componentes afectados: **8**

## Bugs recurrentes (agrupados por `known_bug_id`)

Tickets que matchean el mismo bug en el registro. Esto es la correlacion de causa raiz: usuarios distintos, pedidos distintos, mismo bug subyacente.

### `BUG-003` — order_create falla por timeout de inventory_service post-pago exitoso
**Severidad:** critical · **Estado:** investigating · **Equipo:** Backend / Inventario · **Tickets (1):** TCK-1011

- **TCK-1011**: result=ERROR por timeout en order_create: fallo de proceso detras del pago (timeout en el servicio downstream). NO es bug payment service ni config.
- **Workaround:** Si el pago esta SUCCESS pero no hay order: crear el pedido manualmente y reservar inventario offline. No cobrar de nuevo.

### `BUG-002` — Doble cobro por reutilizacion de idempotency_key en reintentos
**Severidad:** critical · **Estado:** open · **Equipo:** Pagos · **Tickets (1):** TCK-1022

- **TCK-1022**: idempotency_key_reused: fallo de la plataforma que permite cobros duplicados.
- **Workaround:** Reembolso automatico del segundo cobro (attempt id=B). Escalar a Pagos para conciliacion.

### `BUG-006` — availability_service con tz_config=UTC muestra todos los restaurantes cerrados en CL
**Severidad:** critical · **Estado:** open · **Equipo:** Catalogo / Plataforma · **Tickets (1):** TCK-1024

- **TCK-1024**: Todos los restaurantes aparecen cerrados con tz_config=UTC: bug masivo de configuración del servicio.
- **Workaround:** Hotfix de configuracion: setear tz_config=America/Santiago en el servicio. Incidente activo.

### `BUG-008` — delivery_status acepta DELIVERED sin validar geofencing (courier lejos del cliente)
**Severidad:** high · **Estado:** open · **Equipo:** Logistica / Backend · **Tickets (1):** TCK-1002

- **TCK-1002**: El sistema marcó entregado con distancia >200m: defecto de la plataforma.
- **Workaround:** Reembolsar al cliente. Investigar la entrega: si el courier marco a >200m, marcar como incidente de logica.

### `BUG-001` — Crash NullPointerException al abrir carrito en Android 9 / app 5.2.8
**Severidad:** high · **Estado:** investigating · **Equipo:** Mobile · **Tickets (1):** TCK-1004

- **TCK-1004**: Crash con stacktrace en CartRenderer: fallo de codigo en la app movil.
- **Workaround:** Sugerir al usuario actualizar a 5.3.0 (donde no se reproduce). Forzar upgrade.

### `BUG-004` — Proveedor SMS sms_gw_2 no alcanza a ciertos carriers (carrier_unreachable)
**Severidad:** high · **Estado:** mitigated · **Equipo:** Cuentas / Plataforma · **Tickets (1):** TCK-1016

- **TCK-1016**: otp_send result=FAILED con provider_error=carrier_unreachable: fallo de la plataforma en el envio del SMS.
- **Workaround:** Forzar fallback a sms_gw_1 o canal WhatsApp para OTP. Retry con backoff.

### `BUG-007` — Pantalla de confirmacion web en blanco por js_error en build web-5.3.0
**Severidad:** high · **Estado:** investigating · **Equipo:** Web Frontend · **Tickets (1):** TCK-1026

- **TCK-1026**: frontend_error y js_error: fallo en la capa frontend que no permite continuar con el proceso de pago.
- **Workaround:** El pago SI se proceso: confirmar al cliente por email/WhatsApp que el pedido existe. Evitar doble pago.

### `BUG-005` — courier_location_stream se congela en versiones de courier app <= 2.9.x
**Severidad:** medium · **Estado:** open · **Equipo:** Logistica Movil · **Tickets (1):** TCK-1019

- **TCK-1019**: gap_s=1250 (mas de 20 min sin ping) + app_version antigua: el stream de ubicación está congelado, defecto de la courier app.
- **Workaround:** Forzar upgrade de la courier app a 3.1.0+. Reiniciar el stream manualmente.

## Bugs nuevos 🆕 (no presentes en el registro)

### `SYS-1234` — TCK-1006 — severidad **high** 🆕
- Cobro raro: sospecha fundada de fallo en el sistema de cobros.
- Hipótesis causa raíz: El sistema de cobros está fallando y está causando dos cargos en lugar de uno.
- Siguientes pasos: Implementar un workaround para evitar los duplicados hasta que se solucione el problema root cause, revisar logs del sistema de cobro

### `SYS-1234` — TCK-1017 — severidad **high** 🆕
- Crash persistente con misma app version y dispositivo: fallo de plataforma.
- Hipótesis causa raíz: El problema se debe a una incompatibilidad específica de la plataforma Android en dispositivos Samsung.
- Siguientes pasos: Realizar pruebas exhaustivas con diferentes dispositivos Samsung y versiones del sistema operativo para confirmar el problema. Luego, realizar un parche o actualización de software si es necesario.

## Resumen por sistema

| # | Sistema | Severidad | Tickets | Bug conocido | Estado | Equipo |
|---|---------|-----------|---------|--------------|--------|--------|
| 1 | `SYS-LOC-STREAM` | **critical** | TCK-1019 | BUG-005 | open | Logistica Movil |
| 2 | `availability_service` | **critical** | TCK-1024 | BUG-006 | open | Catalogo / Plataforma |
| 3 | `SYS-PLAT-001` | **high** | TCK-1002 | BUG-008 | open | Logistica / Backend |
| 4 | `SD-003` | **high** | TCK-1004 | BUG-001 | investigating | Mobile |
| 5 | `SYS-1234` | **high** | TCK-1006, TCK-1017, TCK-1026 | BUG-007 | investigating | Web Frontend |
| 6 | `payment_order_create` | **high** | TCK-1011 | BUG-003 | investigating | Backend / Inventario |
| 7 | `SYS-FLW-123` | **high** | TCK-1016 | BUG-004 | mitigated | Cuentas / Plataforma |
| 8 | `SYS-PLA-1234` | **high** | TCK-1022 | BUG-002 | open | Pagos |

## Detalle por sistema

### `SYS-LOC-STREAM` — severidad **critical**
- **TCK-1019**: gap_s=1250 (mas de 20 min sin ping) + app_version antigua: el stream de ubicación está congelado, defecto de la courier app.
  - Hipótesis causa raíz: El stream de ubicación está congelado debido a una versión antigua de la app courier y un retraso significativo en el ping.
  - Siguientes pasos: Implementar parche para actualizar la app courier, revisar y optimizar el stream de ubicación para reducir el gap_s y validar cambios en entorno de producción.
  - Bug conocido: `BUG-005` — courier_location_stream se congela en versiones de courier app <= 2.9.x
    - Estado: open | Severidad: medium | Equipo: Logistica Movil
    - Workaround: Forzar upgrade de la courier app a 3.1.0+. Reiniciar el stream manualmente.

### `availability_service` — severidad **critical**
- **TCK-1024**: Todos los restaurantes aparecen cerrados con tz_config=UTC: bug masivo de configuración del servicio.
  - Hipótesis causa raíz: La configuración de zona horaria UTC está causando que todos los restaurantes aparezcan cerrados en la aplicación.
  - Siguientes pasos: Investigar el impacto en otros usuarios, confirmar si es un problema de configuración o software y preparar una actualización para solucionarlo.
  - Bug conocido: `BUG-006` — availability_service con tz_config=UTC muestra todos los restaurantes cerrados en CL
    - Estado: open | Severidad: critical | Equipo: Catalogo / Plataforma
    - Workaround: Hotfix de configuracion: setear tz_config=America/Santiago en el servicio. Incidente activo.

### `SYS-PLAT-001` — severidad **high**
- **TCK-1002**: El sistema marcó entregado con distancia >200m: defecto de la plataforma.
  - Hipótesis causa raíz: El sistema de la plataforma no está correctamente actualizando la distancia entre el punto de entrega y el cliente.
  - Siguientes pasos: Investigar por qué la aplicación móvil no está reflejando adecuadamente la distancia. Realizar pruebas en diferentes entornos para confirmar el problema. Implementar un workaround temporal hasta que se solucione la raíz del problema.
  - Bug conocido: `BUG-008` — delivery_status acepta DELIVERED sin validar geofencing (courier lejos del cliente)
    - Estado: open | Severidad: high | Equipo: Logistica / Backend
    - Workaround: Reembolsar al cliente. Investigar la entrega: si el courier marco a >200m, marcar como incidente de logica.

### `SD-003` — severidad **high**
- **TCK-1004**: Crash con stacktrace en CartRenderer: fallo de codigo en la app movil.
  - Hipótesis causa raíz: El NullPointerException en CartRenderer es causado por un fallo de código en la aplicación móvil.
  - Siguientes pasos: Implementar workaround para evitar el crash, realizar pruebas exhaustivas y reportar al equipo de desarrollo para corrección del bug.
  - Bug conocido: `BUG-001` — Crash NullPointerException al abrir carrito en Android 9 / app 5.2.8
    - Estado: investigating | Severidad: high | Equipo: Mobile
    - Workaround: Sugerir al usuario actualizar a 5.3.0 (donde no se reproduce). Forzar upgrade.

### `SYS-1234` — severidad **high**
- **TCK-1006**: Cobro raro: sospecha fundada de fallo en el sistema de cobros.
  - Hipótesis causa raíz: El sistema de cobros está fallando y está causando dos cargos en lugar de uno.
  - Siguientes pasos: Implementar un workaround para evitar los duplicados hasta que se solucione el problema root cause, revisar logs del sistema de cobro
  - 🆕 **Bug no presente en el registro**: alta prioridad, registrar y investigar.
- **TCK-1017**: Crash persistente con misma app version y dispositivo: fallo de plataforma.
  - Hipótesis causa raíz: El problema se debe a una incompatibilidad específica de la plataforma Android en dispositivos Samsung.
  - Siguientes pasos: Realizar pruebas exhaustivas con diferentes dispositivos Samsung y versiones del sistema operativo para confirmar el problema. Luego, realizar un parche o actualización de software si es necesario.
  - 🆕 **Bug no presente en el registro**: alta prioridad, registrar y investigar.
- **TCK-1026**: frontend_error y js_error: fallo en la capa frontend que no permite continuar con el proceso de pago.
  - Hipótesis causa raíz: El error en la capa frontend impide que se complete correctamente el proceso de pago.
  - Siguientes pasos: Implementar un workaround para evitar pagos no completados y realizar una corrección en la próxima actualización del sistema.
  - Bug conocido: `BUG-007` — Pantalla de confirmacion web en blanco por js_error en build web-5.3.0
    - Estado: investigating | Severidad: high | Equipo: Web Frontend
    - Workaround: El pago SI se proceso: confirmar al cliente por email/WhatsApp que el pedido existe. Evitar doble pago.

### `payment_order_create` — severidad **high**
- **TCK-1011**: result=ERROR por timeout en order_create: fallo de proceso detras del pago (timeout en el servicio downstream). NO es bug payment service ni config.
  - Hipótesis causa raíz: El timeout en el servicio downstream (inventory_service) está causando que la orden no se cree correctamente.
  - Siguientes pasos: Investigar y posiblemente ajustar la configuración del tiempo de espera para el proceso de creación de ordenes, o mejorar la robustez del servicio inventory_service.
  - Bug conocido: `BUG-003` — order_create falla por timeout de inventory_service post-pago exitoso
    - Estado: investigating | Severidad: critical | Equipo: Backend / Inventario
    - Workaround: Si el pago esta SUCCESS pero no hay order: crear el pedido manualmente y reservar inventario offline. No cobrar de nuevo.

### `SYS-FLW-123` — severidad **high**
- **TCK-1016**: otp_send result=FAILED con provider_error=carrier_unreachable: fallo de la plataforma en el envio del SMS.
  - Hipótesis causa raíz: El fallo de envío de SMS está causando problemas para los usuarios que intentan crear una cuenta.
  - Siguientes pasos: Investigar la causa del error en el proveedor de servicios móviles, implementar un fallback alternativo y notificar a los usuarios afectados.
  - Bug conocido: `BUG-004` — Proveedor SMS sms_gw_2 no alcanza a ciertos carriers (carrier_unreachable)
    - Estado: mitigated | Severidad: high | Equipo: Cuentas / Plataforma
    - Workaround: Forzar fallback a sms_gw_1 o canal WhatsApp para OTP. Retry con backoff.

### `SYS-PLA-1234` — severidad **high**
- **TCK-1022**: idempotency_key_reused: fallo de la plataforma que permite cobros duplicados.
  - Hipótesis causa raíz: El uso repetido de un IDempotency Key en la plataforma ha causado duplicidad de cobros.
  - Siguientes pasos: Implementar corrección inmediata y notificar a los usuarios afectados.
  - Bug conocido: `BUG-002` — Doble cobro por reutilizacion de idempotency_key en reintentos
    - Estado: open | Severidad: critical | Equipo: Pagos
    - Workaround: Reembolso automatico del segundo cobro (attempt id=B). Escalar a Pagos para conciliacion.
