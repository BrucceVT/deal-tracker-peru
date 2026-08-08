import asyncio
import logging

import httpx

log = logging.getLogger("deal-tracker")


async def send_discord_alert(cfg: dict, product, deal_result, store_name: str):
    settings = cfg["notifications"]["discord"]
    if not settings.get("enabled"):
        return
    webhook_url = settings["webhook_url"]
    if "TU_WEBHOOK_AQUI" in webhook_url:
        return  # no configurado todavía

    # Calcular descuento porcentual si es posible
    discount_pct = None
    if product.original_price and product.original_price > product.price:
        discount_pct = (1 - product.price / product.original_price) * 100
        
    discount_field = f"**-{discount_pct:.0f}%**" if discount_pct else "N/D"

    # Determinar nivel de confianza/fuerza de la oferta
    score_val = deal_result.score
    if score_val >= 3.5:
        fuerza = "🚨 Crítico / Error de Precio"
    elif score_val >= 3.0:
        fuerza = "🔥 Muy Alta"
    elif score_val >= 2.5:
        fuerza = "📈 Alta"
    else:
        fuerza = "✅ Buena Oferta"
        
    fuerza_field = f"**{fuerza}** ({score_val:.1f})"

    embed = {
        "title": product.title[:250],
        "url": product.url,
        "description": "\n".join(f"• {r}" for r in deal_result.reasons),
        "color": 0x2ecc71,
        "fields": [
            {"name": "🏪 Tienda", "value": f"**{store_name.upper()}**", "inline": True},
            {"name": "💰 Precio Oferta", "value": f"**S/ {product.price:.2f}**", "inline": True},
            {"name": "🏷️ Lista / Tachado", "value": f"S/ {product.original_price:.2f}" if product.original_price else "N/D", "inline": True},
            {"name": "📉 Dto. Tienda", "value": discount_field, "inline": True},
            {"name": "⚡ Confianza de Alerta", "value": fuerza_field, "inline": True},
            {"name": "📦 Stock", "value": "Disponible" if product.in_stock else "Agotado", "inline": True},
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
