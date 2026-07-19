"""
Genera un dashboard estático (site/index.html) con las últimas ofertas de la
DB, para publicarlo en GitHub Pages desde el workflow de escaneo.

Contexto: en el modelo de hosting por GitHub Actions no hay servidor FastAPI
corriendo 24/7, así que el dashboard "vivo" de web/ no aplica. Este script
produce un HTML autocontenido (datos embebidos, sin API) que el workflow
regenera y publica en cada escaneo — visible desde el celular en la URL de
Pages del repo.

Uso:
    python scripts/generate_static_dashboard.py [salida]  # default: site/index.html
"""
import html
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import storage  # noqa: E402

LIMA_TZ = timezone(timedelta(hours=-5))

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Deal Tracker Perú</title>
<meta name="theme-color" content="#0f1115" />
<style>
  :root {{
    --bg: #0f1115; --card: #171a21; --accent: #ff5c39;
    --text: #eef0f3; --muted: #8b93a1;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
  }}
  header {{
    padding: 20px; border-bottom: 1px solid #22262f;
    position: sticky; top: 0; background: var(--bg); z-index: 10;
  }}
  header h1 {{ font-size: 1.15rem; margin: 0; }}
  header h1 span {{ color: var(--accent); }}
  .updated {{ font-size: 0.75rem; color: var(--muted); margin-top: 4px; }}
  main {{ padding: 16px; max-width: 720px; margin: 0 auto; }}
  .deal-card {{
    background: var(--card); border-radius: 14px; padding: 14px; margin-bottom: 12px;
    display: flex; gap: 12px; align-items: center; text-decoration: none;
    color: var(--text); border: 1px solid #22262f;
  }}
  .deal-card img {{
    width: 64px; height: 64px; object-fit: contain;
    background: white; border-radius: 8px; flex-shrink: 0;
  }}
  .deal-info {{ flex: 1; min-width: 0; }}
  .deal-title {{
    font-size: 0.92rem; font-weight: 600; margin: 0 0 4px;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }}
  .deal-meta {{ font-size: 0.8rem; color: var(--muted); }}
  .deal-price {{ color: var(--accent); font-weight: 700; }}
  .deal-store {{
    display: inline-block; font-size: 0.7rem; text-transform: uppercase;
    background: #22262f; padding: 2px 8px; border-radius: 10px; margin-right: 6px;
  }}
  .empty {{ color: var(--muted); text-align: center; margin-top: 60px; font-size: 0.9rem; line-height: 1.6; }}
</style>
</head>
<body>
  <header>
    <h1>Deal<span>Tracker</span> 🇵🇪</h1>
    <div class="updated">Errores de precio detectados · actualizado {updated} (hora Lima)</div>
  </header>
  <main>
{cards}
  </main>
</body>
</html>
"""

EMPTY_STATE = """    <p class="empty">
      Ningún error de precio detectado todavía.<br/>
      El tracker escanea las tiendas cada 15 minutos — cuando un producto
      aparezca a un precio absurdamente bajo, saldrá aquí y llegará la
      alerta a Discord.
    </p>"""

CARD_TEMPLATE = """    <a class="deal-card" href="{url}" target="_blank" rel="noopener">
      {img}
      <div class="deal-info">
        <p class="deal-title">{title}</p>
        <div class="deal-meta">
          <span class="deal-store">{store}</span>
          <span class="deal-price">S/ {price:.2f}</span>
          · score {score} · {when}
        </div>
      </div>
    </a>"""


def render(deals: list[dict]) -> str:
    if not deals:
        cards = EMPTY_STATE
    else:
        rendered = []
        for d in deals:
            img = (
                f'<img src="{html.escape(d["image_url"], quote=True)}" alt="" '
                f"onerror=\"this.style.display='none'\" />"
                if d.get("image_url")
                else ""
            )
            when = datetime.fromtimestamp(d["ts"], tz=LIMA_TZ).strftime("%d/%m %H:%M")
            rendered.append(
                CARD_TEMPLATE.format(
                    url=html.escape(d["url"], quote=True),
                    img=img,
                    title=html.escape(d["title"]),
                    store=html.escape(d["store"]),
                    price=d["price_at_alert"],
                    score=d["score"],
                    when=when,
                )
            )
        cards = "\n".join(rendered)

    updated = datetime.now(tz=LIMA_TZ).strftime("%d/%m/%Y %H:%M")
    return PAGE_TEMPLATE.format(updated=updated, cards=cards)


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("site/index.html")
    storage.init_db()
    deals = storage.recent_deals(limit=50)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(deals), encoding="utf-8")
    print(f"Dashboard estático generado: {out_path} ({len(deals)} ofertas)")


if __name__ == "__main__":
    main()
