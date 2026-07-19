"""
Scraper base para tiendas VTEX (Plaza Vea, Oechsle) usando su API pública
de catálogo en vez de scraping HTML.

Endpoint (sin autenticación, confirmado contra producción el 2026-07-19):
    GET {scheme}://{host}/api/catalog_system/pub/products/search/{categoria}
        ?_from=N&_to=M

Ventajas sobre Playwright+BeautifulSoup:
  - Sin selectores CSS que se rompen con cada deploy del frontend.
  - Mucho más rápido y liviano (sin lanzar Chromium) — clave para correr
    en GitHub Actions dentro del presupuesto de minutos gratis.
  - Datos de stock (IsAvailable) más confiables que inferir del HTML.

La categoría se deriva del path de la URL de config.yaml: para
"https://www.plazavea.com.pe/tecnologia/computo" la categoría de API es
"tecnologia/computo" (confirmado que el path de navegación == slug de API
en VTEX estándar).
"""
import asyncio
import random
from urllib.parse import urlparse

import httpx

from scrapers.types import ScrapedProduct

PAGE_SIZE = 50
MAX_PRODUCTS = 200  # tope de seguridad por categoría (4 páginas)


class VtexApiScraper:
    store_name = "vtex-base"

    async def fetch_category(self, url: str) -> list[ScrapedProduct]:
        parsed = urlparse(url)
        category_path = parsed.path.strip("/")
        api_url = f"{parsed.scheme}://{parsed.netloc}/api/catalog_system/pub/products/search/{category_path}"

        products = []
        offset = 0
        async with httpx.AsyncClient(
            timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; deal-tracker/1.0)"}
        ) as client:
            while offset < MAX_PRODUCTS:
                resp = await client.get(api_url, params={"_from": offset, "_to": offset + PAGE_SIZE - 1})
                # VTEX responde 206 (Partial Content) para paginación por rango,
                # y 200 en la última página si el total calza exacto. 404 = fin
                # de resultados (offset pasó el total).
                if resp.status_code not in (200, 206):
                    break
                batch = resp.json()
                if not batch:
                    break

                for item in batch:
                    product = self._parse_product(item)
                    if product:
                        products.append(product)

                if len(batch) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE
                await asyncio.sleep(0.3)  # respiro entre páginas de la misma categoría

        return products

    def _parse_product(self, item: dict) -> ScrapedProduct | None:
        try:
            sku = item["items"][0]
            offer = sku["sellers"][0]["commertialOffer"]
            price = offer.get("Price")
            list_price = offer.get("ListPrice")
            if not price or price <= 0:
                return None

            image_url = None
            if sku.get("images"):
                image_url = sku["images"][0].get("imageUrl")

            original_price = float(list_price) if list_price and list_price > price else None

            return ScrapedProduct(
                title=item["productName"],
                url=item["link"],
                price=float(price),
                original_price=original_price,
                image_url=image_url,
                in_stock=bool(offer.get("IsAvailable", True)),
            )
        except (KeyError, IndexError, TypeError):
            return None

    async def polite_delay(self, base_seconds: float = 0.5):
        await asyncio.sleep(base_seconds + random.uniform(0, 1.0))

    async def close(self):
        """No-op: httpx.AsyncClient ya se cierra solo (context manager) en
        fetch_category. Existe para que main.py pueda llamar scraper.close()
        sin importar si el scraper usa Playwright o no."""
