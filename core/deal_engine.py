"""
Motor de decisión de ofertas.

Combina varias señales en un score. Si el score >= min_score,
el producto se considera una "oferta real" y se dispara alerta.

Señales:
  1. discount_pct_high     -> % de descuento (precio tachado vs precio actual) es grande
  2. below_price_ceiling   -> precio absoluto cae dentro del rango [floor, ceiling] de su categoría
  3. below_historical_min  -> es el precio más bajo jamás visto para ese producto
  4. below_historical_avg  -> está X% bajo el promedio histórico del producto

Regla de combinación: below_price_ceiling NUNCA dispara una oferta ella sola,
tiene que venir acompañada de al menos otra señal. Motivo (encontrado
validando en vivo el 2026-07-19): muchos productos de gama baja viven
SIEMPRE dentro del rango floor/ceiling de su categoría sin que eso sea un
error de precio — es simplemente su precio normal de lista.
"""
import re
from dataclasses import dataclass, field


@dataclass
class DealResult:
    is_deal: bool
    score: float
    reasons: list = field(default_factory=list)


def _contains_word(title_lower: str, word: str) -> bool:
    """Match por palabra completa (no substring) para evitar falsos positivos
    como "tablet" matcheando dentro de "tableta gráfica"."""
    return re.search(rf"\b{re.escape(word.lower())}\b", title_lower) is not None


def _match_category(title: str, price_ceiling: dict):
    title_lower = title.lower()
    for category, bounds in price_ceiling.items():
        if _contains_word(title_lower, category):
            return category, bounds
    return None, None


def evaluate(product_title: str, current_price: float, original_price: float | None,
             price_history: list[tuple[float, float]], cfg: dict) -> DealResult:
    """
    price_history: lista de (price, timestamp) más antiguo->reciente no garantizado,
    se asume que puede incluir el precio actual o no.
    """
    weights = cfg["deal_engine"]["weights"]
    min_score = cfg["deal_engine"]["min_score"]
    discount_threshold = cfg["deal_engine"]["discount_pct_threshold"]
    avg_threshold = cfg["deal_engine"]["historical_avg_pct_threshold"]
    exclude_keywords = cfg.get("exclude_keywords", [])

    title_lower = product_title.lower()

    # Filtro de exclusión: accesorios que calzan por texto dentro de una
    # categoría (ej. "mochila para laptop") pero no son el producto real.
    if any(_contains_word(title_lower, kw) for kw in exclude_keywords):
        return DealResult(is_deal=False, score=0.0, reasons=["Excluido: parece accesorio, no producto"])

    score = 0.0
    reasons = []
    signals_fired = []  # nombres de las señales que se activaron, para la regla de combinación

    # Señal 1: descuento vs precio original mostrado por la tienda
    if original_price and original_price > current_price > 0:
        discount_pct = (1 - current_price / original_price) * 100
        if discount_pct >= discount_threshold:
            score += weights["discount_pct_high"]
            reasons.append(f"Descuento de {discount_pct:.0f}% vs precio de lista")
            signals_fired.append("discount_pct_high")

    # Señal 2: precio absoluto dentro del rango [floor, ceiling] de la categoría.
    # El floor evita que un precio absurdamente bajo (accesorio mal filtrado)
    # se confunda con un "error de precio" real del producto. Esta señal NO
    # puede disparar una oferta ella sola (ver regla de combinación más abajo):
    # muchos productos de gama baja viven permanentemente dentro del rango sin
    # que eso sea un error de precio, solo su precio normal de lista.
    category, bounds = _match_category(product_title, cfg["price_ceiling"])
    if bounds:
        floor = bounds.get("floor", 0)
        ceiling = bounds["ceiling"]
        if floor <= current_price <= ceiling:
            score += weights["below_price_ceiling"]
            reasons.append(f"Precio S/{current_price:.0f} en rango de '{category}' (S/{floor}-{ceiling})")
            signals_fired.append("below_price_ceiling")

    # Señal 3 y 4: comparación con historial de precios de ESTE producto
    historical_prices = [p for p, _ in price_history if p]
    if len(historical_prices) >= 2:  # necesita al menos un punto previo real
        hist_min = min(historical_prices)
        hist_avg = sum(historical_prices) / len(historical_prices)

        if current_price < hist_min:
            score += weights["below_historical_min"]
            reasons.append(f"Precio más bajo histórico registrado (antes S/{hist_min:.0f})")
            signals_fired.append("below_historical_min")

        if hist_avg > 0:
            avg_drop_pct = (1 - current_price / hist_avg) * 100
            if avg_drop_pct >= avg_threshold:
                score += weights["below_historical_avg_pct"]
                reasons.append(f"{avg_drop_pct:.0f}% bajo el precio promedio histórico")
                signals_fired.append("below_historical_avg_pct")

    # Regla de combinación: "rango de precio" sola no basta para alertar.
    # Sin esto, cualquier producto barato que viva SIEMPRE dentro del rango
    # (no un error de precio, solo su precio normal) dispararía alerta en
    # cada primer escaneo, antes incluso de tener historial que lo confirme.
    only_price_ceiling_fired = signals_fired == ["below_price_ceiling"]
    if only_price_ceiling_fired:
        is_deal = False
        reasons.append("Precio en rango pero sin otra señal que lo confirme (esperando más historial)")
    else:
        is_deal = score >= min_score

    return DealResult(is_deal=is_deal, score=round(score, 2), reasons=reasons)
