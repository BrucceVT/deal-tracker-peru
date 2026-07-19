"""
Scraper de Falabella Perú vía el JSON `__NEXT_DATA__` que Next.js embebe en
el SSR de la página de categoría — sin Playwright.

Confirmado en vivo el 2026-07-19 con el navegador: un GET simple ya trae el
HTML completo con los 56 productos de la página serializados en
`<script id="__NEXT_DATA__" type="application/json">`, dentro de
`props.pageProps.results`. No hace falta ejecutar JS ni esperar hidratación
de React — el bloqueo anti-bot (Cloudflare, no Akamai) que se ve en el
navegador es sobre el JS del cliente, no sobre el HTML inicial.

Paginación: `?page=N` (confirmado con page=2, ~56 resultados por página).

Si en el futuro Falabella cambia a hidratación sin SSR (el script deja de
aparecer), este scraper devolverá listas vacías silenciosamente — revisar
primero con la skill `/validate-scrapers`.
"""
import asyncio
import json
import random
import re

import httpx

from scrapers.types import ScrapedProduct, parse_price_pe

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)
MAX_PAGES = 4  # tope de seguridad (~200 productos por categoría)


class FalabellaScraper:
    store_name = "falabella"

    async def fetch_category(self, url: str) -> list[ScrapedProduct]:
        products = []
        async with httpx.AsyncClient(
            timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; deal-tracker/1.0)"}
        ) as client:
            for page in range(1, MAX_PAGES + 1):
                page_url = url if page == 1 else f"{url}?page={page}"
                resp = await client.get(page_url)
                if resp.status_code != 200:
                    break

                match = NEXT_DATA_RE.search(resp.text)
                if not match:
                    break

                try:
                    data = json.loads(match.group(1))
                    results = data["props"]["pageProps"]["results"]
                except (KeyError, json.JSONDecodeError):
                    break

                if not results:
                    break

                for item in results:
                    product = self._parse_product(item)
                    if product:
                        products.append(product)

        return products

    def _parse_product(self, item: dict) -> ScrapedProduct | None:
        try:
            title = item["displayName"]
            product_url = item["url"]

            prices_by_type = {p["type"]: p for p in item.get("prices", [])}
            # internetPrice = precio general online; cmrPrice requiere la
            # tarjeta propia de Falabella y no todos los usuarios la tienen,
            # así que no lo usamos como precio "de facto".
            current = prices_by_type.get("internetPrice") or prices_by_type.get("cmrPrice")
            if not current or not current.get("price"):
                return None
            price = parse_price_pe("".join(current["price"]))
            if not price:
                return None

            original_price = None
            normal = prices_by_type.get("normalPrice")
            if normal and normal.get("crossed") and normal.get("price"):
                normal_price = parse_price_pe("".join(normal["price"]))
                if normal_price and normal_price > price:
                    original_price = normal_price

            media_urls = item.get("mediaUrls") or []
            image_url = media_urls[0] if media_urls else None

            return ScrapedProduct(
                title=title,
                url=product_url,
                price=price,
                original_price=original_price,
                image_url=image_url,
                in_stock=True,
            )
        except (KeyError, IndexError, TypeError):
            return None

    async def polite_delay(self, base_seconds: float = 0.5):
        await asyncio.sleep(base_seconds + random.uniform(0, 1.0))

    async def close(self):
        """No-op: no usa Playwright. Existe para la interfaz común con scan_store."""
