"""Scraper de Oechsle vía la API pública de VTEX. Ver scrapers/vtex_api.py
para el detalle del endpoint y la estructura de datos."""
from scrapers.vtex_api import VtexApiScraper


class OechsleScraper(VtexApiScraper):
    store_name = "oechsle"
