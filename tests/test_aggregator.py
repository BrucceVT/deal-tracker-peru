"""
Tests unitarios para core/aggregator.py.
"""
from dataclasses import dataclass
from core.aggregator import StoreDealCandidate, group_deals_by_model

@dataclass
class DummyProduct:
    title: str
    price: float
    original_price: float
    url: str
    in_stock: bool = True
    image_url: str = None

@dataclass
class DummyDealResult:
    score: float = 2.5
    reasons: list = None

def test_group_deals_by_model_selects_lowest_price():
    p1 = DummyProduct(title="Monitor Gamer Acer Nitro VG272 27\" 165Hz", price=509.0, original_price=1449.0, url="https://oechsle.pe/p1")
    p2 = DummyProduct(title="Monitor Gamer Acer Nitro VG272 LVBMIIPX 27\" Full HD 165Hz", price=458.10, original_price=1449.0, url="https://plazavea.pe/p2")
    p3 = DummyProduct(title="Monitor Gamer Acer Nitro VG272 27 Inch", price=599.0, original_price=1449.0, url="https://promart.pe/p3")

    c1 = StoreDealCandidate(store="oechsle", product=p1, deal_result=DummyDealResult(), product_id=1, category_url="")
    c2 = StoreDealCandidate(store="plazavea", product=p2, deal_result=DummyDealResult(), product_id=2, category_url="")
    c3 = StoreDealCandidate(store="promart", product=p3, deal_result=DummyDealResult(), product_id=3, category_url="")

    aggregated = group_deals_by_model([c1, c2, c3])

    assert len(aggregated) == 1
    agg = aggregated[0]

    # La mejor oferta debe ser PlazaVea a S/ 458.10
    assert agg.best_offer.store == "plazavea"
    assert agg.best_offer.product.price == 458.10

    # Las alternativas deben incluir Oechsle y Promart
    assert len(agg.other_offers) == 2
    alt_stores = {alt.store for alt in agg.other_offers}
    assert alt_stores == {"oechsle", "promart"}
