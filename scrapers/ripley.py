"""
Scraper de Ripley Perú (simple.ripley.com.pe).

Necesita Playwright (a diferencia de Falabella): confirmado en vivo el
2026-07-19 que un GET plano con httpx devuelve 403 (Cloudflare bot
management en modo bloqueo), mientras que Falabella —también detrás de
Cloudflare— sí deja pasar requests planas. Un browser real sí supera el
challenge.

Pero en vez de selectores CSS frágiles sobre las tarjetas de producto,
extrae los datos estructurados del propio `__NEXT_DATA__` que Next.js deja
en el DOM (`props.pageProps.findabilityProps.data.products`) — mismo
enfoque que scrapers/falabella.py. Ese JSON no incluye la URL del producto,
así que se empareja con los `<a href>` reales del DOM usando el parámetro
`pos=N` que Ripley agrega a cada link de producto (posición dentro de la
grilla, 1-indexado, coincide con el índice+1 del array de productos).

IMPORTANTE: la categoría de config.yaml estaba rota (devolvía 404,
"computo" ya no existe) — la correcta es "computacion":
    https://simple.ripley.com.pe/tecnologia/computacion/laptops
"""
import json
import re

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from scrapers.types import ScrapedProduct, parse_price_pe

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)
POS_RE = re.compile(r"[?&]pos=(\d+)")


class RipleyScraper(BaseScraper):
    store_name = "ripley"

    async def fetch_category(self, url: str) -> list[ScrapedProduct]:
        html = await self._get_page_html(url, wait_selector='a[href*="pos="]')

        match = NEXT_DATA_RE.search(html)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
            products_data = data["props"]["pageProps"]["findabilityProps"]["data"]["products"]
        except (KeyError, json.JSONDecodeError):
            return []

        soup = BeautifulSoup(html, "html.parser")
        url_by_pos = {}
        for a in soup.select('a[href*="pos="]'):
            href = a.get("href", "")
            pos_match = POS_RE.search(href)
            if not pos_match:
                continue
            pos = int(pos_match.group(1))
            if pos not in url_by_pos:
                clean_path = href.split("?")[0]
                full_url = (
                    clean_path if clean_path.startswith("http")
                    else f"https://simple.ripley.com.pe{clean_path}"
                )
                url_by_pos[pos] = full_url

        products = []
        for idx, item in enumerate(products_data, start=1):
            product = self._parse_product(item, url_by_pos.get(idx))
            if product:
                products.append(product)
        return products

    def _parse_product(self, item: dict, product_url: str | None) -> ScrapedProduct | None:
        if not product_url:
            return None
        try:
            title = item["name"]

            price = item.get("priceNumber")
            if price is None:
                price = parse_price_pe(item.get("price", ""))
            if not price or price <= 0:
                return None

            original_price = None
            if item.get("oldPrice"):
                old_price = parse_price_pe(item["oldPrice"])
                if old_price and old_price > price:
                    original_price = old_price

            return ScrapedProduct(
                title=title,
                url=product_url,
                price=float(price),
                original_price=original_price,
                image_url=item.get("primaryImage"),
                in_stock=True,
            )
        except (KeyError, TypeError):
            return None
