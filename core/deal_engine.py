"""
Motor de decisión de ofertas con lógica adaptativa estilo Steam.
"""
import re
from dataclasses import dataclass, field

@dataclass
class DealResult:
    is_deal: bool
    score: float
    reasons: list = field(default_factory=list)

def _contains_word(title_lower: str, word: str) -> bool:
    """Match por palabra completa (no substring) para evitar falsos positivos."""
    return re.search(rf"\b{re.escape(word.lower())}\b", title_lower) is not None

def evaluate(product_title: str, current_price: float, original_price: float | None,
             price_history: list[tuple[float, float]], cfg: dict, category_profile: dict,
             market_consensus_price: float | None = None) -> DealResult:
    """
    Evalúa si un producto es una oferta real basándose en su precio actual,
    el precio de lista de la tienda, su historial propio y el consenso de mercado.
    """
    de = cfg["deal_engine"]
    weights = de["weights"]
    min_score = de["min_score"]
    exclude_keywords = cfg.get("exclude_keywords", [])

    title_lower = product_title.lower()

    # 1. Filtro global de exclusión (accesorios, reacondicionados, etc.)
    if any(_contains_word(title_lower, kw) for kw in exclude_keywords):
        return DealResult(is_deal=False, score=0.0,
                          reasons=["Excluido: parece accesorio o gama que no interesa"])

    # 2. Filtro de palabras clave de la categoría
    category_keywords = category_profile.get("keywords", [])
    if category_keywords and not any(_contains_word(title_lower, kw) for kw in category_keywords):
        return DealResult(is_deal=False, score=0.0,
                          reasons=["Excluido: no coincide con palabras clave de la categoría"])

    # Extraer historial, descartando precios placeholder/irreales.
    MAX_SANE_PRICE = 50_000
    historical_prices = [
        p for p, _ in price_history
        if p and 0 < p <= MAX_SANE_PRICE and p <= current_price * 10
    ]
    has_history = len(historical_prices) >= 2
    hist_min = min(historical_prices) if has_history else None
    hist_avg = (sum(historical_prices) / len(historical_prices)) if has_history else None

    # Validar si el precio de lista de la tienda está inflado respecto al mercado
    effective_original_price = original_price
    if market_consensus_price and original_price:
        if original_price > market_consensus_price * 1.25:
            # El precio tachado de la tienda es irrealo inflado (ej: S/7199 vs S/2789 en mercado)
            effective_original_price = market_consensus_price

    # 3. GATE de "Piso de Precio" específico de la categoría
    min_reference_price = category_profile.get("min_reference_price", 0)
    reference_price = max(effective_original_price or 0, hist_avg or 0, market_consensus_price or 0)

    if reference_price < min_reference_price:
        return DealResult(
            is_deal=False, score=0.0,
            reasons=[f"Producto no supera el piso de la categoría (S/{reference_price:.1f} < S/{min_reference_price:.0f})"],
        )

    # 4. Umbrales adaptativos estilo Steam
    is_expensive = reference_price >= 300
    discount_threshold = 50 if is_expensive else 70        # umbral base de descuento tachado
    avg_threshold = 50 if is_expensive else 70
    market_threshold = 25 if is_expensive else 35         # umbral de caída real vs mediana del mercado

    score = 0.0
    reasons = []

    # Señal 1: Descuento tachado declarado por la tienda (máximo +1.0)
    # Sirve como booster secundario, pero NUNCA da el pase automático de 2.0 por sí solo
    # (evita falsas ofertas por precios tachados inflados de las tiendas).
    if effective_original_price and effective_original_price > current_price > 0:
        discount_pct = (1 - current_price / effective_original_price) * 100
        if discount_pct >= discount_threshold:
            score += weights["discount_pct_high"]
            reasons.append(
                f"Descuento de {discount_pct:.0f}% vs precio de lista (S/{effective_original_price:.0f})"
            )

    # Señal 2: Caída real respecto al Consenso de Mercado en Perú
    if market_consensus_price and market_consensus_price > current_price > 0:
        market_drop_pct = (1 - current_price / market_consensus_price) * 100
        if market_drop_pct >= market_threshold:
            # Si la caída vs mercado es masiva (≥40%), otorga +2.0 (oferta clara de mercado)
            market_weight = weights["below_historical_avg_pct"] if market_drop_pct >= 40 else weights["discount_pct_high"]
            score += market_weight
            reasons.append(
                f"{market_drop_pct:.0f}% bajo la mediana del mercado en Perú (S/{market_consensus_price:.0f})"
            )

    # Señales 3 y 4: Caída respecto al historial propio de la tienda
    if has_history:
        if hist_avg > 0:
            avg_drop_pct = (1 - current_price / hist_avg) * 100
            if avg_drop_pct >= avg_threshold:
                score += weights["below_historical_avg_pct"]
                reasons.append(
                    f"{avg_drop_pct:.0f}% bajo el precio promedio histórico (S/{hist_avg:.0f})"
                )

        if current_price < hist_min:
            # Exigir al menos un 15% de caída respecto al promedio para que sume como récord
            avg_drop = (1 - current_price / hist_avg) * 100 if hist_avg else 0
            if avg_drop >= 15:
                score += weights["below_historical_min"]
                reasons.append(f"Mínimo histórico registrado (antes S/{hist_min:.0f})")

    return DealResult(is_deal=score >= min_score, score=round(score, 2), reasons=reasons)
