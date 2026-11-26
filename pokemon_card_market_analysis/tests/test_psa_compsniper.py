from pathlib import Path
import json

import pandas as pd
import pytest

from src.collectors.psa_collector import collect, fetch_recent
from src.source_validation import compare_ebay_sales


def test_psa_lookup_validates_catalog_and_excludes_mismatch(tmp_path, cards):
    specs = json.loads((Path(__file__).parents[1] / "config/psa_specs.json").read_text())
    card = cards[0]
    spec = specs[card["card_id"]]
    sale = dict(possibleMismatch=False, gradingCompany="PSA", grade="10", certNumber="123",
                saleId="1", url="https://www.ebay.com/itm/123", marketplace="eBay",
                saleDate="2025-01-05", salePrice=100, saleType="Auction")
    response = {
        "card": {"specId": spec["spec_id"], "subject": card["card_name"], "cardNumber": "#085",
                 "setName": "POKEMON SVP EN-SCARLET & VIOLET BLACK STAR PROMOS", "year": "2023"},
        "summary": {"currency": "USD"},
        "items": [sale, {**sale, "saleId": "2", "possibleMismatch": True}],
    }

    def request(path, params):
        assert path == "/v1/psa/card"
        assert params == {"specId": spec["spec_id"], "count": 50, "timeRange": 0, "grade": "10"}
        return response

    assert fetch_recent(tmp_path, card, spec, request) == (2, 1, "2025-01-05")
    assert collect(tmp_path).iloc[0]["cert_number"] == "123"
    response["card"]["cardNumber"] = "#999"
    with pytest.raises(ValueError, match="재확인"):
        fetch_recent(tmp_path, card, spec, request)


def test_overlap_counts_disagreement_and_avoids_ambiguous_listing():
    base = dict(data_type="sale", marketplace="eBay", card_id="svp-85", price_usd=100)
    rows = []
    for item in ("123", "456"):
        rows.append({**base, "source": "PSA", "source_url": f"https://www.ebay.com/itm/{item}",
                     "date": "2025-01-01"})
        rows.append({**base, "source": "CompSniper", "source_url": f"https://ebay.com/itm/pikachu/{item}?a=b",
                     "date": "2025-01-02"})
    rows.append(rows[-1])
    pairs, summary = compare_ebay_sales(pd.DataFrame(rows))
    assert pairs["ebay_id"].tolist() == ["123"]
    assert summary.iloc[0][["matched_listings", "same_date", "same_price"]].tolist() == [1, 0, 1]


def test_history_uses_only_single_unit_sold_price():
    from src.collectors.compsniper_collector import history_listing

    row = dict(recordType="single_unit_listing", soldUnits=1, soldDate="2025-01-05",
               soldPrice={"amount": "100", "currency": "USD"},
               averageSoldPrice={"amount": "500", "currency": "USD"})
    assert history_listing(row)["soldPrice"] == "100"
    assert history_listing({**row, "soldUnits": 2}) is None
    assert history_listing({**row, "recordType": "listing_aggregate"}) is None


def test_goldin_keeps_premium_inclusive_usd_sale(tmp_path, cards):
    from datetime import date
    from src.collectors import goldin_collector

    sale = dict(title="2023 Pokemon SVP EN #085 Pikachu Grey Felt Hat PSA GEM MT 10",
                gradingService="PSA", grade="10", currency="USD", saleId="lot001",
                url="https://goldin.co/item/test", soldAt="2025-07-11T00:00:00Z",
                price=1244.40, hammerPrice=1020)
    payload = {"items": [sale, {**sale, "saleId": "lot002", "title": sale["title"] + " Signed"}]}
    assert goldin_collector.store_page(tmp_path, cards[0], payload, 1,
                                       date(2025, 1, 1), date(2026, 11, 25)) == (2, 1, False)
    result = goldin_collector.collect(tmp_path).iloc[0]
    assert result["source"] == "Goldin"
    assert float(result["original_price"]) == 1244.40
