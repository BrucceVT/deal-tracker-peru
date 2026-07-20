"""Scraper de Coolbox vía la API pública de VTEX. Ver scrapers/vtex_api.py."""
from scrapers.vtex_api import VtexApiScraper


class CoolboxScraper(VtexApiScraper):
    store_name = "coolbox"
