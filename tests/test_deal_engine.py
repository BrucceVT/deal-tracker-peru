"""
Tests del motor de decisión (core/deal_engine.py).

Cubren en particular los 3 bugs corregidos en la Fase 1:
- Bug 2: below_historical_min debe poder activarse cuando el historial
  pasado (SIN el precio actual) tiene un mínimo mayor al precio actual.
- Bug 3: el rango floor/ceiling y la lista de exclusión deben evitar que
  accesorios baratos ("mochila para laptop") se marquen como oferta.
- Matching por palabra completa: "tablet" no debe matchear "tableta gráfica".
"""
import pytest

from core.deal_engine import evaluate


@pytest.fixture
def base_cfg():
    return {
        "deal_engine": {
            "min_score": 2.0,
            "weights": {
                "discount_pct_high": 1.5,
                "below_price_ceiling": 2.0,
                "below_historical_min": 1.5,
                "below_historical_avg_pct": 1.0,
            },
            "discount_pct_threshold": 35,
            "historical_avg_pct_threshold": 20,
        },
        "exclude_keywords": [
            "mochila", "funda", "case", "cooler", "cargador", "cable", "soporte",
        ],
        "price_ceiling": {
            "laptop": {"floor": 300, "ceiling": 1200},
            "tablet": {"floor": 150, "ceiling": 500},
        },
    }


def test_no_signal_no_deal(base_cfg):
    result = evaluate("Laptop HP 15 pulgadas", 3500, None, [], base_cfg)
    assert result.is_deal is False
    assert result.score == 0.0


def test_discount_signal_activates(base_cfg):
    # 50% de descuento >= threshold 35% -> dispara sola con peso 1.5, pero
    # min_score es 2.0, así que sola no basta.
    result = evaluate("Monitor Samsung 24 pulgadas", 500, 1000, [], base_cfg)
    assert any("Descuento" in r for r in result.reasons)
    assert result.score == 1.5
    assert result.is_deal is False


def test_discount_below_threshold_no_signal(base_cfg):
    result = evaluate("Monitor Samsung 24 pulgadas", 900, 1000, [], base_cfg)
    assert result.score == 0.0


def test_price_ceiling_alone_does_not_trigger_deal(base_cfg):
    # Regla de combinación (2026-07-19): "rango de precio" sola NO basta.
    # Encontrado en validación real: ~27/399 productos de gama baja viven
    # SIEMPRE dentro del rango sin ser un error de precio real.
    result = evaluate("Laptop Lenovo IdeaPad 475", 475, None, [], base_cfg)
    assert result.is_deal is False
    assert result.score == 2.0
    assert any("rango" in r for r in result.reasons)
    assert any("sin otra señal" in r for r in result.reasons)


def test_price_ceiling_combined_with_discount_activates_deal(base_cfg):
    # Rango de precio + descuento fuerte sí debe alertar (caso real: laptop
    # de error de precio que ADEMÁS viene con descuento vs precio de lista).
    result = evaluate("Laptop Lenovo IdeaPad 475", 475, 900, [], base_cfg)
    assert result.is_deal is True
    assert result.score == 3.5


def test_price_below_floor_is_not_a_deal(base_cfg):
    # Precio absurdamente bajo para "laptop" = probable accesorio mal filtrado,
    # no debe activar la señal de rango.
    result = evaluate("Laptop stand ajustable", 45, None, [], base_cfg)
    assert result.score == 0.0
    assert result.is_deal is False


def test_exclude_keyword_blocks_accessory_even_in_price_range(base_cfg):
    # "mochila para laptop" a S/59 -> sin exclusión, calzaría con category
    # "laptop" (contiene la palabra) pero 59 < floor 300, así que ya no
    # activaría por el fix del floor. Probamos igual con un precio DENTRO
    # del rango para confirmar que la exclusión por keyword es la que manda.
    result = evaluate("Mochila para laptop 15 pulgadas reforzada", 350, None, [], base_cfg)
    assert result.is_deal is False
    assert result.score == 0.0
    assert "Excluido" in result.reasons[0]


def test_word_boundary_no_false_positive_tablet_vs_tableta(base_cfg):
    # "tableta gráfica" (accesorio de dibujo) no debe matchear la categoría "tablet"
    result = evaluate("Tableta gráfica digitalizadora XP-Pen", 400, None, [], base_cfg)
    assert result.score == 0.0


def test_historical_min_signal_activates_when_price_drops(base_cfg):
    # Historial (SIN precio actual, tal como lo entrega main.py tras el fix
    # del Bug 2): mínimo previo 1000. Precio actual 900 < 1000 -> dispara.
    history = [(1000.0, 100), (1100.0, 90), (1050.0, 80)]
    result = evaluate("Laptop Asus Vivobook", 900, None, history, base_cfg)
    assert any("más bajo histórico" in r for r in result.reasons)
    assert result.score >= 1.5


def test_historical_min_signal_does_not_activate_with_only_current_point(base_cfg):
    # Con menos de 2 puntos históricos no hay base de comparación confiable.
    # Precio fuera del rango floor/ceiling de "laptop" a propósito, para
    # aislar la señal histórica de la señal 2 (rango de precio).
    history = [(2000.0, 100)]
    result = evaluate("Laptop Asus Vivobook", 2000, None, history, base_cfg)
    assert result.score == 0.0


def test_historical_avg_signal_activates(base_cfg):
    history = [(1000.0, 100), (1000.0, 90), (1000.0, 80)]
    # 30% bajo el promedio de 1000 = 700, >= threshold 20%
    result = evaluate("Laptop Dell Inspiron", 700, None, history, base_cfg)
    assert any("bajo el precio promedio" in r for r in result.reasons)


def test_combined_signals_sum_score(base_cfg):
    # Descuento fuerte + dentro de rango + bajo mínimo histórico: score alto
    history = [(1300.0, 100), (1250.0, 90)]
    result = evaluate("Laptop HP Pavilion", 700, 1500, history, base_cfg)
    assert result.is_deal is True
    assert result.score > 2.0
    assert len(result.reasons) >= 2
