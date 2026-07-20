"""Scraper de Promart vía la API pública de VTEX. Ver scrapers/vtex_api.py."""
from scrapers.vtex_api import VtexApiScraper


class PromartScraper(VtexApiScraper):
    store_name = "promart"
