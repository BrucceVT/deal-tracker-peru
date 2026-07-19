# Deal Tracker Perú — Contexto del proyecto

Rastreador de ofertas tech en retailers peruanos (Falabella, Ripley, Plaza Vea, Oechsle).
Scrapea precios → evalúa con motor de señales → alerta por Discord/Telegram/WebPush.

## ⚡ Economía de tokens (reglas para el agente)

1. **Lee `docs/PLAN.md` ANTES de explorar código** — contiene el plan por fases, bugs conocidos y decisiones ya tomadas. No re-derivar nada de eso.
2. **Usa `TaskList`** al inicio de sesión: las tareas #1-#12 ya describen el trabajo pendiente con archivos y líneas exactas. No crear tareas duplicadas.
3. **No releer archivos completos** — el mapa de abajo dice qué hay en cada uno. Leer solo la sección necesaria (usa `offset`/`limit` o Grep).
4. **No usar subagentes** para búsquedas en este proyecto: son ~18 archivos, Grep directo basta.
5. Respuestas al usuario en **español**, concisas.

## Mapa del proyecto

| Archivo | Qué hace | Notas |
|---|---|---|
| `main.py` | Loop infinito o `--once`: scan → evaluate → notify | `seen_urls` por-pasada (fix #1). `--once` probado en vivo (tarea #7, completa) |
| `config.yaml` | Tiendas, keywords, umbrales, pesos, notificaciones, `exclude_keywords` | Se recarga en caliente cada ciclo. `price_ceiling` ahora es `{floor, ceiling}` por categoría |
| `core/deal_engine.py` | Score de 4 señales, `evaluate()` | Bugs #2 y #3 corregidos (2026-07-19): historial ya no incluye el precio actual, rango floor/ceiling + exclude_keywords + match por palabra completa |
| `core/storage.py` | SQLite (`data/deals.db`): products, price_history, alerts_sent, push_subscriptions | `upsert_product_price` se dividió en `get_or_create_product` + `record_price_point` (fix #2). Dedupe de alertas con tolerancia de float (fix #4) |
| `tests/` | 16 tests pytest (deal_engine + storage) | `python -m pytest tests/ -v` — protege los fixes de F1 |
| `scrapers/types.py` | `ScrapedProduct`, `parse_price_pe()` — SIN Playwright | Separado a propósito para que scrapers API-only no carguen Chromium |
| `scrapers/base.py` | `BaseScraper` con Playwright headless, browser persistente por instancia | `wait_for_selector` usa `state="attached"` (no "visible" default) — importante si agregas selectores nuevos |
| `scrapers/falabella.py` | Parsea `__NEXT_DATA__` (SSR de Next.js) con httpx puro, SIN Playwright | Cloudflare deja pasar el GET plano. Paginación `?page=N`. Ya no usa selectores CSS |
| `scrapers/ripley.py` | Playwright (Cloudflare bloquea GET plano, 403 confirmado) + parsea `__NEXT_DATA__.findabilityProps` | URL real del producto se empareja por `pos=N` del DOM, no viene en el JSON |
| `scrapers/vtex_api.py` | `VtexApiScraper`: API JSON pública de VTEX (httpx, sin Playwright) | VTEX responde **206**, no 200, al paginar — ya corregido |
| `scrapers/{plazavea,oechsle}.py` | Subclases de 3 líneas de `VtexApiScraper` | — |
| **Nota general scrapers** | 3 de 4 tiendas (Falabella + las 2 VTEX) NO usan Playwright | Solo Ripley necesita browser real — gran ahorro de minutos en CI |
| `notifiers/{discord,telegram,webpush}.py` | Envío de alertas | Completos; webpush bloquea event loop (tarea #9) |
| `web/app.py` | FastAPI: dashboard + API + push subscribe | `on_event` deprecado (tarea #10) |
| `web/static/` | PWA: index.html, sw.js, manifest | JS del dashboard y sw.js incompletos (tareas #8, #9) |

## Decisiones tomadas (no re-discutir)

- **Hosting: GitHub Actions** (decisión del usuario). Cron cada 15 min en minutos desfasados (ej. `7,22,37,52`), modo `--once`, DB persistida en rama `data`, secretos en GitHub Secrets. Limitación aceptada: cron best-effort (retrasos 5-30 min), sin servidor persistente → **Discord es el canal principal** (decisión del usuario, 2026-07-19), Telegram queda como secundario/opcional, web push solo aplicaría en un futuro VPS.
- **Plaza Vea y Oechsle**: usar API pública VTEX `GET {base}/api/catalog_system/pub/products/search/{cat}?_from=0&_to=49` (JSON, sin auth, sin Playwright) en vez de HTML.
- **Riesgo a validar temprano**: IPs de GitHub runners pueden estar bloqueadas por Falabella/Ripley (Akamai). Probar run manual antes de invertir en esos scrapers.

## Comandos

```bash
venv/Scripts/activate            # Windows
pip install -r requirements.txt && playwright install chromium
python main.py                   # tracker (loop)
uvicorn web.app:app --port 8000  # dashboard
python -m pytest tests/ -q       # tests (desde tarea #4)
```

## Convenciones

- Python 3.11+, async/await en scrapers y notifiers, type hints estilo `float | None`.
- Comentarios y docstrings en español.
- Nunca commitear `data/deals.db` a main (solo a la rama `data` desde CI) ni llaves/tokens en `config.yaml` — en CI van por env vars/Secrets.
