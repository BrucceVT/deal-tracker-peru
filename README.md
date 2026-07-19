# Deal Tracker Perú 🇵🇪

Cazador de **errores de precio** en tecnología (laptops, TVs, celulares,
tablets) en Falabella, Ripley, Plaza Vea y Oechsle. Cuando un producto
aparece a un precio absurdamente bajo — tipo una laptop buena a S/475 —
avisa por Discord en el siguiente escaneo.

**No es un agregador de ofertas**: los descuentos comunes de 30-50% se
ignoran a propósito. Solo alerta ante señales de error genuino.

📱 Dashboard público: **https://bruccevt.github.io/deal-tracker-peru/**

## Cómo decide qué es "un error de precio"

Combina 4 señales en `core/deal_engine.py` (umbrales en `config.yaml`):

1. **Descuento drástico**: ≥80% vs el precio de lista tachado.
2. **Rango de error absoluto**: el precio cae por debajo del mínimo normal
   de mercado de su categoría (ej. una laptop nueva real nunca baja de
   ~S/1,800 — si aparece una entre S/300-900, algo está mal). Esta señal
   dispara sola: en un error de precio la tienda a veces ni muestra tachado.
3. **Mínimo histórico**: es el precio más bajo jamás visto de ESE producto.
4. **Caída histórica drástica**: ≥60% bajo el promedio histórico propio.

El ruido se filtra con `exclude_keywords` (accesorios como "mochila para
laptop", y baratos legítimos como reacondicionados o chromebooks).

## Arquitectura de scraping (sin selectores CSS frágiles)

| Tienda | Método | Playwright |
|---|---|---|
| Falabella | JSON `__NEXT_DATA__` del SSR de Next.js, vía httpx | No |
| Plaza Vea | API pública VTEX (`/api/catalog_system/pub/products/search/`) | No |
| Oechsle | API pública VTEX | No |
| Ripley | JSON `__NEXT_DATA__`, pero Cloudflare exige browser real | Sí |

Nota: VTEX responde `206 Partial Content` al paginar — es normal.

## Producción (GitHub Actions — ya configurado en este repo)

`.github/workflows/scan.yml` corre cada ~15 min:
escanea → evalúa → alerta a Discord → persiste la DB en la rama `data` →
republica el dashboard en GitHub Pages.

Secretos (Settings → Secrets and variables → Actions):
- `DISCORD_WEBHOOK_URL` — requerido (canal principal).
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — opcionales.

Limitaciones conocidas:
- El cron de GitHub es best-effort (retrasos de 5-30 min son normales).
- **Ripley no funciona desde los runners** (Cloudflare bloquea IPs de
  datacenter); solo aporta cuando el tracker corre en local/VPS.
- GitHub desactiva los crons de repos públicos tras 60 días sin actividad —
  llega un email para reactivarlo con un click.

## Correr localmente

```bash
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
playwright install chromium     # solo necesario para Ripley

python main.py --once           # una pasada y termina (lo que corre CI)
python main.py                  # loop continuo (uso local/VPS)

# Dashboard web local (opcional):
uvicorn web.app:app --port 8000

# Tests:
python -m pytest tests/ -v
```

Para recibir alertas en local sin tocar `config.yaml`, exporta
`DISCORD_WEBHOOK_URL` como variable de entorno (tiene prioridad).

## Web Push / PWA (para un futuro VPS)

El frontend en `web/` es una PWA completa con notificaciones push
(suscripción VAPID + service worker con caché offline). Funciona en local,
pero el push end-to-end necesita HTTPS y un servidor persistente — no aplica
al modelo GitHub Actions. Si algún día se migra a un VPS: generar llaves con
`npx web-push generate-vapid-keys`, pegarlas en `config.yaml`, y servir con
Caddy/Nginx + HTTPS. En iPhone el push requiere "Agregar a inicio" (Safari).

## Estructura

```
deal-tracker/
├── config.yaml               # tiendas, keywords, umbrales de error, notificaciones
├── main.py                   # loop / --once: scrapea + evalúa + notifica
├── core/
│   ├── storage.py             # SQLite: productos, historial de precios, alertas
│   └── deal_engine.py         # las 4 señales de error de precio
├── scrapers/                  # vtex_api, falabella (httpx), ripley (Playwright)
├── notifiers/                 # discord (con retry anti rate-limit), telegram, webpush
├── scripts/
│   └── generate_static_dashboard.py  # HTML para GitHub Pages
├── web/                       # PWA local: FastAPI + static
├── tests/                     # pytest (29 tests)
└── .github/workflows/scan.yml # el cron de producción
```

## Uso responsable

Scraping de precios públicos para uso personal, con ritmo moderado (~15 min)
y vía APIs/SSR que las propias tiendas sirven. Revisa los Términos de
Servicio de cada tienda y no redistribuyas los datos comercialmente.
