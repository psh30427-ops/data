import pandas as pd
import pytest

from src.market_index import market_index


def test_fixed_basket_missing_price_does_not_change_denominator():
    data = pd.DataFrame({"a": [10, 20, 40, 40], "b": [None, 50, None, 75]},
                        index=pd.date_range("2025-01-05", periods=4, freq="7D"))
    index, normalized = market_index(data, ["a", "b"])
    assert index["pcpi"].iloc[1] == 100
    assert index["pcpi"].iloc[3] == pytest.approx(175)
    assert index["observed_cards"].tolist() == [1, 2, 1, 2]
    assert index["included_cards"].tolist() == [0, 2, 0, 2]
    assert pd.isna(index["pcpi"].iloc[2])
    assert pd.isna(normalized["a"].iloc[0])


def test_no_complete_week_no_index():
    data = pd.DataFrame({"a": [1], "b": [None]}, index=pd.date_range("2025-01-05", periods=1))
    index, _ = market_index(data, ["a", "b"])
    assert index["pcpi"].isna().all()
    assert index["base_week"].isna().all()


def test_same_basket_keeps_missing_source_weeks_blank():
    from src.market_index import compare_source_indices

    rows = [
        ("PSA", "a", "2025-01-02", 100),
        ("PSA", "b", "2025-01-02", 50),
        ("PSA", "a", "2025-01-07", 120),
        ("PSA", "b", "2025-01-09", 60),
        ("CompSniper", "a", "2025-01-02", 200),
        ("CompSniper", "b", "2025-01-07", 80),
        ("CompSniper", "extra", "2025-01-07", 200),
    ]
    data = pd.DataFrame(rows, columns=["source", "card_id", "date", "price_usd"]).assign(data_type="sale")
    data["date"] = pd.to_datetime(data["date"])
    by_source, coverage = compare_source_indices(data, ["a", "b"], "2025-01-01", "2025-01-12")
    assert by_source.loc[by_source["source"].eq("PSA"), "pcpi"].tolist() == [100, 120]
    ebay = by_source.loc[by_source["source"].eq("CompSniper")]
    assert ebay["pcpi"].isna().all()
    assert ebay["missing_card_ids"].tolist() == ["b", "a"]
    assert coverage.loc[coverage["source"].eq("CompSniper"), "sales_shortfall_to_100"].tolist() == [99, 99]
