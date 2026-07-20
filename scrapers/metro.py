"""Scraper de Metro (Cencosud) vía la API pública de VTEX. Ver scrapers/vtex_api.py.

Nota: Metro y Wong comparten catálogo (ambos Cencosud) — por eso Wong viene
deshabilitado por defecto en config.yaml, para no duplicar alertas del mismo
error de precio.
"""
from scrapers.vtex_api import VtexApiScraper


class MetroScraper(VtexApiScraper):
    store_name = "metro"
