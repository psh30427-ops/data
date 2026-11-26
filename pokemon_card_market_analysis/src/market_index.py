"""Equal-weight fixed-basket index with complete-case publication."""
import pandas as pd


def market_index(prices, card_ids):
    basket = prices.reindex(columns=card_ids)
    observed = basket.notna().sum(axis=1)
    complete = observed.eq(len(card_ids))
    base = basket.index[complete][0] if complete.any() else pd.NaT
    normalized = basket.div(basket.loc[base]).mul(100) if complete.any() else basket * float("nan")
    normalized.loc[normalized.index < base] = float("nan")
    index = normalized.sum(axis=1, min_count=len(card_ids)).div(len(card_ids))
    return pd.DataFrame({"pcpi": index, "observed_cards": observed,
                         "included_cards": observed.where(index.notna(), 0),
                         "base_week": base}), normalized


def compare_source_indices(data, card_ids, start, end):
    """Compute independent indices over the same calendar and fixed basket."""
    weeks = pd.date_range(pd.Timestamp(start).to_period("W-SUN").end_time.normalize(),
                          pd.Timestamp(end).to_period("W-SUN").end_time.normalize(), freq="W-SUN")
    sales = data.loc[data["card_id"].isin(card_ids) & data["data_type"].eq("sale")
                     & data["date"].between(start, end)].copy()
    sales["week_end"] = sales["date"].dt.to_period("W-SUN").dt.end_time.dt.normalize()
    series, coverage = [], []
    for source in ("PSA", "CompSniper"):
        sample = sales.loc[sales["source"].eq(source)]
        basket = (sample.groupby(["week_end", "card_id"])["price_usd"].median().unstack()
                  .reindex(index=weeks, columns=card_ids))
        index, _ = market_index(basket, card_ids)
        index["missing_card_ids"] = [
            ", ".join(row.index[row.isna()]) for _, row in basket.iterrows()
        ]
        series.append(index.assign(source=source).rename_axis("date").reset_index())
        counts = sample.groupby("card_id").agg(
            sales=("date", "size"), distinct_days=("date", "nunique"),
            first_sale=("date", "min"), last_sale=("date", "max"),
        ).reindex(card_ids)
        counts[["sales", "distinct_days"]] = counts[["sales", "distinct_days"]].fillna(0).astype(int)
        counts["observed_weeks"] = basket.count()
        counts["sales_shortfall_to_100"] = (100 - counts["sales"]).clip(lower=0)
        coverage.append(counts.assign(source=source).reset_index())
    return pd.concat(series, ignore_index=True), pd.concat(coverage, ignore_index=True)
