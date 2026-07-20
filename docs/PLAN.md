# Plan de finalización — Deal Tracker Perú

> Fuente de verdad del plan. Las tareas #1-#12 del task tracker mapean 1:1 con estas fases.
> Última actualización: 2026-07-19.

## Estado actual (resumen)

**Completo:** storage SQLite, deal_engine (4 señales), notifiers (Discord/Telegram/WebPush), config.yaml, README.
**Incompleto:** frontend PWA (JS del dashboard, sw.js), tests (no existen), deploy.
**Con bugs:** main.py y deal_engine (ver Fase 1). Scrapers frágiles (ver Fase 2).

---

## Fase 1 — Corrección de lógica core (tareas #1-#4) ✅ COMPLETA (2026-07-19)

Bugs encontrados en el análisis del 2026-07-19, en orden de gravedad. Los 4 están
corregidos y cubiertos por 16 tests en `tests/` (`python -m pytest tests/ -v`).

### Bug 1 — `seen_urls` nunca se limpia (main.py:114,127)
El set se crea una vez al arrancar y se comparte entre todos los ciclos. Cada URL se
procesa **una sola vez por vida del proceso**: el historial de precios nunca acumula
más de 1 punto por producto y una bajada de precio posterior jamás se evalúa.
Esto anula en la práctica las señales 3 y 4 del motor.
**Fix:** dedupe por ciclo (el set nace y muere dentro de cada pasada), o dedupe por
(url, ciclo_id).

### Bug 2 — `below_historical_min` no puede activarse (main.py:58-69 + deal_engine.py:59-66)
`upsert_product_price` inserta el precio actual **antes** de que se lea el historial,
así que `price_history` ya incluye el precio actual → `current_price < hist_min` es
siempre falso. El promedio también queda sesgado hacia el precio actual.
**Fix:** leer historial antes de insertar, o excluir el punto más reciente al evaluar.

### Bug 3 — Falsos positivos masivos del price_ceiling (deal_engine.py:52-56 + config.yaml)
`below_price_ceiling` pesa 2.0 y `min_score` es 2.0 → la señal dispara alerta **sola**.
Con matching por substring, "mochila para laptop" a S/59 o "cooler laptop" a S/35
califican como oferta (están bajo el techo de S/1200 de "laptop").
**Fix implementado:**
- `price_ceiling` en config.yaml ahora es `{categoria: {floor, ceiling}}` — solo
  alerta si el precio cae DENTRO del rango (ej. laptop: 300-1200).
- `exclude_keywords` en config.yaml: mochila, funda, case, cooler, cargador,
  cable, adaptador, soporte, teclado, mouse, parlante, repuesto, accesorio…
  Si el título matchea cualquiera, `evaluate()` devuelve is_deal=False de inmediato.
- `_match_category`/exclusión usan match por **palabra completa** (regex `\b`),
  no substring — corrige de paso "tablet" matcheando "tableta gráfica".

### Bug 4 — Igualdad exacta de float en dedupe de alertas (storage.py:109-119)
`price_at_alert = ?` compara floats con igualdad exacta. S/999.9000001 ≠ S/999.90 →
re-alerta. **Fix:** comparar con tolerancia (ABS(price_at_alert - ?) < 0.01) o
redondear a 2 decimales al guardar.

### Mejoras menores de la fase
- `_match_category`: matchear con límites de palabra, no substring puro
  ("tablet" matchea "tableta gráfica").
- Tests pytest para todo lo anterior (tarea #4) — protegen las fases siguientes.

---

### VTEX API para Plaza Vea y Oechsle (tarea #5) ✅ COMPLETA (2026-07-19)
Ambas corren sobre VTEX, que expone API pública sin autenticación. Validado en
vivo contra producción: 199 y 200 productos reales con precio/descuento/stock.

```
GET https://www.plazavea.com.pe/api/catalog_system/pub/products/search/{categoria}?_from=0&_to=49
GET https://www.oechsle.pe/api/catalog_system/pub/products/search/{categoria}?_from=0&_to=49
```

**Bug real encontrado y corregido durante la implementación**: VTEX responde
**206 (Partial Content)**, no 200, cuando se pagina con `_from`/`_to` — un
chequeo `status_code == 200` deja el scraper devolviendo 0 productos en
silencio, sin ningún error visible. Cubierto por test de regresión.

**Implementado:**
- `scrapers/types.py` — nuevo módulo con `ScrapedProduct`/`parse_price_pe` SIN
  importar Playwright (antes vivían en `scrapers/base.py`, que sí lo importa).
  Necesario para que estos scrapers livianos no arrastren un Chromium que no
  usan — impacto directo en el presupuesto de minutos de GitHub Actions.
- `scrapers/vtex_api.py` — `VtexApiScraper` con httpx, paginación en bloques
  de 50 (tope de seguridad 200 productos/categoría).
- `scrapers/plazavea.py` y `scrapers/oechsle.py` reducidos a una subclase de
  3 líneas cada uno.
- `tests/test_vtex_api.py` — 3 tests con `httpx.MockTransport` (sin red real).

### Falabella y Ripley (tarea #6) ✅ COMPLETA (2026-07-19)
Investigado con el navegador real (Network tab + `__NEXT_DATA__`), no con suposiciones.
Corrección importante de la Fase 2 original: la protección no es Akamai, es
**Cloudflare** (`cdn-cgi/challenge-platform`) en ambas tiendas.

- **Falabella**: Next.js con SSR completo — el HTML de un GET plano (sin
  Playwright, sin JS) ya trae el `<script id="__NEXT_DATA__">` con
  `props.pageProps.results`: título, url, precios (`internetPrice`,
  `normalPrice` tachado, `cmrPrice`), imágenes. Cloudflare deja pasar el GET
  plano (no está en modo bloqueo para esta ruta). `scrapers/falabella.py`
  reescrito sobre httpx puro, sin Playwright, con paginación `?page=N`.
  Probado en vivo: 95 y 137 productos reales en las 2 categorías configuradas.
- **Ripley**: la categoría en config.yaml estaba **rota** (`/tecnologia/computo/laptops`
  devolvía 404 — "computo" ya no existe). Corregida a
  `/tecnologia/computacion/laptops` (encontrada vía la API del menú del sitio).
  A diferencia de Falabella, Cloudflare sí bloquea el GET plano de Ripley (403
  confirmado, con y sin headers de navegador) — necesita Playwright. Pero en
  vez de selectores CSS, `scrapers/ripley.py` extrae el mismo tipo de JSON SSR
  (`props.pageProps.findabilityProps.data.products`) del HTML ya renderizado
  por Playwright, y empareja cada producto con su URL real del DOM usando el
  parámetro `pos=N` que Ripley agrega a cada link (posición en la grilla).
  Probado en vivo: 49 productos reales con precio, descuento e imagen.
- **Fix de infraestructura en `scrapers/base.py`**: `wait_for_selector` sin
  `state="attached"` exige que el elemento sea *visible* (default de
  Playwright) — Ripley tiene 49 elementos que matchean el selector pero
  fallan el chequeo de visibilidad (timeout de 20s). Cambiado a
  `state="attached"`: a un scraper solo le importa que el nodo exista en el
  DOM, no que esté en pantalla.
- **Bono**: con el fix de Falabella también se eliminó Playwright de esa
  tienda — de las 4 tiendas, solo Ripley sigue necesitando browser real.
- **Validación end-to-end con las 4 tiendas activas** (`main.py --once`):
  95+137 (falabella) + 49 (ripley) + 199 (plazavea) + 200 (oechsle) productos,
  15 alertas con la regla de combinación de 2+ señales, corrida completa en
  ~17s, proceso terminó solo.

### Rendimiento + modo CI (tarea #7) ✅ COMPLETA (2026-07-19)
- `scrapers/base.py`: `BaseScraper` ahora mantiene un browser+context de Playwright
  persistente por instancia (antes lanzaba Chromium nuevo por categoría). Cada
  `_get_page_html` solo abre una `page` liviana. `close()` debe llamarse al
  terminar — `main.py` lo hace en un `finally` dentro de `scan_store`.
  `VtexApiScraper` tiene un `close()` no-op para la misma interfaz.
- `python main.py --once`: escanea todas las tiendas activas en paralelo
  (`asyncio.gather`) y termina. Probado en vivo con Plaza Vea + Oechsle:
  399 productos, 27 alertas, corrida completa en ~9s, proceso terminó solo.
- **Hallazgo de tuning, iterado dos veces (2026-07-19)**:
  - Iteración 1: con floor/ceiling amplios, ~27/399 productos alertaban solo
    por rango de precio → se exigió combinación de ≥2 señales. Aun así, en
    producción salieron 15 alertas de TVs/tablets de gama baja con descuentos
    comunes de 30-40% (rango + descuento ≥35% = 3.5).
  - Iteración 2 (RECALIBRACIÓN FINAL, pedido explícito del usuario): el
    objetivo son **errores de precio** tipo "laptop buena a S/475", no
    descuentos comunes. Cambios: descuento mínimo 35%→**80%**, caída
    histórica 20%→**60%**, rangos apretados a nivel de error (ceiling POR
    DEBAJO del precio mínimo normal de mercado medido con datos reales:
    laptop 900, TV 300, smartphone 280, tablet 250), reacondicionados y
    chromebooks excluidos (baratos legítimos), y la señal de rango vuelve a
    disparar SOLA (en errores de precio a veces no hay tachado) — se eliminó
    la regla de combinación de la iteración 1. Validado en vivo: **0 alertas
    en 697 productos reales** (antes 15 falsas), y el caso S/475 cubierto por
    test. 29 tests pasando.

---

## Fase 3 — Frontend PWA (tareas #8-#9) ✅ COMPLETA (2026-07-19)

Sorpresa del análisis: `index.html` y los handlers push/notificationclick de
`sw.js` ya estaban completos (el análisis inicial los daba por incompletos).
Lo que realmente faltaba, hecho y probado:
- `sw.js`: caché offline del shell (network-first con fallback a caché;
  `/api/*` siempre va a red) + limpieza de cachés viejos en activate.
- `notifiers/webpush.py`: `webpush()` síncrono → `asyncio.to_thread` (no
  bloquear el event loop); suscripciones caducadas (404/410) se borran de la
  DB vía la nueva `storage.delete_push_subscription()`.
- `web/app.py`: `@app.on_event("startup")` deprecado → lifespan.
- **Probado en vivo con uvicorn + browser**: render de ofertas, auto-refresh
  (segunda llamada a /api/deals confirmada en logs), 0 errores de consola.
  `.claude/launch.json` creado para levantar el dashboard con preview.
- El flujo completo de push queda sin probar end-to-end (requiere llaves
  VAPID + HTTPS + servidor persistente = futuro VPS); el código está listo.

## Fase 4 — Validación end-to-end local (tarea #10) ✅ COMPLETA (2026-07-19)

Validado con webhook de Discord real del usuario, sin datos simulados:
1. `main.py --once` con las 4 tiendas → 497 productos reales, 15 ofertas
   detectadas por el deal_engine (regla de combinación de F2 en acción).
2. **15/15 notificaciones a Discord confirmadas** (HTTP 204 en cada POST +
   confirmación visual del usuario en su canal).
3. Segunda pasada inmediata → **0 notificaciones, 0 líneas "OFERTA:"** —
   `was_alert_sent_recently` bloquea el spam correctamente.
4. Corrida completa (scraping de 4 tiendas + evaluación + 15 notificaciones
   reales) en ~20s.

Pendiente (menor, no bloqueante): dashboard en localhost:8000 y modernizar
`web/app.py` (`@app.on_event` → lifespan) — se hará junto con F3.

---

## Fase 5 — Producción en GitHub Actions (tareas #11-#12)

**Decisión del usuario: GitHub Actions.** Evaluación: viable con adaptaciones.

### Limitaciones conocidas (aceptadas)
| Limitación | Impacto | Mitigación |
|---|---|---|
| Cron mínimo 5 min, best-effort, retrasos 5-30 min típicos (a veces 60+) | No caza errores de precio de minutos | Cron cada 15 min en minutos desfasados (`7,22,37,52 * * * *`) — evitar :00/:30 |
| Sin servidor persistente | No hay dashboard FastAPI ni endpoint de push subscribe | **Discord como canal principal** (Telegram secundario); dashboard estático en Pages |
| Runner efímero, disco no persiste | La DB se pierde entre runs | Commit de `data/deals.db` a rama huérfana `data` (mejor que actions/cache, que expira a los 7 días) |
| IPs de datacenter | Cloudflare (no Akamai, corregido 2026-07-19) puede bloquear | Falabella y las VTEX ya no dependen de esto (sin Playwright). Solo Ripley usa browser — validar con run manual si Cloudflare bloquea datacenter IPs además del fingerprint TLS |
| Límite 2000 min/mes (plan free) | Con Playwright solo para Ripley (no las otras 3), el run baja de ~2min a ~15-20s para 3/4 tiendas + ~10s de Ripley ≈ bien dentro del presupuesto incluso a 15 min de intervalo | Confirmado en vivo: corrida completa de las 4 tiendas en ~17s |

### Workflow (`.github/workflows/scan.yml`) ✅ COMPLETO (2026-07-19), pendiente de deploy
1. `schedule: cron '7,22,37,52 * * * *'` + `workflow_dispatch` (run manual).
2. Setup Python 3.12 + `pip install -r requirements.txt` (cache de pip).
3. Cache de los browsers de Playwright (`~/.cache/ms-playwright`, keyed por
   requirements.txt) — solo Ripley necesita Chromium; con caché el paso es
   casi instantáneo en runs subsecuentes.
4. Restaura `data/deals.db` desde la rama `data` con `git show origin/data:data/deals.db`
   (si la rama no existe todavía, arranca con DB vacía — `storage.init_db()`
   la crea).
5. `python main.py --once` con secretos por env: `DISCORD_WEBHOOK_URL` (canal
   principal), `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` (secundario, opcional).
   `main.py::_apply_env_overrides()` (implementado 2026-07-19) les da
   prioridad sobre `config.yaml` y activa el canal automáticamente si el
   secreto está presente. Cubierto por 3 tests.
6. Commit + push de `data/deals.db` a la rama `data` vía `git worktree`
   (bootstrap automático de la rama huérfana si no existe todavía).
7. (Tarea #12, opcional) Generar dashboard estático desde `recent_deals()` y
   publicar a GitHub Pages.

**Estado del deploy: EN PRODUCCIÓN (2026-07-19).**
- ✅ Repo publicado: https://github.com/BrucceVT/deal-tracker-peru (público).
- ✅ `DISCORD_WEBHOOK_URL` configurado en GitHub Secrets (webhook real del usuario).
- ✅ Primer `workflow_dispatch` manual corrido con éxito (run
  [29704597030](https://github.com/BrucceVT/deal-tracker-peru/actions/runs/29704597030),
  1m41s) — **15 notificaciones reales llegaron al Discord del usuario**,
  confirmadas visualmente.
- ✅ Rama `data` creada automáticamente, `data/deals.db` persistido (192 KB).
- ✅ **El cron ya está activo**: corre solo cada 15 min (`7,22,37,52 * * * *`)
  desde que el workflow quedó registrado — no requiere más acción para seguir
  funcionando.

**Bug de registro del workflow, encontrado y corregido:** GitHub Actions no
indexaba `scan.yml` en absoluto (ni un check-suite se generaba, 404 al
intentar dispatch). Diagnosticado por eliminación con 3 workflows mínimos de
prueba: la causa era `workflow_dispatch: {}` (mapping vacío explícito) en vez
de la forma bare `workflow_dispatch:`. Ambos son YAML válido, pero GitHub
solo indexa la segunda forma. Corregido y confirmado.

**Riesgo de Cloudflare, confirmado con datos reales del primer run:**
| Tienda | Resultado desde el runner de GitHub | 
|---|---|
| Falabella | ✅ 98 + 141 productos — Cloudflare NO bloquea el GET plano |
| Plaza Vea | ✅ 200 productos — API VTEX sin problema |
| Oechsle | ✅ 200 productos — API VTEX sin problema |
| Ripley | ❌ Timeout esperando el selector — Cloudflare bloquea el browser headless desde la IP de datacenter del runner |

El fallo de Ripley no rompe el run (capturado por el try/except de
`scan_store`, main.py sigue con las demás tiendas y termina bien). **Ripley
queda como limitación conocida en producción**: solo trae ofertas cuando el
tracker corre en local/VPS (IP residencial), no desde GitHub Actions. No se
invirtió en workarounds (proxy residencial, etc.) — fuera de alcance por
ahora, documentado para revisitar si se vuelve prioritario.

**Bug adicional encontrado y corregido en el primer run real:** Discord
devolvió `429 Too Many Requests` en 1 de 15 notificaciones (rate limit del
webhook ante ráfaga de alertas simultáneas). `notifiers/discord.py` ahora
reintenta una vez respetando el `Retry-After` de Discord. Cubierto por 3
tests nuevos (`tests/test_discord_notifier.py`).

### Dashboard estático en GitHub Pages (tarea #12) ✅ COMPLETA (2026-07-19)
- `scripts/generate_static_dashboard.py`: HTML autocontenido desde
  `recent_deals()` (mismo diseño oscuro, hora de Lima, estado vacío explicando
  la filosofía de errores de precio).
- `scan.yml`: tras persistir la DB, genera `site/index.html` y lo publica con
  `upload-pages-artifact` + `deploy-pages` (job separado, patrón oficial).
- Pages habilitado en modo workflow vía `gh api`.
- **En vivo y verificado: https://bruccevt.github.io/deal-tracker-peru/**
  (se regenera en cada escaneo, cada ~15 min).
- Nota: las 15 alertas visibles al inicio son historial de la calibración
  antigua (pre-recalibración de errores de precio); las nuevas entradas solo
  serán errores genuinos.

### Si GitHub Actions no alcanza (plan B documentado, no activo)
Oracle Cloud Free Tier (VM gratis 24/7), o Raspberry Pi, o VPS ~$4/mes. El modo
loop de main.py ya funciona para ese caso sin cambios.

---

## Fase 6 — Ampliación de cobertura (tareas #13-#15) ✅ COMPLETA (2026-07-19)

Motivación: el motor tenía rangos de error para TV/celular/tablet/monitor pero
casi solo se escaneaban laptops (~700 productos). Ahora: **~2,300 productos
por escaneo, 1,436 únicos tras el filtro de keywords** en 7 tiendas activas.

### Categorías nuevas (todas validadas en vivo con los scrapers reales)
- Falabella: + TV (cat210477), celulares (cat760706), tablets (cat270476),
  monitores (cat40695). IDs extraídos del HTML de la propia página.
- Plaza Vea: + televisores, celulares, tablets.
- Oechsle: tecnologia → computo + televisores + celulares (mejor cobertura).

### Tiendas nuevas (sondeo VTEX del 2026-07-19)
- **Coolbox, Promart, Metro**: exponen la API pública VTEX → subclases de 3
  líneas de `VtexApiScraper`, activas.
- **Wong**: también VTEX pero deshabilitada por defecto — comparte catálogo
  con Metro (ambos Cencosud) y duplicaría alertas del mismo error.
- Hiraoka: no es VTEX (404). Tottus: 503. Sodimac: plataforma Falabella pero
  la categoría probada devolvió 0 resultados. Los tres descartados por ahora.

### Recalibración del motor tras la red ampliada (2 fuentes de ruido nuevas)
1. **Tablets kids/ultra-baratas** (S/99-250 es precio normal): se quitó el
   rango de error de "tablet" — existen tablets legítimas en todo el espectro
   de precios, ningún rango absoluto distingue error de producto barato. La
   categoría queda cubierta por las señales histórica y de descuento. Además
   exclude_keywords += kids, niños, niñas, básico.
2. **Listas infladas de marketplace** (caso real: "Redmi Pad 2 a S/919,
   antes S/4,600" — descuento falso de 80%): `discount_pct_high` bajó de
   peso 2.0 → 1.5. Ahora es señal de REFUERZO: no dispara sola, necesita
   coincidir con el rango de error o con una caída histórica (que un vendedor
   no puede falsificar). Las ANCLAS que sí disparan solas: rango de error
   absoluto y caída histórica ≥60%.
- Validado en vivo tras la recalibración: **0 alertas en ~2,300 productos**.

### Guardia de fallos del workflow (tarea #15)
`scan.yml` ahora postea al webhook de Discord si el job falla
(`if: failure()`), con link al run — antes un fallo solo generaba un email
de GitHub fácil de ignorar.

---

## Orden de ejecución recomendado

```
F1 (#1→#2→#3→#4)  →  F2 (#5→#7→#6)  →  F4 parcial (#10 con VTEX)
                                     →  F5 (#11: validar IPs YA, luego workflow)
F3 (#8→#9) puede ir en paralelo a F5. #12 al final.
```

Racional: F1 primero porque los bugs invalidan cualquier prueba; #5 antes que #6
porque VTEX es el camino de menor riesgo; validar bloqueo de IPs (#11) temprano
porque puede cambiar el alcance de #6.
