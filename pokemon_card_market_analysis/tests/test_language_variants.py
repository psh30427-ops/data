import json
from pathlib import Path

import pandas as pd
import pytest

from main import collect
from src.analysis import compare_languages
from src.card_config import availability, load_cards
from src.cleaning import clean

CONFIG = Path(__file__).resolve().parents[1] / "config/cards.json"


def test_japanese_jpy_and_usd_import(tmp_path, observation):
    variants, selected = load_cards(CONFIG)
    card = next(c for c in variants if c["card_id"] == "ja-sv2a-201-2023-psa10")
    fx = dict(currency="JPY", original_price="¥20,000", fx_rate_to_usd="0.0065",
              fx_rate_date="2025-01-06", fx_source_url="https://example.org/fx")
    rows = [
        observation(card, **fx),
        observation(card, price_usd="145", language="Japanese"),
        observation(card, **{**fx, "fx_rate_date": "2025-01-03"}),
        observation(card, **{**fx, "fx_source_url": ""}),
    ]
    pd.DataFrame(rows).to_csv(tmp_path / "psa_sales.csv", index=False)
    sales, audit = clean(collect(tmp_path), variants)
    assert len(selected) == 10
    assert next(c for c in selected if c["artwork_id"] == "svp-85")["language"] == "en"
    assert sales["price_usd"].tolist() == pytest.approx([130, 145])
    assert sales["original_price"].tolist() == [20000, 145]
    assert sales["currency"].tolist() == ["JPY", "USD"]
    assert sales["artwork_id"].tolist() == ["sv3pt5-199"] * 2
    assert sales["release_year"].tolist() == [2023, 2023]
    assert sales["fx_rate_to_usd"].tolist() == pytest.approx([.0065, 1])
    assert sales.iloc[0]["fx_source_url"] == "https://example.org/fx"
    assert audit.loc[audit["outcome"].eq("invalid_fx"), "rows"].sum() == 2
    report = availability(sales, audit, variants)
    captured = report.loc[report["card_id"].eq(card["card_id"]) & report["source"].eq("PSA")].iloc[0]
    assert (captured.sales, captured.distinct_dates, captured.missing_input_ratio) == (2, 1, .25)


def test_basket_can_swap_only_one_verified_version(tmp_path):
    original, _ = load_cards(CONFIG)
    cfg = tmp_path / "cards.json"
    jp = next(c for c in original if c["card_id"] == "ja-sv2a-201-2023-psa10")
    next(c for c in original if c["card_id"] == jp["artwork_id"])["selected"] = True
    jp["selected"] = True
    cfg.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError, match="일러스트 10종"):
        load_cards(cfg)
    next(c for c in original if c["card_id"] == jp["artwork_id"])["selected"] = False
    cfg.write_text(json.dumps(original), encoding="utf-8")
    _, picked = load_cards(cfg)
    assert len(picked) == 10 and jp in picked


def test_optional_language_comparison_uses_common_weeks():
    variants, _ = load_cards(CONFIG)
    sparse = []
    for cid, price in (("sv3pt5-199", 100), ("ja-sv2a-201-2023-psa10", 150)):
        for i, date in enumerate(pd.date_range("2025-01-06", periods=4, freq="7D")):
            sparse.extend([dict(card_id=cid, date=date, price_usd=price * (1 + i / 10))] * 25)
    data = pd.DataFrame(sparse)
    assert compare_languages(data.iloc[1:], variants).empty
    result = compare_languages(data, variants).iloc[0]
    assert result.paired_weeks == 4
    assert result.ja_premium_pct == pytest.approx(.5)
    assert result.en_return == result.ja_return == pytest.approx(.3)
