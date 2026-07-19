"""
Tests del scraper VTEX API (scrapers/vtex_api.py).

Usa httpx.MockTransport para no depender de red real en la suite de tests
(la validación contra las APIs en vivo de Plaza Vea/Oechsle se hizo manualmente
el 2026-07-19, ver docs/PLAN.md). Cubre en particular:

- Bug encontrado en vivo: VTEX responde 206 (Partial Content) para paginación
  por rango _from/_to, no 200. Un chequeo `== 200` deja el scraper devolviendo
  0 productos silenciosamente.
- Parseo de precio/descuento/imagen/stock desde la forma real del JSON.
"""
import httpx
import pytest

import scrapers.vtex_api as vtex_api_mod
from scrapers.vtex_api import VtexApiScraper

SAMPLE_PRODUCT = {
    "productName": "Laptop Gamer ASUS TUF Gaming A15",
    "link": "https://www.plazavea.com.pe/laptop-asus-tuf/p",
    "items": [
        {
            "images": [{"imageUrl": "https://plazavea.vteximg.com.br/img.jpg"}],
            "sellers": [
                {
                    "commertialOffer": {
                        "Price": 3649.0,
                        "ListPrice": 3899.0,
                        "IsAvailable": True,
                        "AvailableQuantity": 169,
                    }
                }
            ],
        }
    ],
}

SAMPLE_PRODUCT_NO_DISCOUNT = {
    "productName": "Tablet Lenovo Ideatab",
    "link": "https://www.plazavea.com.pe/tablet-lenovo/p",
    "items": [
        {
            "images": [],
            "sellers": [
                {"commertialOffer": {"Price": 726.0, "ListPrice": 726.0, "IsAvailable": True}}
            ],
        }
    ],
}


@pytest.fixture
def mock_vtex(monkeypatch):
    """Redirige httpx.AsyncClient DENTRO de scrapers.vtex_api hacia un
    MockTransport, sin tocar el httpx.AsyncClient global (evita que el
    reemplazo se llame a sí mismo recursivamente)."""

    def _install(handler):
        transport = httpx.MockTransport(handler)
        original_client_cls = vtex_api_mod.httpx.AsyncClient

        def patched_client(**kwargs):
            return original_client_cls(transport=transport, **kwargs)

        monkeypatch.setattr(vtex_api_mod.httpx, "AsyncClient", patched_client)

    return _install


async def test_fetch_category_handles_206_partial_content(mock_vtex):
    """El bug real encontrado: VTEX responde 206, no 200, para _from/_to."""

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("_from", 0))
        if offset == 0:
            return httpx.Response(206, json=[SAMPLE_PRODUCT])
        return httpx.Response(206, json=[])  # página siguiente vacía -> fin

    mock_vtex(handler)
    scraper = VtexApiScraper()
    products = await scraper.fetch_category("https://www.plazavea.com.pe/tecnologia/computo")

    assert len(products) == 1
    assert products[0].title == "Laptop Gamer ASUS TUF Gaming A15"
    assert products[0].price == 3649.0
    assert products[0].original_price == 3899.0
    assert products[0].in_stock is True
    assert products[0].image_url == "https://plazavea.vteximg.com.br/img.jpg"


async def test_no_discount_when_price_equals_list_price(mock_vtex):
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("_from", 0))
        if offset == 0:
            return httpx.Response(200, json=[SAMPLE_PRODUCT_NO_DISCOUNT])
        return httpx.Response(200, json=[])

    mock_vtex(handler)
    scraper = VtexApiScraper()
    products = await scraper.fetch_category("https://www.plazavea.com.pe/tecnologia")

    assert len(products) == 1
    assert products[0].original_price is None  # Price == ListPrice -> sin descuento
    assert products[0].image_url is None  # sin imágenes en el SKU


async def test_http_error_status_returns_empty_list(mock_vtex):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="blocked")

    mock_vtex(handler)
    scraper = VtexApiScraper()
    products = await scraper.fetch_category("https://www.plazavea.com.pe/tecnologia")

    assert products == []
