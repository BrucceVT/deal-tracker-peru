---
name: validate-scrapers
description: Valida rápidamente qué scrapers de tienda devuelven productos reales y cuáles están rotos, sin correr el loop completo ni disparar alertas.
---

# Validar scrapers

Objetivo: saber en <5 min qué tiendas funcionan, sin tocar la DB de producción ni enviar notificaciones.

## Pasos

1. Escribe un script temporal en el scratchpad (NO en el repo) que, por cada tienda habilitada en `config.yaml`, llame `scraper.fetch_category(primera_categoria)` y reporte: nombre de tienda, nº de productos, primeros 3 títulos con precio, o el error/traceback si falla.
2. Ejecútalo con timeout amplio (Playwright tarda; VTEX API no).
3. Reporta en tabla: tienda | estado (✔/✘) | productos | causa probable si falló.

## Diagnóstico por tienda

- **Plaza Vea / Oechsle (VTEX)**: si fallan y aún usan HTML, prueba directo la API:
  `curl "{base_url}/api/catalog_system/pub/products/search/tecnologia?_from=0&_to=9"` — si devuelve JSON, el problema son los selectores HTML y conviene completar la tarea #5.
- **Falabella / Ripley**: si devuelven 0 productos o timeout, probable cambio de selectores o bloqueo anti-bot (Akamai). Verifica primero con `curl -I {url}` si responde 200 o 403.
- Un `TimeoutError` de `wait_for_selector` casi siempre = selector obsoleto, no red.

## Reglas

- NO modificar los scrapers durante la validación — solo diagnosticar y reportar.
- NO bajar `polite_delay` ni martillar las tiendas: 1 categoría por tienda basta.
- Borrar el script temporal al terminar o dejarlo solo en el scratchpad.
