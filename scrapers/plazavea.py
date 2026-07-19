"""Scraper de Plaza Vea vía la API pública de VTEX. Ver scrapers/vtex_api.py
para el detalle del endpoint y la estructura de datos."""
from scrapers.vtex_api import VtexApiScraper


class PlazaVeaScraper(VtexApiScraper):
    store_name = "plazavea"
