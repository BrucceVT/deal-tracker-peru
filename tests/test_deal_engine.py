"""
Tests del motor de decisión (core/deal_engine.py).

Filosofía (recalibrado 2026-07-19 a pedido del usuario): el motor caza
ERRORES DE PRECIO (laptop buena a S/475), no descuentos comunes. Señales
fuertes — descuento >=80%, precio en rango de error, caída histórica >=60% —
pueden disparar SOLAS. El ruido se controla con exclude_keywords
(accesorios, reacondicionados, chromebooks) y el floor del rango.

Cubren también los bugs corregidos en la Fase 1:
- Bug 2: below_historical_min debe poder activarse cuando el historial
  pasado (SIN el precio actual) tiene un mínimo mayor al precio actual.
- Matching por palabra completa: "tablet" no debe matchear "tableta gráfica".
"""
import pytest

from core.deal_engine import evaluate


@pytest.fixture
def base_cfg():
    # Refleja la calibración real de config.yaml post-2026-07-19.
    return {
        "deal_engine": {
            "min_score": 2.0,
            "weights": {
                "discount_pct_high": 2.0,
                "below_price_ceiling": 2.0,
                "below_historical_min": 0.5,
                "below_historical_avg_pct": 2.0,
            },
            "discount_pct_threshold": 80,
            "historical_avg_pct_threshold": 60,
        },
        "exclude_keywords": [
            "mochila", "funda", "case", "cooler", "cargador", "cable", "soporte",
            "reacondicionado", "reacondicionada", "refurbished", "chromebook",
        ],
        "price_ceiling": {
            "laptop": {"floor": 300, "ceiling": 900},
            "tablet": {"floor": 80, "ceiling": 250},
            "televisor": {"floor": 100, "ceiling": 300},
        },
    }


def test_no_signal_no_deal(base_cfg):
    result = evaluate("Laptop HP 15 pulgadas", 3500, None, [], base_cfg)
    assert result.is_deal is False
    assert result.score == 0.0


def test_common_discount_is_ignored(base_cfg):
    # 50% de descuento es una oferta común, NO un error de precio.
    # El usuario pidió explícitamente ignorar descuentos < 80%.
    result = evaluate("Monitor Samsung 24 pulgadas", 500, 1000, [], base_cfg)
    assert result.score == 0.0
    assert result.is_deal is False


def test_drastic_discount_alerts_alone(base_cfg):
    # 85% de descuento tachado -> error de precio o liquidación drástica.
    result = evaluate("Monitor Samsung 24 pulgadas", 150, 1000, [], base_cfg)
    assert result.is_deal is True
    assert any("Descuento de 85%" in r for r in result.reasons)


def test_price_error_range_alerts_alone(base_cfg):
    # EL caso arquetipo del usuario: laptop buena a S/475 (Falabella).
    # En errores de precio la tienda a veces ni muestra tachado, así que
    # la señal de rango debe bastar ELLA SOLA.
    result = evaluate("Laptop Lenovo IdeaPad 5 Ryzen 7 16GB", 475, None, [], base_cfg)
    assert result.is_deal is True
    assert result.score == 2.0
    assert any("error de precio" in r for r in result.reasons)


def test_normal_cheap_product_outside_error_range(base_cfg):
    # Un TV de 32" a S/369 es su precio normal de lista, no un error:
    # queda FUERA del rango de error (ceiling 300) y no alerta.
    # (Este era el ruido de la calibración anterior: 15 alertas de TVs/tablets
    # de gama baja en el primer escaneo real.)
    result = evaluate('Televisor Hyundai 32" HD', 369, 549, [], base_cfg)
    assert result.is_deal is False
    assert result.score == 0.0  # 33% de descuento tampoco llega al umbral de 80%


def test_price_below_floor_is_not_a_deal(base_cfg):
    # Precio absurdamente bajo para "laptop" = probable accesorio mal
    # filtrado, no el producto real.
    result = evaluate("Laptop stand ajustable", 45, None, [], base_cfg)
    assert result.score == 0.0


def test_refurbished_laptop_is_excluded(base_cfg):
    # S/899 es el precio NORMAL de una laptop reacondicionada — cae dentro
    # del rango de error de laptops nuevas pero no es un error de precio.
    # Caso real del primer escaneo: "LAPTOP LENOVO B50-70 REACONDICIONADO".
    result = evaluate("Laptop Lenovo B50-70 Reacondicionado 15.6", 899, None, [], base_cfg)
    assert result.is_deal is False
    assert "Excluido" in result.reasons[0]


def test_chromebook_is_excluded(base_cfg):
    # Chromebooks nuevas a S/500-700 son precio normal, no error.
    result = evaluate("Laptop Chromebook HP 14 4GB 64GB", 549, None, [], base_cfg)
    assert result.is_deal is False
    assert "Excluido" in result.reasons[0]


def test_accessory_keyword_blocks_even_in_price_range(base_cfg):
    result = evaluate("Mochila para laptop 15 pulgadas reforzada", 350, None, [], base_cfg)
    assert result.is_deal is False
    assert result.score == 0.0
    assert "Excluido" in result.reasons[0]


def test_word_boundary_no_false_positive_tablet_vs_tableta(base_cfg):
    # "tableta gráfica" (accesorio de dibujo) no debe matchear la categoría "tablet"
    result = evaluate("Tableta gráfica digitalizadora XP-Pen", 200, None, [], base_cfg)
    assert result.score == 0.0


def test_drastic_historical_drop_alerts_alone(base_cfg):
    # Producto que siempre costó ~S/3000 y aparece a S/1000 (67% bajo su
    # promedio): error de precio aunque no haya tachado ni esté en el rango
    # absoluto de la categoría.
    history = [(3000.0, 100), (3000.0, 90), (3000.0, 80)]
    result = evaluate("Laptop Asus Vivobook Pro", 1000, None, history, base_cfg)
    assert result.is_deal is True
    assert any("bajo el precio promedio" in r for r in result.reasons)


def test_moderate_historical_drop_is_ignored(base_cfg):
    # 30% bajo el promedio es una rebaja normal, no un error (umbral: 60%).
    history = [(3000.0, 100), (3000.0, 90)]
    result = evaluate("Laptop Asus Vivobook Pro", 2100, None, history, base_cfg)
    assert result.is_deal is False


def test_historical_min_is_only_a_booster(base_cfg):
    # Ser el mínimo histórico por sí solo (bajada de S/3000 a S/2900) no
    # es un error de precio: peso 0.5 < min_score 2.0.
    history = [(3000.0, 100), (3050.0, 90)]
    result = evaluate("Laptop Asus Vivobook Pro", 2900, None, history, base_cfg)
    assert result.score == 0.5
    assert result.is_deal is False


def test_historical_signals_need_two_prior_points(base_cfg):
    # Con menos de 2 puntos históricos no hay base de comparación confiable.
    history = [(3000.0, 100)]
    result = evaluate("Laptop Asus Vivobook Pro", 1000, None, history, base_cfg)
    assert result.score == 0.0


def test_combined_signals_sum_score(base_cfg):
    # Error total: laptop en rango de error + descuento drástico + mínimo
    # histórico + caída drástica vs promedio.
    history = [(2800.0, 100), (2900.0, 90)]
    result = evaluate("Laptop HP Pavilion 15 i7", 475, 2900, history, base_cfg)
    assert result.is_deal is True
    assert result.score == 6.5  # 2.0 + 2.0 + 0.5 + 2.0
    assert len(result.reasons) == 4
