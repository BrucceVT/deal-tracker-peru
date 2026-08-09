"""
Tests del motor de decisión (core/deal_engine.py).
"""
import pytest

from core.deal_engine import evaluate


@pytest.fixture
def base_cfg():
    return {
        "deal_engine": {
            "min_score": 2.0,
            "weights": {
                "discount_pct_high": 1.0,
                "below_historical_min": 0.5,
                "below_historical_avg_pct": 2.0,
            },
        },
        "exclude_keywords": [
            "mochila", "funda", "case", "cooler", "cargador", "cable", "soporte",
            "reacondicionado", "reacondicionada", "refurbished", "chromebook",
            "kids", "niños", "básico", "basico",
        ],
    }


@pytest.fixture
def laptop_profile():
    return {
        "min_reference_price": 800,
        "keywords": ["laptop", "notebook", "computadora", "pc gamer", "all in one"],
    }


@pytest.fixture
def shampoo_profile():
    return {
        "min_reference_price": 15,
        "keywords": ["shampoo", "champu", "acondicionador"],
    }


def test_no_signal_no_deal(base_cfg, laptop_profile):
    result = evaluate("Laptop Lenovo LOQ", 3400, 3500, [], base_cfg, laptop_profile)
    assert result.is_deal is False
    assert result.score == 0.0


def test_common_discount_is_ignored(base_cfg, laptop_profile):
    # En laptops (categoría cara), un 30% no es suficiente para ser oferta.
    # Necesita pasar el umbral adaptativo (50% en caras).
    result = evaluate("Laptop HP Pavilion 15 i7", 2800, 4000, [], base_cfg, laptop_profile)
    assert result.score == 0.0
    assert result.is_deal is False


def test_cheap_product_is_gated_out(base_cfg, laptop_profile):
    # Un celular barato de por sí no pasa el piso de laptop (S/800) si se evalúa como laptop.
    result = evaluate("Laptop HP i3 barata", 269, 289, [], base_cfg, laptop_profile)
    assert result.is_deal is False
    assert "no supera el piso" in result.reasons[0]


def test_inflated_marketplace_list_price_does_not_alert(base_cfg, laptop_profile):
    # Descuento tachado por sí solo no alcanza min_score.
    result = evaluate("Laptop Asus Vivobook Pro", 949, 10000, [], base_cfg, laptop_profile)
    assert result.is_deal is False
    assert result.score == 1.0


def test_inflated_discount_plus_weak_booster_still_not_enough(base_cfg, laptop_profile):
    history = [(950.0, 100), (949.0, 90)]
    result = evaluate("Laptop Asus Vivobook Pro", 948, 10000, history, base_cfg, laptop_profile)
    assert result.is_deal is False
    # 1.0 (descuento) + 0.5 (mínimo histórico ya que es 948 vs min 949) = 1.5 < 2.0
    # Pero notar que para que sume como mínimo histórico, el drop vs promedio debe ser >= 15%
    # Aquí el promedio es 949.5, la caída es 0.15% (no llega a 15%), así que el booster de mínimo histórico no se activa.
    assert result.score == 1.0


def test_drastic_discount_confirmed_by_history_alerts(base_cfg, laptop_profile):
    history = [(3900.0, 100), (4000.0, 90)]
    result = evaluate("Laptop Lenovo IdeaPad 5 Ryzen 7 16GB", 475, 4000, history, base_cfg, laptop_profile)
    assert result.is_deal is True
    assert any("Descuento" in r for r in result.reasons)
    assert any("bajo el precio promedio" in r for r in result.reasons)


def test_expensive_historical_drop_alerts_alone(base_cfg, laptop_profile):
    history = [(5000.0, 100), (5000.0, 90), (5000.0, 80)]
    result = evaluate("Laptop Asus Vivobook Pro", 900, None, history, base_cfg, laptop_profile)
    assert result.is_deal is True
    assert any("bajo el precio promedio" in r for r in result.reasons)


def test_moderate_historical_drop_is_ignored(base_cfg, laptop_profile):
    # Caída del 40% es ignorada en laptops si no hay descuento tachado,
    # porque el umbral adaptativo en caras es 50%.
    history = [(3000.0, 100), (3000.0, 90)]
    result = evaluate("Laptop Asus Vivobook Pro", 1800, None, history, base_cfg, laptop_profile)
    assert result.is_deal is False
    assert result.score == 0.5


def test_historical_min_is_only_a_booster(base_cfg, laptop_profile):
    # Caída menor sin promedio (S/3000 -> S/2500 es 16.7% caída, califica para mínimo histórico pero no para promedio)
    history = [(3000.0, 100), (3050.0, 90)]
    result = evaluate("Laptop Asus Vivobook Pro", 2500, None, history, base_cfg, laptop_profile)
    assert result.score == 0.5
    assert result.is_deal is False


def test_historical_signals_need_two_prior_points(base_cfg, laptop_profile):
    history = [(3000.0, 100)]
    result = evaluate("Laptop Asus Vivobook Pro", 1000, 1100, history, base_cfg, laptop_profile)
    assert result.score == 0.0
    assert result.is_deal is False


def test_gate_uses_history_not_current_price(base_cfg, laptop_profile):
    history = [(5000.0, 100), (5000.0, 90)]
    result = evaluate("Laptop Dell XPS", 900, None, history, base_cfg, laptop_profile)
    assert result.is_deal is True


def test_laptop_error_without_context_does_not_alert(base_cfg, laptop_profile):
    result = evaluate("Laptop Lenovo IdeaPad 5 Ryzen 7 16GB", 475, None, [], base_cfg, laptop_profile)
    assert result.is_deal is False
    assert result.score == 0.0


def test_combined_signals_sum_score(base_cfg, laptop_profile):
    history = [(4800.0, 100), (5000.0, 90)]
    result = evaluate("Laptop HP Pavilion 15 i7", 900, 5000, history, base_cfg, laptop_profile)
    assert result.is_deal is True
    # 1.0 (descuento base -82%) + 1.0 (gran oferta -82% >= 60%) + 2.0 (historial) + 0.5 (mínimo) = 4.5
    # S/5000 lista vs hist_avg S/4900 → credible (5000 <= 4900*3=14700) → señal mega activa
    assert result.score == 4.5


def test_refurbished_is_excluded_before_gate(base_cfg, laptop_profile):
    result = evaluate("Laptop Lenovo ThinkPad Reacondicionado i7", 900, 5000, [], base_cfg, laptop_profile)
    assert result.is_deal is False
    assert "Excluido" in result.reasons[0]


def test_chromebook_is_excluded(base_cfg, laptop_profile):
    result = evaluate("Laptop Chromebook HP 14 4GB 64GB", 549, None, [], base_cfg, laptop_profile)
    assert result.is_deal is False
    assert "Excluido" in result.reasons[0]


def test_accessory_keyword_blocks_even_when_expensive(base_cfg, laptop_profile):
    result = evaluate("Mochila para laptop premium de cuero", 900, 5000, [], base_cfg, laptop_profile)
    assert result.is_deal is False
    assert "Excluido" in result.reasons[0]


def test_kids_product_is_excluded(base_cfg, laptop_profile):
    # La exclusión de kids va primero
    result = evaluate('Laptop HP KIDs 7"', 99, None, [], base_cfg, laptop_profile)
    assert result.is_deal is False
    assert "Excluido" in result.reasons[0]


# --- NUEVOS TESTS PARA CATEGORÍAS BARATAS Y ADAPTATIVAS ---

def test_shampoo_normal_discount_is_ignored(base_cfg, shampoo_profile):
    # Un shampoo de S/25 a S/18 (28% descuento) es normal -> se ignora
    result = evaluate("Shampoo Head & Shoulders 375ml", 18, 25, [], base_cfg, shampoo_profile)
    assert result.is_deal is False
    assert result.score == 0.0


def test_shampoo_drastic_drop_alerts(base_cfg, shampoo_profile):
    # Un shampoo de S/25 a S/5 es una caída del 80% (mayor al 70% requerido para baratas) -> alerta
    history = [(25.0, 100), (25.0, 90)]
    result = evaluate("Shampoo Head & Shoulders 375ml", 5, 25, history, base_cfg, shampoo_profile)
    assert result.is_deal is True
    assert result.score >= 2.0


def test_category_keyword_mismatch_blocks(base_cfg, shampoo_profile):
    # Si estamos en la categoría de shampoo, pero se cuela una "crema" que no coincide con las palabras clave -> se excluye
    result = evaluate("Crema Facial Pond's Rejuveness", 5, 25, [], base_cfg, shampoo_profile)
    assert result.is_deal is False
    assert "no coincide con palabras clave" in result.reasons[0]


def test_placeholder_price_99999_does_not_inflate_score(base_cfg):
    """Un historial de precios S/99999 (placeholder de Knasta cuando no tiene dato
    real) NO debe disparar señales de 'por debajo del promedio histórico'.
    El proyector de S/149 con lista S/299 no debe alcanzar score >= 2.0 solo
    por el placeholder; su score real es 1.0 (solo señal de descuento de tienda)."""
    profile = {"min_reference_price": 80}
    # Knasta devolvió dos puntos con precio placeholder S/99999
    fake_history = [(99999.0, 1_000_000), (99999.0, 900_000)]
    result = evaluate(
        "Proyector Inteligente Nium Gol Vision 720P",
        149.0,          # precio actual
        299.0,          # lista/tachado en tienda (-50%)
        fake_history,
        base_cfg,
        profile,
    )
    # Con precio barato (< S/300) se requiere >= 70% de descuento para señal 1.
    # -50% no alcanza el umbral -> score debe ser 0.0
    assert result.is_deal is False
    assert result.score == 0.0


def test_sane_history_still_works_after_filter(base_cfg):
    """Asegurar que el filtro de precios irreales no afecta historiales reales."""
    profile = {"min_reference_price": 250}
    # Monitor a S/509, historial real de S/1449
    real_history = [(1449.0, 1_000_000), (1400.0, 900_000), (1350.0, 800_000)]
    result = evaluate(
        "Monitor Gamer Acer Nitro VG272 27\" 165Hz",
        509.0,
        1449.0,
        real_history,
        base_cfg,
        profile,
    )
    # Descuento de 64% >= 50% umbral (caro) -> señal 1 (+1.0)
    # Caída vs avg (S/1399) = 63.6% >= 50% -> señal 2 (+2.0)
    # S/509 < hist_min S/1350 -> señal 3 (+0.5)
    assert result.is_deal is True
    assert result.score >= 3.0


def test_inflated_list_price_with_market_consensus(base_cfg):
    """
    Caso real de la impresora Brother MFC-T4500DW:
    - Oechsle pone un precio tachado inflado de S/7,199.00
    - Precio oferta: S/2,539.00 (-65% aparente)
    - Pero el consenso de mercado (mediana en Perú) es S/2,789.50
    - Con la validación de consenso de mercado, el descuento real es solo ~9% vs S/2789.50
    - El motor DEBE rechazar la oferta falsa (score = 0.0, is_deal = False).
    """
    profile = {"min_reference_price": 250}
    result = evaluate(
        "IMPRESORA MULTIFUNCIONAL A3 MFC - T4500DW Dúplex ADF Wifi",
        2539.0,                # precio oferta
        7199.0,                # precio tachado inflado de la tienda
        [],                    # sin historial previo
        base_cfg,
        profile,
        market_consensus_price=2789.50 # mediana real del mercado en Perú
    )
    assert result.is_deal is False
    assert result.score == 0.0

