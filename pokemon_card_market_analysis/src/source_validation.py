"""Compare the same eBay listing across the PSA and CompSniper observations."""
import pandas as pd


def compare_ebay_sales(data):
    sales = data.loc[data["data_type"].eq("sale") & data["marketplace"].str.casefold().eq("ebay")].copy()
    sales["ebay_id"] = sales["source_url"].str.extract(
        r"^https://(?:[a-z]+\.)?ebay\.com/itm/(?:[^/]+/)?([0-9]+)(?:[/?#]|$)"
    )
    keys = ["card_id", "ebay_id"]
    fields = ["date", "price_usd"]
    by_source = {}
    for source in ("PSA", "CompSniper"):
        rows = sales.loc[sales["source"].eq(source), keys + fields].dropna(subset=["ebay_id"])
        # Multiple rows under one listing can be ambiguous. Compare only one-to-one matches.
        by_source[source] = rows.loc[~rows.duplicated(keys, keep=False)]
    pairs = by_source["PSA"].merge(by_source["CompSniper"], on=keys, suffixes=("_psa", "_compsniper"))
    pairs["same_date"] = pairs["date_psa"].eq(pairs["date_compsniper"])
    pairs["same_price"] = pairs["price_usd_psa"].eq(pairs["price_usd_compsniper"])
    pairs["same_date_and_price"] = pairs["same_date"] & pairs["same_price"]
    return (
        pairs,
        pairs.groupby("card_id").agg(
            matched_listings=("ebay_id", "size"), same_date=("same_date", "sum"),
            same_price=("same_price", "sum"), same_date_and_price=("same_date_and_price", "sum"),
        ).reset_index(),
    )
