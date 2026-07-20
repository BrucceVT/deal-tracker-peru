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
| `core/deal_engine.py` | Score de 4 señales, `evaluate()` | **Calibrado para ERRORES DE PRECIO, no descuentos comunes** (pedido del usuario 2026-07-19): descuento >=80%, rangos de error bajo el precio mínimo normal de mercado, caída histórica >=60%. Cada señal fuerte dispara sola. Reacondicionados y chromebooks excluidos |
| `core/storage.py` | SQLite (`data/deals.db`): products, price_history, alerts_sent, push_subscriptions | `upsert_product_price` se dividió en `get_or_create_product` + `record_price_point` (fix #2). Dedupe de alertas con tolerancia de float (fix #4) |
| `tests/` | 16 tests pytest (deal_engine + storage) | `python -m pytest tests/ -v` — protege los fixes de F1 |
| `scrapers/types.py` | `ScrapedProduct`, `parse_price_pe()` — SIN Playwright | Separado a propósito para que scrapers API-only no carguen Chromium |
| `scrapers/base.py` | `BaseScraper` con Playwright headless, browser persistente por instancia | `wait_for_selector` usa `state="attached"` (no "visible" default) — importante si agregas selectores nuevos |
| `scrapers/falabella.py` | Parsea `__NEXT_DATA__` (SSR de Next.js) con httpx puro, SIN Playwright | Cloudflare deja pasar el GET plano. Paginación `?page=N`. Ya no usa selectores CSS |
| `scrapers/ripley.py` | Playwright (Cloudflare bloquea GET plano, 403 confirmado) + parsea `__NEXT_DATA__.findabilityProps` | URL real del producto se empareja por `pos=N` del DOM, no viene en el JSON |
| `scrapers/vtex_api.py` | `VtexApiScraper`: API JSON pública de VTEX (httpx, sin Playwright) | VTEX responde **206**, no 200, al paginar — ya corregido |
| `scrapers/{plazavea,oechsle,coolbox,promart,metro,wong}.py` | Subclases de 3 líneas de `VtexApiScraper` | Wong deshabilitada en config (catálogo duplicado con Metro, ambos Cencosud) |
| **Nota general scrapers** | 7 de 8 tiendas NO usan Playwright (Falabella SSR + 6 VTEX) | Solo Ripley necesita browser real. ~2,300 productos/escaneo desde F6 |
| `notifiers/{discord,telegram,webpush}.py` | Envío de alertas | Completos; webpush bloquea event loop (tarea #9) |
| `web/app.py` | FastAPI: dashboard + API + push subscribe | Usa lifespan. Solo corre en local (`/dashboard` de launch.json) o futuro VPS |
| `web/static/` | PWA completa: index.html (render + push), sw.js (push + offline), manifest | Probada en vivo. El push end-to-end requiere VAPID + HTTPS (futuro VPS) |
| `scripts/generate_static_dashboard.py` | Dashboard HTML autocontenido desde la DB | Publicado por CI en https://bruccevt.github.io/deal-tracker-peru/ cada escaneo |

## Decisiones tomadas (no re-discutir)

- **Hosting: GitHub Actions — EN PRODUCCIÓN desde 2026-07-19.** Repo:
  https://github.com/BrucceVT/deal-tracker-peru (público). Cron cada 15 min
  desfasado (`7,22,37,52`), modo `--once`, DB persistida en rama `data`,
  `DISCORD_WEBHOOK_URL` en GitHub Secrets. **Discord es el canal principal**
  (Telegram secundario/opcional, no configurado). El cron corre solo, no
  requiere acción para seguir funcionando.
- **Plaza Vea y Oechsle**: API pública VTEX `GET {base}/api/catalog_system/pub/products/search/{cat}?_from=0&_to=49`. Ojo: VTEX responde 206, no 200.
- **Falabella**: parsea `__NEXT_DATA__` (SSR Next.js) con httpx puro, sin Playwright — confirmado funciona también desde runners de GitHub.
- **Ripley**: SÍ necesita Playwright, y Cloudflare bloquea el browser headless desde la IP de datacenter de GitHub Actions (confirmado en el primer run real). Limitación conocida y aceptada: Ripley solo aporta ofertas cuando el tracker corre en local/VPS, no en CI. No es un bug — el error se captura y el resto del scan sigue normal.
- **`.github/workflows/scan.yml`**: usar `workflow_dispatch:` **bare** (sin `{}`) — un `workflow_dispatch: {}` explícito hace que GitHub Actions NO indexe el workflow en absoluto (ni aparece en la lista, ni genera check-suites), sin ningún mensaje de error visible. Encontrado por eliminación con workflows mínimos de prueba el 2026-07-19.
- **Discord**: reintenta una vez ante 429 (rate limit) respetando `Retry-After` — bug real visto en el primer run (ráfaga de 15 alertas simultáneas disparó el límite del webhook).
- **Calibración anti-ruido (F6, no revertir)**: "tablet" NO tiene rango de error (tablets kids/genéricas son legítimas a cualquier precio); el descuento tachado pesa 1.5 y NO dispara solo (vendedores de marketplace inflan el precio de lista — caso real "Redmi Pad 2 antes S/4,600"); exclude_keywords incluye kids/niños/básico. Anclas que sí disparan solas: rango de error y caída histórica ≥60%.
- **Tiendas descartadas en el sondeo F6**: Hiraoka (no VTEX), Tottus (503), Sodimac (0 resultados), Linio (muerta). No re-sondear sin motivo.

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
