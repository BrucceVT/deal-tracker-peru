"""
Tipos y utilidades compartidas por TODOS los scrapers (con y sin Playwright).

Deliberadamente sin dependencias pesadas (Playwright) para que los scrapers
livianos basados en API (scrapers/vtex_api.py) no arrastren un browser
headless que no necesitan — importa httpx nada más y corre mucho más rápido
en CI (GitHub Actions).
"""
import re
from dataclasses import dataclass


@dataclass
class ScrapedProduct:
    title: str
    url: str
    price: float
    original_price: float | None
    image_url: str | None
    in_stock: bool = True


def parse_price_pe(text: str) -> float | None:
    """Convierte 'S/ 1,299.00' o 'S/1299' -> 1299.0"""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.,]", "", text)
    cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None
