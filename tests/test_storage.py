"""
Tests de core/storage.py.

Usan una DB SQLite temporal (monkeypatch de storage.DB_PATH) para no tocar
data/deals.db real.
"""
import pytest

from core import storage


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_deals.db"
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    storage.init_db()
    return db_file


def test_get_or_create_product_creates_new(temp_db):
    product_id = storage.get_or_create_product(
        store="falabella", url="https://x.pe/p1", title="Laptop HP",
        category="laptops", image_url="https://x.pe/img.jpg",
    )
    assert product_id is not None

    # Segunda llamada con la misma URL debe devolver el mismo id, no crear otro.
    same_id = storage.get_or_create_product(
        store="falabella", url="https://x.pe/p1", title="Laptop HP 15",
        category="laptops", image_url="https://x.pe/img2.jpg",
    )
    assert same_id == product_id


def test_record_price_point_and_get_history_excludes_nothing_but_order(temp_db):
    product_id = storage.get_or_create_product(
        store="ripley", url="https://x.pe/p2", title="Tablet Samsung",
        category="tablets", image_url=None,
    )
    # Historial vacío antes de registrar nada (clave para el fix del Bug 2:
    # get_price_history debe poder llamarse ANTES de record_price_point).
    assert storage.get_price_history(product_id) == []

    storage.record_price_point(product_id, 500.0, 600.0, True)
    history_after_one = storage.get_price_history(product_id)
    assert len(history_after_one) == 1
    assert history_after_one[0][0] == 500.0

    storage.record_price_point(product_id, 450.0, 600.0, True)
    history_after_two = storage.get_price_history(product_id)
    assert len(history_after_two) == 2
    prices = {p for p, _ in history_after_two}
    assert prices == {500.0, 450.0}


def test_was_alert_sent_recently_uses_tolerance_not_exact_equality(temp_db):
    product_id = storage.get_or_create_product(
        store="oechsle", url="https://x.pe/p3", title="Smartphone Xiaomi",
        category="celulares", image_url=None,
    )
    storage.record_alert(product_id, 699.90, score=3.0)

    # Precio con diferencia de centésimas (redondeo entre scrapes) debe
    # seguir contando como "la misma alerta reciente".
    assert storage.was_alert_sent_recently(product_id, 699.9000001) is True
    assert storage.was_alert_sent_recently(product_id, 699.90) is True

    # Un precio realmente distinto no debe bloquear una nueva alerta.
    assert storage.was_alert_sent_recently(product_id, 650.00) is False


def test_was_alert_sent_recently_respects_time_window(temp_db):
    product_id = storage.get_or_create_product(
        store="plazavea", url="https://x.pe/p4", title="Monitor LG",
        category="monitores", image_url=None,
    )
    storage.record_alert(product_id, 400.0, score=2.5)

    # Con ventana 0 segundos, cualquier alerta pasada queda fuera del cutoff.
    assert storage.was_alert_sent_recently(product_id, 400.0, window_seconds=0) is False


def test_recent_deals_joins_product_info(temp_db):
    product_id = storage.get_or_create_product(
        store="falabella", url="https://x.pe/p5", title="PC Gamer ASUS",
        category="pc", image_url="https://x.pe/pc.jpg",
    )
    storage.record_alert(product_id, 2500.0, score=4.0)

    deals = storage.recent_deals(limit=10)
    assert len(deals) == 1
    assert deals[0]["title"] == "PC Gamer ASUS"
    assert deals[0]["store"] == "falabella"
    assert deals[0]["price_at_alert"] == 2500.0
