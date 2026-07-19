"""
Clase base para scrapers.

Usa Playwright (navegador headless real) en vez de requests+BeautifulSoup
porque Falabella/Ripley/Plaza Vea/Oechsle son SPAs que cargan precios por
JavaScript. Es más pesado pero es lo confiable.

IMPORTANTE: los selectores CSS de cada tienda cambian con el tiempo.
Si un scraper deja de traer resultados, es lo primero a revisar:
abre la página en el navegador, inspecciona un product card, y
actualiza los selectores en el archivo de esa tienda.
"""
import asyncio
import random

from playwright.async_api import async_playwright

from scrapers.types import ScrapedProduct, parse_price_pe  # noqa: F401 (re-export)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]


class BaseScraper:
    """Mantiene UN browser+context de Playwright por instancia, reusado entre
    fetches de distintas categorías de la misma tienda (antes se lanzaba un
    Chromium nuevo por categoría: ~2-4s + cientos de MB cada vez). Cada
    fetch abre solo una `page` liviana dentro de ese context compartido.

    Quien use el scraper debe llamar `close()` al terminar (main.py lo hace
    en un finally dentro de scan_store) para no dejar el proceso de Chromium
    colgado.
    """

    store_name: str = "base"

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None

    async def _ensure_browser(self):
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale="es-PE",
            viewport={"width": 1366, "height": 900},
        )

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._context = self._browser = self._playwright = None

    async def fetch_category(self, url: str) -> list[ScrapedProduct]:
        """Debe implementarse en cada scraper concreto."""
        raise NotImplementedError

    async def _get_page_html(self, url: str, wait_selector: str | None = None, timeout=20000):
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            if wait_selector:
                # state="attached" (no "visible", el default): a los scrapers
                # les basta con que el nodo exista en el DOM para extraer su
                # HTML/JSON; exigir visibilidad hace fallar categorías reales
                # con elementos fuera de viewport o sin layout (ej. <script>).
                await page.wait_for_selector(wait_selector, timeout=timeout, state="attached")
            else:
                await page.wait_for_timeout(2500)
            # scroll para forzar lazy-loading de imágenes/precios
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(800)
            html = await page.content()
        finally:
            await page.close()
        return html

    async def polite_delay(self, base_seconds: float = 1.0):
        """Pausa con jitter entre requests para no parecer bot agresivo."""
        await asyncio.sleep(base_seconds + random.uniform(0, 1.5))
