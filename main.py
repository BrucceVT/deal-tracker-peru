"""
Punto de entrada principal.

Corre en loop infinito: por cada tienda activa, revisa sus categorías
en el intervalo configurado, evalúa cada producto con el deal_engine,
y si califica como oferta, guarda + notifica (Discord/Telegram/WebPush).

Ejecutar:
    python main.py            # loop infinito (uso local / VPS)
    python main.py --once     # una sola pasada por todas las tiendas activas
                               # y termina (uso en GitHub Actions / cron)

Para producción, ver README.md (systemd / cron / Docker / GitHub Actions).
"""
import asyncio
import logging
import os
import sys
import time

import yaml

from core import storage
from core.deal_engine import evaluate
from core.knasta import get_knasta_history
from notifiers.discord import send_discord_alert
from notifiers.telegram import send_telegram_alert
from notifiers.webpush import send_webpush_alert
from scrapers.coolbox import CoolboxScraper
from scrapers.falabella import FalabellaScraper
from scrapers.metro import MetroScraper
from scrapers.oechsle import OechsleScraper
from scrapers.plazavea import PlazaVeaScraper
from scrapers.promart import PromartScraper
from scrapers.ripley import RipleyScraper
from scrapers.wong import WongScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("deal-tracker")

SCRAPER_CLASSES = {
    "falabella": FalabellaScraper,
    "ripley": RipleyScraper,
    "plazavea": PlazaVeaScraper,
    "oechsle": OechsleScraper,
    "coolbox": CoolboxScraper,
    "promart": PromartScraper,
    "metro": MetroScraper,
    "wong": WongScraper,
}


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    _apply_env_overrides(cfg)
    return cfg


def _apply_env_overrides(cfg):
    """En GitHub Actions los secretos llegan por variables de entorno, no en
    config.yaml (que no debe contener tokens/webhooks reales committeados).
    Si están presentes, tienen prioridad sobre lo que haya en el archivo y
    activan el canal automáticamente."""
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if discord_webhook:
        cfg["notifications"]["discord"]["webhook_url"] = discord_webhook
        cfg["notifications"]["discord"]["enabled"] = True

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID")
    if telegram_token and telegram_chat:
        cfg["notifications"]["telegram"]["bot_token"] = telegram_token
        cfg["notifications"]["telegram"]["chat_id"] = telegram_chat
        cfg["notifications"]["telegram"]["enabled"] = True


async def process_product(cfg, store_name, category_url, scraped, seen_urls, category_profile):
    if scraped.url in seen_urls:
        return
    seen_urls.add(scraped.url)

    # Filtrar solo productos que tengan algún descuento aplicado en la tienda
    # (evita procesar productos a precio regular sin oferta)
    if not scraped.original_price or scraped.original_price <= scraped.price:
        return

    product_id = storage.get_or_create_product(
        store=store_name,
        url=scraped.url,
        title=scraped.title,
        category=category_url,
        image_url=scraped.image_url,
    )

    # Historial SIN el precio actual todavía (se inserta después de evaluar),
    # si no, "precio más bajo histórico" nunca podría dispararse.
    history = storage.get_price_history(product_id)

    # ¿Necesitamos validar/poblar con Knasta?
    # 1. Si no hay suficiente historial (menos de 5 registros).
    # 2. Si hay sospecha de oferta por descuento tachado >=35% o baja de precio respecto al último registrado.
    needs_bootstrap = len(history) < 5
    store_discount = (1 - scraped.price / scraped.original_price) if (scraped.original_price and scraped.original_price > scraped.price) else 0.0
    last_price = history[0][0] if history else None
    has_drop = last_price and scraped.price < last_price
    is_candidate = store_discount >= 0.35 or has_drop

    if needs_bootstrap or is_candidate:
        log.info("Consultando Knasta para '%s' (bootstrap=%s, candidate=%s)", scraped.title, needs_bootstrap, is_candidate)
        knasta_history = await get_knasta_history(scraped.title, scraped.url, store_name)
        if knasta_history:
            storage.backfill_price_history(product_id, knasta_history)
            # Volver a cargar el historial recién guardado
            history = storage.get_price_history(product_id)

    result = evaluate(scraped.title, scraped.price, scraped.original_price, history, cfg, category_profile)

    storage.record_price_point(
        product_id, scraped.price, scraped.original_price, scraped.in_stock
    )

    if result.is_deal:
        if not scraped.in_stock:
            return  # no alertar productos agotados

        if storage.was_alert_sent_recently(product_id, scraped.price):
            return  # ya avisamos esta misma oferta hace poco

        log.info("OFERTA: %s | S/%.2f | score=%.2f", scraped.title, scraped.price, result.score)
        storage.record_alert(product_id, scraped.price, result.score)

        await asyncio.gather(
            send_discord_alert(cfg, scraped, result, store_name),
            send_telegram_alert(cfg, scraped, result),
            send_webpush_alert(cfg, scraped, result),
            return_exceptions=True,
        )


async def scan_store(cfg, store_name, store_cfg):
    scraper_cls = SCRAPER_CLASSES.get(store_name)
    if not scraper_cls:
        return
    scraper = scraper_cls()
    seen_urls = set()  # dedupe solo dentro de ESTA pasada (mismo producto en varias categorías)

    try:
        for cat_item in store_cfg.get("categories", []):
            if isinstance(cat_item, dict):
                category_url = cat_item["url"]
                category_type = cat_item["type"]
            else:
                category_url = cat_item
                category_type = "laptops"
                
            category_profile = cfg.get("category_profiles", {}).get(category_type, {})
            if not category_profile:
                category_profile = {
                    "min_reference_price": 0,
                    "keywords": []
                }

            try:
                products = await scraper.fetch_category(category_url)
                log.info("%s: %d productos encontrados en %s", store_name, len(products), category_url)
                for p in products:
                    await process_product(cfg, store_name, category_url, p, seen_urls, category_profile)
            except Exception:
                log.exception("Error escaneando %s (%s)", store_name, category_url)
            await scraper.polite_delay()
    finally:
        # cierra el browser de Playwright si el scraper lo usa (no-op en scrapers de API)
        await scraper.close()


async def main_loop():
    storage.init_db()
    cfg = load_config()
    last_run = {store: 0 for store in cfg["stores"]}

    log.info("Deal Tracker iniciado. Ctrl+C para detener.")
    while True:
        cfg = load_config()  # recarga config sin reiniciar (útil para ajustar umbrales al vuelo)
        now = time.time()

        for store_name, store_cfg in cfg["stores"].items():
            if not store_cfg.get("enabled"):
                continue
            interval = cfg["scan_interval"].get(store_name, 60)
            if now - last_run[store_name] >= interval:
                last_run[store_name] = now
                asyncio.create_task(scan_store(cfg, store_name, store_cfg))

        await asyncio.sleep(2)


async def run_once():
    """Escanea todas las tiendas activas UNA vez y termina. Pensado para
    GitHub Actions / cron: sin esto, el loop infinito colgaría el job hasta
    el timeout y quemaría minutos de CI."""
    storage.init_db()
    cfg = load_config()

    enabled_stores = {
        name: store_cfg for name, store_cfg in cfg["stores"].items() if store_cfg.get("enabled")
    }
    log.info("Modo --once: escaneando %d tienda(s) activa(s): %s",
              len(enabled_stores), ", ".join(enabled_stores))

    await asyncio.gather(
        *(scan_store(cfg, name, store_cfg) for name, store_cfg in enabled_stores.items()),
        return_exceptions=True,
    )
    log.info("Escaneo completo (--once).")


if __name__ == "__main__":
    if "--once" in sys.argv:
        asyncio.run(run_once())
    else:
        asyncio.run(main_loop())
