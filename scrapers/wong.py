"""Scraper de Wong (Cencosud) vía la API pública de VTEX. Ver scrapers/vtex_api.py.

Deshabilitado por defecto en config.yaml: comparte catálogo con Metro y
duplicaría las alertas del mismo error de precio.
"""
from scrapers.vtex_api import VtexApiScraper


class WongScraper(VtexApiScraper):
    store_name = "wong"
