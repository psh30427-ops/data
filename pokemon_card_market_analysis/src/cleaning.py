"""Validate identity, provenance, and USD prices; flag unusual transactions."""
import re

import numpy as np
import pandas as pd

START = "2025-01-01"
END = "2026-11-25"


def parse_dates(values):
    # Disallow ambiguous day/month ordering and numeric epoch-like dates.
    iso = values.str.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}")
    return pd.to_datetime(values.where(iso).str.replace("/", "-"), format="%Y-%m-%d", errors="coerce")


def clean(raw, cards):
    data = raw.copy()
    for column in data:
        data[column] = data[column].astype("string").fillna("").str.strip()
    data["date"] = parse_dates(data["date"])
    data["collected_at"] = parse_dates(data["collected_at"])
    for field in ("original_price", "price_usd", "fx_rate_to_usd", "fx_rate_date", "fx_source_url"):
        if field not in data:
            data[field] = pd.Series("", index=data.index, dtype="string")
    data["currency"] = data["currency"].str.upper()
    usd = data["currency"].eq("USD")
    jpy = data["currency"].eq("JPY")
    prices = data["original_price"].mask(usd & data["original_price"].eq(""), data["price_usd"])
    prefix = prices.where(jpy).str.replace(r"^(?:JPY\s*|[¥￥]\s*)", "", regex=True, flags=re.I)
    dollar = prices.str.replace(r"^(?:USD\s*|\$\s*)", "", regex=True, flags=re.I)
    prices = prefix.where(jpy, dollar)
    valid_number = prices.str.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?")
    amounts = pd.to_numeric(prices.where(valid_number).str.replace(",", ""), errors="coerce")
    rate_text = data["fx_rate_to_usd"]
    rate = pd.to_numeric(rate_text.where(rate_text.str.fullmatch(r"\d+(?:\.\d+)?")), errors="coerce")
    data["fx_rate_date"] = parse_dates(data["fx_rate_date"])
    url_pattern = r"https?://[^\s/]+(?:/\S*)?"
    fx_valid = (rate.gt(0) & np.isfinite(rate) & data["fx_rate_date"].eq(data["date"])
                & data["fx_source_url"].str.fullmatch(url_pattern)).fillna(False)
    data["original_price"] = amounts
    data["fx_rate_to_usd"] = rate.where(jpy).mask(usd, 1)
    data["fx_rate_date"] = data["fx_rate_date"].where(jpy)
    data["fx_source_url"] = data["fx_source_url"].where(jpy, "")
    data["price_usd"] = amounts * data["fx_rate_to_usd"]
    data["grade"] = pd.to_numeric(data["grade"].str.replace(r"^PSA\s+", "", regex=True, flags=re.I),
                                  errors="coerce")
    data["language"] = data["language"].str.casefold().replace({"english": "en", "eng": "en", "japanese": "ja", "jpn": "ja", "jp": "ja", "日本語": "ja"})
    lookup = pd.DataFrame(cards).set_index("card_id")
    identity = data["card_id"].isin(lookup.index)
    for field in ("card_name", "card_number", "set_name", "language"):
        expected = data["card_id"].map(lookup[field]).astype("string").str.casefold()
        identity &= data[field].str.casefold().eq(expected).fillna(False)
    for field in ("artwork_id", "release_year", "card_type"):
        data[field] = data["card_id"].map(lookup[field])
    identity &= data["grade"].eq(data["card_id"].map(lookup["grade"])).fillna(False)

    missing_fields = ["card_id", "card_name", "card_number", "set_name", "language", "currency", "source_url"]
    missing_required = (data[missing_fields].eq("").any(axis=1) | prices.fillna("").eq("")
                        | raw["grade"].fillna("").astype(str).str.strip().eq("")
                        | raw["date"].fillna("").astype(str).str.strip().eq("")
                        | raw["collected_at"].fillna("").astype(str).str.strip().eq(""))
    missing_fx = jpy & (rate_text.eq("") | data["fx_source_url"].eq("")
                        | raw.get("fx_rate_date", pd.Series("", index=data.index)).fillna("").eq(""))
    reason = pd.Series("", index=data.index, dtype="string")
    checks = {
        "invalid_date": data["date"].isna(),
        "outside_target": ~data["date"].between(START, END),
        "invalid_provenance": (~data["source_url"].str.fullmatch(url_pattern)
                               | data["collected_at"].isna()
                               | data["collected_at"].lt(data["date"])),
        "card_identity_mismatch": ~identity,
        "unsupported_currency": ~(usd | jpy),
        "invalid_fx": jpy & ~fx_valid,
        "invalid_price": ~(data["price_usd"].gt(0) & np.isfinite(data["price_usd"])).fillna(False),
    }
    for label, mask in checks.items():
        reason.loc[reason.eq("") & mask] = label
    valid = data.loc[reason.eq("")].copy()
    # Use transaction IDs scoped to source and marketplace. A certificate may sell repeatedly.
    has_id = valid["sale_id"].ne("") & valid["data_type"].eq("sale")
    keys = ["source", "marketplace", "sale_id"]
    identified = valid.loc[has_id].assign(marketplace=lambda x: x["marketplace"].str.casefold())
    conflicts = identified.groupby(keys)[["date", "card_id", "price_usd"]].transform("nunique").gt(1).any(axis=1)
    reason.loc[conflicts[conflicts].index] = "conflicting_sale_id"
    identified = identified.loc[~conflicts]
    reason.loc[identified.index[identified.duplicated(keys)]] = "duplicate_sale_id"
    # Keep the latest observation for each market estimate date. Reject conflicting values from
    # the same collection date so the outcome is independent of file ordering.
    estimates = valid.loc[valid["data_type"].eq("market_estimate")]
    est_keys = ["source", "card_id", "date"]
    latest = estimates.groupby(est_keys)["collected_at"].transform("max").eq(estimates["collected_at"])
    reason.loc[estimates.index[~latest]] = "superseded_estimate"
    estimates = estimates.loc[latest]
    est_conflict = estimates.groupby(est_keys)["price_usd"].transform("nunique").gt(1)
    reason.loc[estimates.index[est_conflict]] = "conflicting_estimate"
    estimates = estimates.loc[~est_conflict]
    reason.loc[estimates.index[estimates.duplicated(est_keys)]] = "duplicate_estimate"

    kept = data.loc[reason.eq("")].sort_values(["date", "card_id", "source", "sale_id"]).copy()
    kept["outlier_iqr"] = False
    sales = kept["data_type"].eq("sale")
    groups = kept.loc[sales].groupby(["source", "card_id"])["price_usd"]
    q1 = groups.transform("quantile", q=0.25)
    q3 = groups.transform("quantile", q=0.75)
    iqr = q3 - q1
    prices = kept.loc[sales, "price_usd"]
    kept.loc[sales, "outlier_iqr"] = (
        groups.transform("size").ge(4) & iqr.gt(0)
        & (prices.lt(q1 - 1.5 * iqr) | prices.gt(q3 + 1.5 * iqr))
    ).fillna(False)
    audit = data[["source", "data_type", "card_id"]].copy()
    audit["outcome"] = reason.where(reason.ne(""), "accepted")
    audit.loc[kept.index[kept["outlier_iqr"]], "outcome"] = "accepted_outlier"
    groups = list(audit.columns)
    audit["missing_required"] = missing_required | missing_fx
    quality = audit.groupby(groups, dropna=False).agg(rows=("outcome", "size"),
                                                     missing_required_rows=("missing_required", "sum")).reset_index()
    return kept, quality
