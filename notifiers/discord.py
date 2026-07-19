import httpx


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
        await client.post(webhook_url, json=payload)
