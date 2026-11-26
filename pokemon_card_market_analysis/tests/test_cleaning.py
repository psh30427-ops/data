import pandas as pd
import pytest

from main import collect
from src.cleaning import clean


def test_collect_missing_and_malformed_input(tmp_path):
    with pytest.raises(ValueError, match="원본 CSV"):
        collect(tmp_path)
    (tmp_path / "psa_sales.csv").write_text("date,price\n2025-01-01,50\n", encoding="utf-8")
    with pytest.raises(ValueError, match="필수 열 누락"):
        collect(tmp_path)


def test_collect_separates_sources(full_import):
    counts = collect(full_import / "data/raw").groupby(["source", "data_type"]).size()
    assert counts.to_dict() == {("PSA", "sale"): 160, ("PriceCharting", "market_estimate"): 1,
                                ("PriceCharting", "sale"): 1}


def test_price_date_identity_missing_and_duplicates(cards, observation):
    card = cards[0]
    data = pd.DataFrame([
        observation(card, sale_id="same", price_usd="$1,200.50", date="2025/01/06", grade="PSA 10"),
        observation(card, sale_id="same", price_usd="1200.50"),
        observation(card, sale_id="different", price_usd="$1,200.50"),
        observation(card, price_usd="USD 1,200.50"),
        observation(card, language="ja"),
        observation(card, grade="9"),
        observation(card, card_number="999"),
        observation(card, date="06/01/2025"),
        observation(card, price_usd=""),
        observation(card, price_usd="1,00"),
        observation(card, currency="JPY"),
    ])
    valid, quality = clean(data, cards)
    assert valid["price_usd"].tolist() == [1200.5] * 3
    assert set(valid["date"].dt.strftime("%Y-%m-%d")) == {"2025-01-06"}
    assert quality.groupby("outcome")["rows"].sum().to_dict() == {
        "accepted": 3, "card_identity_mismatch": 3, "duplicate_sale_id": 1,
        "invalid_date": 1, "invalid_price": 2, "invalid_fx": 1,
    }


def test_same_id_conflicts_and_outlier_preservation(cards, observation):
    card = cards[0]
    rows = [observation(card, price_usd=str(p)) for p in [90, 91, 92, 93, 95, 1000]]
    rows.extend([observation(card, sale_id="x"), observation(card, sale_id="x", price_usd="85")])
    clean_rows, quality = clean(pd.DataFrame(rows), cards)
    assert clean_rows.loc[clean_rows["outlier_iqr"], "price_usd"].tolist() == [1000]
    assert quality.loc[quality["outcome"].eq("conflicting_sale_id"), "rows"].sum() == 2
