import json

from pywebpush import WebPushException, webpush

from core.storage import all_push_subscriptions


async def send_webpush_alert(cfg: dict, product, deal_result):
    settings = cfg["notifications"]["webpush"]
    if not settings.get("enabled") or not settings.get("vapid_private_key"):
        return

    payload = json.dumps(
        {
            "title": "🔥 Oferta detectada",
            "body": f"{product.title[:80]} — S/ {product.price:.2f}",
            "url": product.url,
        }
    )

    for sub_json in all_push_subscriptions():
        subscription_info = json.loads(sub_json)
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=settings["vapid_private_key"],
                vapid_claims={"sub": settings["vapid_claims_email"]},
            )
        except WebPushException:
            # suscripción caducada/revocada; se podría limpiar de la DB aquí
            continue
