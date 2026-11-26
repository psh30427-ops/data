import re

import pandas as pd
from PIL import Image
import pytest

from main import collect, run
from src.analysis import analyze, drawdown, returns
from src.cleaning import clean


def test_missing_period_is_not_forward_filled():
    series = pd.Series([100., 120., float("nan"), 90., 72.])
    changes = returns(series)
    assert changes.iloc[1] == pytest.approx(.20)
    assert pd.isna(changes.iloc[3])
    assert drawdown(series).min() == pytest.approx(-.40)


def test_period_coverage_and_aligned_analysis(full_import, cards):
    raw = full_import / "data/raw"
    valid, _ = clean(collect(raw), cards)
    out = analyze(valid, cards, raw / "psa_coverage.csv")
    first = cards[0]["card_id"]
    daily = out["daily_prices"].loc[lambda f: f["card_id"].eq(first)].set_index("date")
    assert pd.isna(daily.loc["2025-01-01", "observed_sales"])
    assert daily.loc["2025-01-07", "observed_sales"] == 0
    assert pd.isna(daily.loc["2025-01-07", "price"])
    assert daily.loc["2025-01-20", "ma7"] == 80
    assert daily.loc["2025-01-20", "ma30"] == pytest.approx((100 + 130 + 80) / 3)
    weekly = out["weekly_prices"].loc[lambda f: f["card_id"].eq(first)].set_index("date")
    expected_returns = pd.Series([100., 130., 80., 140., 120.]).pct_change().dropna()
    assert weekly.loc["2025-01-19", "price_return"] == pytest.approx(.3)
    assert out["card_summary"].loc[first, "weekly_volatility"] == pytest.approx(expected_returns.std())
    assert out["card_summary"].loc[first, "mdd"] == pytest.approx(80 / 130 - 1)
    assert out["card_summary"].loc[first, "volume_price_pairs"] == 4
    assert out["card_summary"].loc[first, "pricecharting_sales"] == 1
    assert out["correlation_matrix"].iloc[0, 1] == pytest.approx(1)
    assert out["correlation_sample_sizes"].iloc[0, 1] == 4
    assert out["source_comparison"].iloc[0]["difference_usd"] == 5


def test_cli_reproduces_results_and_reports_real_links(full_import):
    assert run("all", full_import) == 0
    report = full_import / "REPORT.md"
    before = report.read_bytes()
    text = before.decode()
    assert "PSA 실거래 160건" in text
    assert "20.00%" in text
    links = re.findall(r"!\[[^\]]+\]\(([^)]+)\)", text)
    assert len(links) == 10
    for link in links:
        with Image.open(full_import / link) as chart:
            assert chart.format == "PNG"
            assert chart.info["dpi"][0] >= 200
    result = full_import / "results/card_summary.csv"
    summary = result.read_bytes()
    assert run("analyze", full_import) == 0
    assert run("report", full_import) == 0
    assert report.read_bytes() == before
    assert result.read_bytes() == summary
