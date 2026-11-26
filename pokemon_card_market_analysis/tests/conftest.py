import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cards():
    return [{**card, "selected": True}
            for card in json.loads((ROOT / "config/cards.json").read_text(encoding="utf-8"))
            if card["language"] == "en"]


@pytest.fixture
def observation():
    def make(card, **values):
        row = {key: value for key, value in card.items() if key != "catalog_url"}
        row.update(date="2025-01-06", price_usd="100", currency="USD", marketplace="eBay",
                   sale_type="auction", sale_id="", cert_number="", source="PSA", data_type="sale",
                   source_url="https://example.org/test", collected_at="2026-11-26", input_file="test.csv")
        row.update(values)
        return row

    return make


@pytest.fixture
def full_import(tmp_path, cards, observation):
    raw = tmp_path / "data/raw"
    raw.mkdir(parents=True)
    config = tmp_path / "config"
    config.mkdir()
    (config / "cards.json").write_text(json.dumps(cards), encoding="utf-8")
    rows = []
    for ci, card in enumerate(cards):
        for wi, day in enumerate(pd.date_range("2025-01-06", periods=5, freq="7D")):
            counts = [2, 3, 5, 2, 4]
            for ti in range(counts[wi]):
                rows.append(observation(card, date=day.strftime("%Y-%m-%d"),
                                        price_usd=str((ci + 1) * [100, 130, 80, 140, 120][wi]),
                                        sale_id=f"{ci}-{wi}-{ti}"))
    pd.DataFrame(rows).to_csv(raw / "psa_sales.csv", index=False)
    pd.DataFrame([observation(cards[0], price_usd="95")]).to_csv(raw / "pricecharting_market.csv", index=False)
    pd.DataFrame([observation(cards[0], sale_id=rows[0]["sale_id"])]).to_csv(
        raw / "pricecharting_sales.csv", index=False
    )
    pd.DataFrame([dict(card_id=card["card_id"], start_date="2025-01-06", end_date="2025-02-09")
                  for card in cards]).to_csv(raw / "psa_coverage.csv", index=False)
    return tmp_path
