import asyncio
import json
import logging

from pywebpush import WebPushException, webpush

from core.storage import all_push_subscriptions, delete_push_subscription

log = logging.getLogger("deal-tracker")


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
            # webpush() es síncrono (hace HTTP con requests por dentro):
            # ejecutarlo directo bloquearía el event loop y con él los
            # escaneos concurrentes de las demás tiendas.
            await asyncio.to_thread(
                webpush,
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=settings["vapid_private_key"],
                vapid_claims={"sub": settings["vapid_claims_email"]},
            )
        except WebPushException as exc:
            # 404/410 = suscripción caducada o revocada por el navegador:
            # se elimina de la DB para no reintentar contra ella por siempre.
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                delete_push_subscription(subscription_info.get("endpoint", ""))
                log.info("Suscripción push caducada eliminada (%s)", status)
            else:
                log.warning("Error enviando web push: %s", exc)
