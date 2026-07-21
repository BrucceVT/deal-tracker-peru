"""
Tests del motor de decisión (core/deal_engine.py).

Filosofía (recalibrado 2026-07-20 a pedido del usuario): el motor caza ERRORES
DE PRECIO en productos que NORMALMENTE son CAROS — una caída drástica (>=80%)
de su precio real. El precio absoluto NO es señal (un equipo barato de por sí
no interesa). Se eliminaron los rangos floor/ceiling por categoría.

Reglas clave:
- GATE de "producto caro": si ni el precio de lista tachado ni el promedio
  histórico superan min_reference_price (S/800), se descarta sin evaluar.
- ÚNICA ancla que dispara sola (peso 2.0): caída >=80% vs el promedio
  histórico propio — la mide el tracker, no se puede falsificar.
- discount_pct_high (descuento tachado) es REFUERZO débil (peso 1.0), nunca
  alcanza min_score solo ni combinado solo con below_historical_min (0.5):
  caso real (2026-07-20) — "Tablet Redmi Pad 2 a S/949, antes S/10,000" (91%
  dto.) alertó 4 veces en producción; resultó ser el mismo vendedor de
  marketplace repitiendo el idéntico "antes S/10,000" en otro producto
  ("Poco Pad M1"). El precio tachado lo declara el vendedor y nunca cambia
  entre escaneos — no es señal confiable por sí sola.
"""
import pytest

from core.deal_engine import evaluate


@pytest.fixture
def base_cfg():
    # Refleja la calibración real de config.yaml post-2026-07-20 (fix del
    # fraude de precio tachado inflado).
    return {
        "deal_engine": {
            "min_score": 2.0,
            "min_reference_price": 800,
            "weights": {
                "discount_pct_high": 1.0,
                "below_historical_min": 0.5,
                "below_historical_avg_pct": 2.0,
            },
            "discount_pct_threshold": 80,
            "historical_avg_pct_threshold": 80,
        },
        "exclude_keywords": [
            "mochila", "funda", "case", "cooler", "cargador", "cable", "soporte",
            "reacondicionado", "reacondicionada", "refurbished", "chromebook",
            "kids", "niños", "básico", "basico",
        ],
    }


def test_no_signal_no_deal(base_cfg):
    # Producto caro sin descuento ni historial: nada que disparar.
    result = evaluate("Laptop HP 15 pulgadas i5", 3400, 3500, [], base_cfg)
    assert result.is_deal is False
    assert result.score == 0.0


def test_common_discount_is_ignored(base_cfg):
    # 50% de descuento es una oferta común, NO un error de precio (<80%).
    result = evaluate("Monitor Samsung 27 pulgadas", 500, 1000, [], base_cfg)
    assert result.score == 0.0
    assert result.is_deal is False


def test_cheap_product_is_gated_out(base_cfg):
    # El caso que motivó el gate: "Smartphone ZTE Blade A35E a S/269, antes
    # S/289". Producto barato de por sí (ref S/289 < piso S/800) -> ni se evalúa.
    result = evaluate("Smartphone ZTE Blade A35E 2+64GB", 269, 289, [], base_cfg)
    assert result.is_deal is False
    assert result.score == 0.0
    assert "piso de 'caro'" in result.reasons[0]


def test_inflated_marketplace_list_price_does_not_alert(base_cfg):
    # CASO REAL (2026-07-20): "Tablet Xiaomi Redmi Pad 2 256GB, S/949, antes
    # S/10,000" (91% dto.) — el precio real de mercado de esa tablet es
    # ~S/1,200. El mismo vendedor repitió el idéntico "antes S/10,000" en un
    # producto totalmente distinto (Poco Pad M1). Descuento tachado por sí
    # solo, sin historial que lo confirme, ya NO alcanza min_score.
    result = evaluate("Tablet Xiaomi Redmi Pad 2 256GB 8GB", 949, 10000, [], base_cfg)
    assert result.is_deal is False
    assert result.score == 1.0


def test_inflated_discount_plus_weak_booster_still_not_enough(base_cfg):
    # Cierra la rendija: si el precio fraudulento alguna vez cae levemente por
    # debajo de su propio mínimo previo (ruido normal de un marketplace), NO
    # debe combinarse con el descuento tachado para alcanzar min_score
    # (1.0 + 0.5 = 1.5 < 2.0). Solo la caída histórica real (ancla) debe poder
    # completar el score.
    history = [(950.0, 100), (949.0, 90)]  # nunca vimos esta tablet cara de verdad
    result = evaluate("Tablet Xiaomi Redmi Pad 2 256GB 8GB", 948, 10000, history, base_cfg)
    assert result.is_deal is False
    assert result.score == 1.5


def test_drastic_discount_confirmed_by_history_alerts(base_cfg):
    # El arquetipo del usuario: laptop buena a S/475 (antes ~S/4,000), y el
    # propio tracker YA había visto esta laptop cara antes -> la caída
    # histórica (ancla) confirma el error; el descuento tachado solo suma.
    history = [(3900.0, 100), (4000.0, 90)]
    result = evaluate("Laptop Lenovo IdeaPad 5 Ryzen 7 16GB", 475, 4000, history, base_cfg)
    assert result.is_deal is True
    assert any("Descuento" in r for r in result.reasons)
    assert any("bajo el precio promedio" in r for r in result.reasons)


def test_expensive_historical_drop_alerts_alone(base_cfg):
    # Producto que siempre costó ~S/5000 y aparece a S/900 (82% bajo su
    # promedio): error de precio aunque no haya tachado. Señal fake-proof,
    # ÚNICA que dispara sola.
    history = [(5000.0, 100), (5000.0, 90), (5000.0, 80)]
    result = evaluate("Laptop Asus Vivobook Pro", 900, None, history, base_cfg)
    assert result.is_deal is True
    assert any("bajo el precio promedio" in r for r in result.reasons)


def test_moderate_historical_drop_is_ignored(base_cfg):
    # 60% bajo el promedio ya no basta (umbral 80%). Solo queda el refuerzo
    # de mínimo histórico (0.5) -> por debajo de min_score.
    history = [(3000.0, 100), (3000.0, 90)]
    result = evaluate("Laptop Asus Vivobook Pro", 1200, None, history, base_cfg)
    assert result.is_deal is False
    assert result.score == 0.5


def test_historical_min_is_only_a_booster(base_cfg):
    # Ser el mínimo histórico por sí solo (S/3000 -> S/2900) no es un error:
    # peso 0.5 < min_score 2.0.
    history = [(3000.0, 100), (3050.0, 90)]
    result = evaluate("Laptop Asus Vivobook Pro", 2900, None, history, base_cfg)
    assert result.score == 0.5
    assert result.is_deal is False


def test_historical_signals_need_two_prior_points(base_cfg):
    # Con menos de 2 puntos históricos no hay base de comparación confiable.
    history = [(3000.0, 100)]
    result = evaluate("Laptop Asus Vivobook Pro", 1000, 1100, history, base_cfg)
    assert result.score == 0.0
    assert result.is_deal is False


def test_gate_uses_history_not_current_price(base_cfg):
    # El gate mira el valor REAL (promedio histórico), no el precio actual
    # bajo. Un producto caro (avg S/5000) en error (S/900) pasa el gate aunque
    # su precio actual esté muy por debajo del piso de S/800.
    history = [(5000.0, 100), (5000.0, 90)]
    result = evaluate("Laptop Dell XPS", 900, None, history, base_cfg)
    assert result.is_deal is True


def test_laptop_error_without_context_does_not_alert(base_cfg):
    # Tradeoff aceptado: una laptop a S/475 SIN tachado y SIN historial ya no
    # se puede confirmar como error (no sabemos su precio real) -> no alerta.
    result = evaluate("Laptop Lenovo IdeaPad 5 Ryzen 7 16GB", 475, None, [], base_cfg)
    assert result.is_deal is False
    assert result.score == 0.0


def test_combined_signals_sum_score(base_cfg):
    # Error total: descuento tachado + mínimo histórico + caída >=80% vs
    # promedio, todos apuntando en la misma dirección.
    history = [(4800.0, 100), (5000.0, 90)]
    result = evaluate("Laptop HP Pavilion 15 i7", 900, 5000, history, base_cfg)
    assert result.is_deal is True
    assert result.score == 3.5  # 1.0 + 0.5 + 2.0
    assert len(result.reasons) == 3


def test_refurbished_is_excluded_before_gate(base_cfg):
    # La exclusión corre antes que todo: un reacondicionado no alerta ni aunque
    # tuviera un descuento drástico.
    result = evaluate("Laptop Lenovo ThinkPad Reacondicionado i7", 900, 5000, [], base_cfg)
    assert result.is_deal is False
    assert "Excluido" in result.reasons[0]


def test_chromebook_is_excluded(base_cfg):
    result = evaluate("Laptop Chromebook HP 14 4GB 64GB", 549, None, [], base_cfg)
    assert result.is_deal is False
    assert "Excluido" in result.reasons[0]


def test_accessory_keyword_blocks_even_when_expensive(base_cfg):
    result = evaluate("Mochila para laptop premium de cuero", 900, 5000, [], base_cfg)
    assert result.is_deal is False
    assert "Excluido" in result.reasons[0]


def test_kids_product_is_excluded(base_cfg):
    result = evaluate('Tablet Advance KIDs 7" 3G Dual SIM', 99, None, [], base_cfg)
    assert result.is_deal is False
    assert "Excluido" in result.reasons[0]
