"""
Tests del integrador de Knasta.pe (core/knasta.py).
"""
import httpx
import pytest
import core.knasta as knasta_mod
from core.knasta import get_knasta_history, clean_url

SAMPLE_SEARCH_RESPONSE = {
    "products": [
        {
            "kid": "plazavea#2925700",
            "product_id": "2925700",
            "title": "Laptop Lenovo LOQ 8GB RAM Intel Core i5-12450HX",
            "price_value": 2799.0,
            "retail": "plazavea",
            "url": "https://www.plazavea.com.pe/laptop-lenovo-loq-8gb-ram-intel-core-i5-12450hx-101853888/p"
        },
        {
            "kid": "oechsle#2925700",
            "product_id": "2925700",
            "title": "Laptop Lenovo LOQ 8GB RAM Intel Core i5-12450HX",
            "price_value": 2799.0,
            "retail": "oechsle",
            "url": "https://www.oechsle.pe/laptop-lenovo-loq-8gb-ram-intel-core-i5-12450hx-101853888/p"
        }
    ]
}

SAMPLE_DETAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Laptop Lenovo LOQ</title>
</head>
<body>
    <script id="__NEXT_DATA__" type="application/json">
    {
        "props": {
            "pageProps": {
                "initialData": {
                    "product": {
                        "dprices": [
                            {"date": "08-08-2026", "price": 2799.0, "retail": "plazavea"},
                            {"date": "05-08-2026", "price": 3099.0, "retail": "plazavea"}
                        ]
                    }
                }
            }
        }
    }
    </script>
</body>
</html>
"""

@pytest.fixture
def mock_knasta(monkeypatch):
    """Parchea httpx.AsyncClient dentro de core.knasta para simular respuestas de red."""
    def _install(handler):
        transport = httpx.MockTransport(handler)
        original_client_cls = knasta_mod.httpx.AsyncClient

        def patched_client(**kwargs):
            return original_client_cls(transport=transport, **kwargs)

        monkeypatch.setattr(knasta_mod.httpx, "AsyncClient", patched_client)

    return _install

def test_clean_url():
    assert clean_url("https://www.plazavea.com.pe/laptop-lenovo?query=1") == "www.plazavea.com.pe/laptop-lenovo"
    assert clean_url("HTTP://PLAzaVEA.com.pe/Laptop-Lenovo/") == "plazavea.com.pe/laptop-lenovo"

async def test_get_knasta_history_success(mock_knasta):
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "api/results" in url_str:
            assert request.url.params.get("q") == "Laptop Lenovo LOQ"
            return httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
        elif "detail/plazavea/2925700" in url_str:
            return httpx.Response(200, text=SAMPLE_DETAIL_HTML)
        return httpx.Response(404, text="Not Found")

    mock_knasta(handler)
    history = await get_knasta_history(
        title="Laptop Lenovo LOQ",
        store_url="https://www.plazavea.com.pe/laptop-lenovo-loq-8gb-ram-intel-core-i5-12450hx-101853888/p?query=abc",
        store_name="plazavea"
    )

    assert history is not None
    assert len(history) == 2
    # El primero debe ser el más reciente: 08-08-2026 -> timestamp más alto
    assert history[0][0] == 2799.0
    assert history[1][0] == 3099.0
    assert history[0][1] > history[1][1]

async def test_get_knasta_history_fuzzy_match(mock_knasta):
    # La URL no coincide exactamente, pero el product_id ("2925700") está en la URL
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "api/results" in url_str:
            return httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
        elif "detail/plazavea/2925700" in url_str:
            return httpx.Response(200, text=SAMPLE_DETAIL_HTML)
        return httpx.Response(404, text="Not Found")

    mock_knasta(handler)
    history = await get_knasta_history(
        title="Laptop Lenovo LOQ",
        store_url="https://www.plazavea.com.pe/p/some-slug-2925700",
        store_name="plazavea"
    )

    assert history is not None
    assert len(history) == 2

async def test_get_knasta_history_not_found(mock_knasta):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"products": []})

    mock_knasta(handler)
    history = await get_knasta_history(
        title="Non existent",
        store_url="https://www.plazavea.com.pe/non-existent",
        store_name="plazavea"
    )
    assert history is None

async def test_get_knasta_history_http_error(mock_knasta):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    mock_knasta(handler)
    history = await get_knasta_history(
        title="Laptop",
        store_url="https://www.plazavea.com.pe/laptop",
        store_name="plazavea"
    )
    assert history is None
