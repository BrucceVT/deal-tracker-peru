"""
Motor de decisión de ofertas.

Combina varias señales en un score. Si el score >= min_score,
el producto se considera una "oferta real" y se dispara alerta.

FILOSOFÍA (recalibrado 2026-07-20 a pedido del usuario): el objetivo son
ERRORES DE PRECIO en productos que NORMALMENTE son CAROS — una caída drástica
(>=80%) de su precio real. El precio absoluto YA NO es señal: un equipo barato
de por sí no interesa ("normalmente son malos", pedido del usuario). Se
eliminaron los rangos floor/ceiling por categoría.

Flujo:
  0. Exclusión por keywords (accesorios, reacondicionados, chromebooks…).
  1. GATE de "producto caro": el valor real del producto es su precio de lista
     tachado o su promedio histórico — NUNCA el precio actual (que en un error
     es justamente el bajo). Si esa referencia no supera min_reference_price, se
     descarta sin evaluar señales.
  2. Señales:
     - discount_pct_high    -> descuento tachado >=80%. REFUERZO (peso bajo):
       el precio tachado lo declara el vendedor y es 100% falsificable — caso
       real (2026-07-20): "Tablet Redmi Pad 2 a S/949, antes S/10,000" (91%
       dto., alertó 4 veces) resultó ser el mismo vendedor de marketplace
       repitiendo el idéntico "antes S/10,000" en otro producto distinto. Ya
       NUNCA dispara sola ni combinada solo con below_historical_min.
     - below_historical_avg -> caída >=80% vs el promedio histórico propio.
       ÚNICA ANCLA: dispara sola — esta la mide el propio tracker, no se
       puede falsificar desde afuera.
     - below_historical_min -> es el precio más bajo jamás visto (refuerzo 0.5).
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
    como excluir "case" dentro de una palabra que solo lo contiene."""
    return re.search(rf"\b{re.escape(word.lower())}\b", title_lower) is not None


def evaluate(product_title: str, current_price: float, original_price: float | None,
             price_history: list[tuple[float, float]], cfg: dict) -> DealResult:
    """
    price_history: lista de (price, timestamp) más antiguo->reciente no garantizado,
    se asume que puede incluir el precio actual o no.
    """
    de = cfg["deal_engine"]
    weights = de["weights"]
    min_score = de["min_score"]
    discount_threshold = de["discount_pct_threshold"]
    avg_threshold = de["historical_avg_pct_threshold"]
    min_reference_price = de.get("min_reference_price", 0)
    exclude_keywords = cfg.get("exclude_keywords", [])

    title_lower = product_title.lower()

    # Paso 0: filtro de exclusión. Accesorios que calzan por texto ("mochila
    # para laptop"), reacondicionados y chromebooks (baratos legítimos).
    if any(_contains_word(title_lower, kw) for kw in exclude_keywords):
        return DealResult(is_deal=False, score=0.0,
                          reasons=["Excluido: parece accesorio o gama que no interesa"])

    # Historial propio del producto (fake-proof: lo mide el propio tracker).
    historical_prices = [p for p, _ in price_history if p]
    has_history = len(historical_prices) >= 2  # necesita al menos un punto previo real
    hist_min = min(historical_prices) if has_history else None
    hist_avg = (sum(historical_prices) / len(historical_prices)) if has_history else None

    # Paso 1: GATE de "producto caro". La referencia del valor real es el precio
    # de lista tachado o el promedio histórico — NUNCA el precio actual (en un
    # error es justamente el bajo). Los equipos que de por sí son baratos se
    # descartan de raíz, sin importar el descuento.
    reference_price = max(original_price or 0, hist_avg or 0)
    if reference_price < min_reference_price:
        return DealResult(
            is_deal=False, score=0.0,
            reasons=[f"Producto no supera el piso de 'caro' (S/{min_reference_price:.0f}); "
                     f"los equipos baratos no interesan"],
        )

    score = 0.0
    reasons = []

    # Señal 1 (REFUERZO, no ancla): descuento drástico >=80% vs el precio tachado
    # de la tienda. El vendedor controla ese número, así que solo suma puntos —
    # nunca decide una alerta por sí sola (ver docstring del módulo).
    if original_price and original_price > current_price > 0:
        discount_pct = (1 - current_price / original_price) * 100
        if discount_pct >= discount_threshold:
            score += weights["discount_pct_high"]
            reasons.append(
                f"Descuento de {discount_pct:.0f}% vs precio de lista (S/{original_price:.0f})"
            )

    # Señales 2 y 3: caída respecto al historial propio del producto.
    if has_history:
        if current_price < hist_min:
            score += weights["below_historical_min"]
            reasons.append(f"Precio más bajo histórico registrado (antes S/{hist_min:.0f})")

        if hist_avg > 0:
            avg_drop_pct = (1 - current_price / hist_avg) * 100
            if avg_drop_pct >= avg_threshold:  # ANCLA
                score += weights["below_historical_avg_pct"]
                reasons.append(
                    f"{avg_drop_pct:.0f}% bajo el precio promedio histórico (S/{hist_avg:.0f})"
                )

    return DealResult(is_deal=score >= min_score, score=round(score, 2), reasons=reasons)
