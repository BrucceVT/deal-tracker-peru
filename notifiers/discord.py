import asyncio
import logging

import httpx

log = logging.getLogger("deal-tracker")


async def send_discord_alert(cfg: dict, product, deal_result):
    settings = cfg["notifications"]["discord"]
    if not settings.get("enabled"):
        return
    webhook_url = settings["webhook_url"]
    if "TU_WEBHOOK_AQUI" in webhook_url:
        return  # no configurado todavía

    embed = {
        "title": product.title[:250],
        "url": product.url,
        "description": "\n".join(f"• {r}" for r in deal_result.reasons),
        "color": 0x2ecc71,
        "fields": [
            {"name": "Precio", "value": f"S/ {product.price:.2f}", "inline": True},
            {
                "name": "Precio original",
                "value": f"S/ {product.original_price:.2f}" if product.original_price else "N/D",
                "inline": True,
            },
            {"name": "Score", "value": str(deal_result.score), "inline": True},
        ],
        "thumbnail": {"url": product.image_url} if product.image_url else None,
    }

    payload = {"content": "🔥 **Nueva oferta detectada**", "embeds": [embed]}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=payload)
        if resp.status_code == 429:
            # Confirmado en producción (2026-07-19): con varias ofertas en el
            # mismo escaneo, Discord rate-limita el webhook y el POST se
            # pierde en silencio si no se reintenta. Un solo retry con el
            # backoff que Discord indica alcanza — el burst es esporádico
            # (normal solo la primera vez o tras perder el historial).
            retry_after = 1.0
            try:
                retry_after = float(resp.headers.get("Retry-After") or resp.json().get("retry_after", 1.0))
            except (ValueError, TypeError):
                pass
            log.warning("Discord rate limit (429), reintentando en %.1fs", retry_after)
            await asyncio.sleep(retry_after)
            await client.post(webhook_url, json=payload)
