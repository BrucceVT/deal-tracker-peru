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
             price_history: list[tuple[float, float]], cfg: dict, category_profile: dict) -> DealResult:
    """
    Evalúa si un producto es una oferta real basándose en su precio actual,
    el precio de lista de la tienda y su historial de precios (ej. de Knasta).
    
    Aplica límites adaptativos según la categoría (barata vs cara):
    - Categorías Caras (Piso >= S/300): Detección desde 50% de caída.
    - Categorías Baratas (Piso < S/300): Detección desde 70% de caída.
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

    # Extraer historial
    historical_prices = [p for p, _ in price_history if p]
    has_history = len(historical_prices) >= 2
    hist_min = min(historical_prices) if has_history else None
    hist_avg = (sum(historical_prices) / len(historical_prices)) if has_history else None

    # 3. GATE de "Piso de Precio" específico de la categoría
    min_reference_price = category_profile.get("min_reference_price", 0)
    reference_price = max(original_price or 0, hist_avg or 0)
    
    if reference_price < min_reference_price:
        return DealResult(
            is_deal=False, score=0.0,
            reasons=[f"Producto no supera el piso de la categoría (S/{reference_price:.1f} < S/{min_reference_price:.0f})"],
        )

    # 4. Umbrales adaptativos estilo Steam
    is_expensive = reference_price >= 300
    discount_threshold = 50 if is_expensive else 70
    avg_threshold = 50 if is_expensive else 70

    score = 0.0
    reasons = []

    # Señal 1: Descuento tachado declarado por la tienda (refuerzo)
    if original_price and original_price > current_price > 0:
        discount_pct = (1 - current_price / original_price) * 100
        if discount_pct >= discount_threshold:
            score += weights["discount_pct_high"]
            reasons.append(
                f"Descuento de {discount_pct:.0f}% vs precio de lista (S/{original_price:.0f})"
            )

    # Señales 2 y 3: Caída respecto al historial
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
