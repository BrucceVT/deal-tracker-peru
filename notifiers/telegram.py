import httpx


async def send_telegram_alert(cfg: dict, product, deal_result):
    settings = cfg["notifications"]["telegram"]
    if not settings.get("enabled"):
        return
    token = settings["bot_token"]
    chat_id = settings["chat_id"]
    if "TU_BOT_TOKEN_AQUI" in token:
        return  # no configurado todavía

    reasons = "\n".join(f"• {r}" for r in deal_result.reasons)
    text = (
        f"🔥 *Oferta detectada*\n\n"
        f"*{product.title}*\n\n"
        f"💰 Precio: S/ {product.price:.2f}\n"
    )
    if product.original_price:
        text += f"~~S/ {product.original_price:.2f}~~\n"
    text += f"\n{reasons}\n\n🔗 {product.url}"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": False}

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json=payload)
