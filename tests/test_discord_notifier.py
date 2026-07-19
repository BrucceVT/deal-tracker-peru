"""
Tests de notifiers/discord.py.

Bug real encontrado en producción (2026-07-19, primer run en GitHub Actions):
con varias ofertas detectadas en el mismo escaneo, Discord rate-limita el
webhook (429) y el POST se pierde en silencio si no se reintenta.
"""
import httpx
import pytest

import notifiers.discord as discord_mod
from core.deal_engine import DealResult
from scrapers.types import ScrapedProduct


def _cfg():
    return {"notifications": {"discord": {"enabled": True, "webhook_url": "https://discord.com/api/webhooks/real/token"}}}


def _product():
    return ScrapedProduct(title="Laptop de prueba", url="https://example.com/p", price=900.0, original_price=1500.0, image_url=None)


def _result():
    return DealResult(is_deal=True, score=3.5, reasons=["Descuento de 40%"])


@pytest.fixture
def mock_discord(monkeypatch):
    def _install(handler):
        transport = httpx.MockTransport(handler)
        original_client_cls = discord_mod.httpx.AsyncClient
        monkeypatch.setattr(
            discord_mod.httpx, "AsyncClient", lambda **kw: original_client_cls(transport=transport, **kw)
        )

    return _install


async def test_retries_once_after_429_and_succeeds(mock_discord):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.01"}, json={"retry_after": 0.01})
        return httpx.Response(204)

    mock_discord(handler)
    await discord_mod.send_discord_alert(_cfg(), _product(), _result())

    assert len(calls) == 2  # el primer intento (429) + el retry exitoso


async def test_single_success_does_not_retry(mock_discord):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(204)

    mock_discord(handler)
    await discord_mod.send_discord_alert(_cfg(), _product(), _result())

    assert len(calls) == 1


async def test_disabled_or_placeholder_webhook_sends_nothing(mock_discord):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(204)

    mock_discord(handler)
    cfg = _cfg()
    cfg["notifications"]["discord"]["webhook_url"] = "https://discord.com/api/webhooks/TU_WEBHOOK_AQUI"
    await discord_mod.send_discord_alert(cfg, _product(), _result())

    assert len(calls) == 0
