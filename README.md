# Deal Tracker Perú 🇵🇪

Rastrea ofertas de tecnología (laptops, PCs, celulares, TVs, etc.) en
Falabella, Ripley, Plaza Vea y Oechsle, y te avisa por Discord, Telegram
y/o notificación push del navegador (PWA) cuando detecta una oferta real.

## Cómo decide qué es "una oferta real"

No se guía solo por el % de descuento (fácil de inflar subiendo el precio
"original" antes de bajarlo). Combina 4 señales en `core/deal_engine.py`:

1. Descuento grande vs. precio de lista de la tienda
2. Precio absoluto dentro de un rango (piso y techo) que tú defines por
   categoría (para cazar "errores de precio" como tu laptop a S/475, sin
   confundir accesorios baratos como "laptop" barata)
3. Es el precio más bajo que se ha visto de ESE producto específico
4. Está muy por debajo del promedio histórico de ESE producto

Ajusta pesos y umbrales en `config.yaml`.

## Instalación

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Configurar notificaciones

Edita `config.yaml`:

- **Discord**: crea un webhook en tu servidor (Configuración del canal →
  Integraciones → Webhooks) y pega la URL.
- **Telegram**: crea un bot con [@BotFather](https://t.me/BotFather),
  copia el token, y consigue tu `chat_id` escribiéndole a
  [@userinfobot](https://t.me/userinfobot).
- **Web Push (PWA)**: genera las llaves VAPID:
  ```bash
  npx web-push generate-vapid-keys
  ```
  (más simple que el script de Python incluido). Pega ambas llaves en
  `config.yaml`.

## Correr localmente

Terminal 1 — el tracker (scraping + alertas):
```bash
python main.py           # loop infinito, revisa cada tienda en su intervalo
python main.py --once    # una sola pasada por todas las tiendas activas y termina
                          # (el modo que usa el workflow de GitHub Actions)
```

Terminal 2 — el dashboard web:
```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000
```

Abre `http://localhost:8000` en tu celular (misma red WiFi) o despliega
en un servidor para acceder desde cualquier lado y poder "Agregar a
inicio" (PWA) y activar las notificaciones push.

## Desplegarlo 24/7

Este proyecto necesita correr de forma continua — Claude no puede
mantenerlo corriendo por ti. Opciones, de más simple a más control:

- **Un VPS barato** (Hetzner, DigitalOcean, ~$4-6/mes): sube el proyecto,
  usa `systemd` o `tmux`/`screen` para dejar `main.py` y `uvicorn`
  corriendo, y un dominio + Caddy/Nginx si quieres HTTPS (necesario para
  que el push notification funcione fuera de localhost).
- **Raspberry Pi en casa**: gratis si ya la tienes, mismo setup.
- **GitHub Actions con cron**: más limitado (no puede correr "cada 45s"
  de forma continua, mínimo cada 5 min, y no sirve para el dashboard
  en vivo), pero sirve si te alcanza con revisiones cada 5-15 min.

## ⚠️ Notas importantes

- **Ritmo de escaneo**: configurado en `config.yaml` (`scan_interval`),
  ya con jitter incluido en el scraper. No lo bajes de ~20-30s por tienda:
  te arriesgas a que te bloqueen la IP. Para cazar errores de precio que
  duran minutos, 30-45s ya es razonable.
- **Selectores CSS**: los scrapers de `scrapers/*.py` son plantillas
  realistas pero las tiendas cambian su HTML seguido. Si un scraper deja
  de traer productos, inspecciona la página en el navegador y actualiza
  los selectores (instrucciones dentro de cada archivo).
- **Uso responsable**: esto es scraping de páginas públicas para uso
  personal. Revisa los Términos de Servicio de cada tienda; evita
  cargas agresivas y no redistribuyas los datos comercialmente.
- **iOS**: las notificaciones push web funcionan en iPhone solo después
  de "Agregar a pantalla de inicio" (Safari → compartir → Agregar a
  inicio), por restricción de Apple.

## Estructura del proyecto

```
deal-tracker/
├── config.yaml          # tiendas, categorías, umbrales, notificaciones
├── main.py              # loop principal: scrapea + evalúa + notifica
├── core/
│   ├── storage.py        # SQLite: productos, historial, alertas
│   └── deal_engine.py     # lógica de qué cuenta como "oferta"
├── scrapers/              # uno por tienda (Playwright + BeautifulSoup)
├── notifiers/              # discord.py, telegram.py, webpush.py
└── web/
    ├── app.py              # FastAPI: dashboard + API + push subscribe
    └── static/              # PWA (index.html, manifest.json, sw.js)
```
