"""
Módulo de agregación de ofertas multi-tienda.
Agrupa productos idénticos detectados en distintas tiendas para enviar
UNA SOLA tarjeta a Discord con la mejor oferta y enlaces comparativos a las demás.
"""
from dataclasses import dataclass, field
from typing import Any
from core.knasta import extract_clean_model


@dataclass
class StoreDealCandidate:
    store: str
    product: Any         # ScrapedProduct
    deal_result: Any     # DealResult
    product_id: int
    category_url: str


@dataclass
class AggregatedDeal:
    best_offer: StoreDealCandidate
    other_offers: list[StoreDealCandidate] = field(default_factory=list)


def group_deals_by_model(candidates: list[StoreDealCandidate]) -> list[AggregatedDeal]:
    """
    Toma una lista de candidatos a oferta y los agrupa por su modelo de producto.
    Devuelve una lista de AggregatedDeal ordenados con la tienda de menor precio
    como best_offer y las alternativas de otras tiendas en other_offers.
    """
    grouped: dict[str, list[StoreDealCandidate]] = {}

    for cand in candidates:
        model_key = extract_clean_model(cand.product.title)
        if not model_key:
            model_key = cand.product.title.strip().lower()
        else:
            model_key = model_key.strip().lower()

        if model_key not in grouped:
            grouped[model_key] = []
        grouped[model_key].append(cand)

    aggregated_list: list[AggregatedDeal] = []

    for model_key, cand_list in grouped.items():
        # Ordenar los candidatos de este modelo por precio oferta ascendente
        cand_list.sort(key=lambda c: c.product.price)

        # Seleccionar la mejor oferta (menor precio)
        best = cand_list[0]

        # Agrupar las alternativas en OTRAS tiendas (descartando duplicados de la misma tienda)
        other_offers: list[StoreDealCandidate] = []
        seen_stores = {best.store.lower()}

        for alt in cand_list[1:]:
            alt_store = alt.store.lower()
            if alt_store not in seen_stores:
                seen_stores.add(alt_store)
                other_offers.append(alt)

        aggregated_list.append(AggregatedDeal(best_offer=best, other_offers=other_offers))

    return aggregated_list
