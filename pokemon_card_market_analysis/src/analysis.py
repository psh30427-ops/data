"""Calendar-aligned analysis of observed sales and independent market estimates."""
import numpy as np
import pandas as pd

from .cleaning import END, START, parse_dates
from .market_index import market_index

FREQUENCIES = {"daily": "D", "weekly": "W-SUN", "monthly": "MS"}
MIN_CORRELATION_PAIRS = 3


def drawdown(prices):
    return prices.div(prices.cummax()).sub(1)


def returns(prices):
    return prices.pct_change(fill_method=None)


def aggregate(sales, dates, coverage, frequency):
    if sales.empty:
        daily = pd.DataFrame(index=dates, columns=["price", "observed_sales"], dtype=float)
    else:
        daily = sales.groupby("date")["price_usd"].agg(price="median", observed_sales="size").reindex(dates)
    daily.loc[coverage & daily["observed_sales"].isna(), "observed_sales"] = 0
    daily["covered_days"] = coverage.astype(int)
    if frequency == "D":
        return daily
    # Medians use individual sales, so days with one sale do not get the same weight
    # as days with many sales. Coverage counts only calendar dates inside the study.
    bins = daily.resample(frequency)
    price = sales.set_index("date")["price_usd"].resample(frequency).median() if len(sales) else pd.Series(dtype=float)
    return pd.DataFrame({
        "price": price.reindex(bins.size().index),
        "observed_sales": bins["observed_sales"].sum(min_count=1),
        "covered_days": bins["covered_days"].sum(),
        "period_days": bins.size(),
    })


def read_coverage(path, card_ids, dates):
    coverage = pd.DataFrame(False, index=dates, columns=card_ids)
    if not path.exists():
        return coverage
    rows = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {"card_id", "start_date", "end_date"}
    if not required.issubset(rows.columns):
        raise ValueError("수집 범위 CSV 필수 열: card_id, start_date, end_date")
    starts, ends = parse_dates(rows["start_date"]), parse_dates(rows["end_date"])
    if (starts.isna() | ends.isna() | starts.gt(ends) | ~rows["card_id"].isin(card_ids)).any():
        raise ValueError("수집 범위 CSV에 잘못된 날짜 범위 또는 카드 ID가 있습니다.")
    for card_id, start, end in zip(rows["card_id"], starts, ends):
        coverage.loc[start:end, card_id] = True
    return coverage


def analyze(data, cards, coverage_path, variants=None, sales_source="PSA"):
    ids = [card["card_id"] for card in cards]
    dates = pd.date_range(START, END)
    coverage = read_coverage(coverage_path, [c["card_id"] for c in variants or cards], dates)
    primary_sales = data.loc[data["source"].eq(sales_source) & data["data_type"].eq("sale")].copy()
    price_column = "psa_price" if sales_source == "PSA" else "compsniper_price"
    estimates = data.loc[data["source"].eq("PriceCharting") & data["data_type"].eq("market_estimate")]
    secondary_sales = data.loc[data["source"].eq("PriceCharting") & data["data_type"].eq("sale")]
    frames = {label: [] for label in FREQUENCIES}
    stats, events, comparisons = [], [], []
    for card_id in ids:
        sales = primary_sales.loc[primary_sales["card_id"].eq(card_id)]
        tables = {label: aggregate(sales, dates, coverage[card_id], freq)
                  for label, freq in FREQUENCIES.items()}
        daily, weekly, monthly = (tables[label] for label in FREQUENCIES)
        for days in (7, 30):
            daily[f"ma{days}"] = daily["price"].rolling(days, min_periods=1).mean().where(daily["price"].notna())
        daily["drawdown"] = drawdown(daily["price"])
        for period in (weekly, monthly):
            period["price_return"] = returns(period["price"])
            period["full_coverage"] = period["covered_days"].eq(period["period_days"])
            volume = period["observed_sales"].where(period["full_coverage"])
            # Relative change is undefined when the preceding count is zero.
            period["volume_change"] = volume.div(volume.shift().where(volume.shift().gt(0))).sub(1)
        weekly["rolling_volatility"] = weekly["price_return"].rolling(8, min_periods=4).std()
        pair = weekly[["price_return", "volume_change"]].dropna()
        correlation = (pair["price_return"].corr(pair["volume_change"])
                       if len(pair) >= MIN_CORRELATION_PAIRS and pair.nunique().min() > 1 else np.nan)
        stats.append(dict(
            card_id=card_id, observed_sales=len(sales),
            pricecharting_sales=int(secondary_sales["card_id"].eq(card_id).sum()),
            first_sale=sales["date"].min(), last_sale=sales["date"].max(),
            observed_days=sales["date"].nunique(),
            covered_days=int(coverage[card_id].sum()),
            observed_weeks=int(weekly["price"].count()), observed_months=int(monthly["price"].count()),
            min_price=sales["price_usd"].min(), max_price=sales["price_usd"].max(),
            weekly_returns=int(weekly["price_return"].count()),
            weekly_volatility=weekly["price_return"].std(), mdd=daily["drawdown"].min(),
            volume_price_r=correlation, volume_price_pairs=len(pair),
        ))
        blows = weekly.assign(next_return=weekly["price"].shift(-1).div(weekly["price"]).sub(1))
        events.append(blows.loc[blows["price_return"].abs().ge(.20), ["price_return", "next_return"]]
                      .assign(card_id=card_id))
        market = estimates.loc[estimates["card_id"].eq(card_id)].set_index("date")["price_usd"]
        if not market.empty:
            match = (
                monthly.loc[monthly["price"].notna(), ["price", "observed_sales"]]
                .join(market.resample("MS").median().rename("market_estimate"))
                .join(market.resample("MS").size().rename("market_points"))
                .dropna(subset=["market_estimate"])
                .rename(columns={"price": price_column})
                .assign(card_id=card_id)
            )
            match["difference_usd"] = match[price_column] - match["market_estimate"]
            match["difference_pct"] = match[price_column].div(match["market_estimate"]).sub(1)
            if not match.empty:
                comparisons.append(match)
        for label, frame in tables.items():
            frames[label].append(frame.assign(card_id=card_id).rename_axis("date").reset_index())

    daily, weekly, monthly = (pd.concat(frames[label], ignore_index=True) for label in FREQUENCIES)
    price_panel = weekly.pivot(index="date", columns="card_id", values="price").reindex(columns=ids)
    pcpi, normalized = market_index(price_panel, ids)
    weekly = weekly.merge(normalized.rename_axis(columns="card_id").stack().rename("normalized_price").reset_index(),
                          on=["date", "card_id"], how="left")
    weekly["cumulative_return"] = weekly["normalized_price"].div(100).sub(1)
    complete = price_panel.dropna()
    summary = pd.DataFrame(stats).set_index("card_id")
    summary["common_start_week"] = complete.index.min()
    summary["common_end_week"] = complete.index.max()
    summary["cumulative_return"] = np.nan
    if len(complete) >= 2:
        summary["cumulative_return"] = complete.iloc[-1].div(complete.iloc[0]).sub(1)
    return_panel = weekly.pivot(index="date", columns="card_id", values="price_return").reindex(columns=ids)
    present = return_panel.notna().astype(int)
    return {
        "language_comparison": compare_languages(primary_sales, variants or cards),
        "card_summary": summary,
        "daily_prices": daily,
        "weekly_prices": weekly,
        "monthly_volume": monthly,
        "correlation_matrix": return_panel.corr(min_periods=MIN_CORRELATION_PAIRS),
        "correlation_sample_sizes": present.T @ present,
        "market_index": pcpi.rename_axis("date"),
        "price_shocks": pd.concat(events).rename_axis("date").reset_index(),
        "source_comparison": (pd.concat(comparisons).rename_axis("date").reset_index() if comparisons else
                              pd.DataFrame(columns=["date", "card_id", price_column, "observed_sales",
                                                    "market_estimate", "market_points", "difference_usd",
                                                    "difference_pct"])),
    }


def compare_languages(primary_sales, variants):
    """Compare verified products on overlapping weeks without pooling their sales."""
    rows = []
    catalog = pd.DataFrame(variants)
    columns = ["artwork_id", "en_card_id", "ja_card_id", "first_common_week", "last_common_week",
               "paired_weeks", "en_observed_sales", "ja_observed_sales", "en_return", "ja_return",
               "en_volatility", "ja_volatility", "ja_premium_pct"]
    for artwork, products in catalog.groupby("artwork_id"):
        pair = products.loc[~products["identity_status"].eq("candidate")].set_index("language")
        if not {"en", "ja"}.issubset(pair.index):
            continue
        sales = {lang: primary_sales.loc[primary_sales["card_id"].eq(pair.loc[lang, "card_id"])] for lang in ("en", "ja")}
        if min(map(len, sales.values())) < 100:
            continue
        weekly = pd.concat({lang: frame.set_index("date")["price_usd"].resample("W-SUN").median()
                            for lang, frame in sales.items()}, axis=1)
        common = weekly.dropna()
        if len(common) < 3:
            continue
        first, last = common.index[[0, -1]]
        window = weekly.loc[first:last].asfreq("W-SUN")
        window.loc[window.isna().any(axis=1)] = np.nan
        growth = common.iloc[-1].div(common.iloc[0]).sub(1)
        volatility = returns(window).std()
        counts = {lang: int(frame["date"].dt.to_period("W-SUN").dt.end_time.dt.normalize()
                            .between(first, last).sum()) for lang, frame in sales.items()}
        rows.append(dict(artwork_id=artwork, en_card_id=pair.loc["en", "card_id"],
                         ja_card_id=pair.loc["ja", "card_id"], first_common_week=first, last_common_week=last,
                         paired_weeks=len(common), en_observed_sales=counts["en"], ja_observed_sales=counts["ja"],
                         en_return=growth["en"], ja_return=growth["ja"], en_volatility=volatility["en"],
                         ja_volatility=volatility["ja"],
                         ja_premium_pct=common["ja"].div(common["en"]).sub(1).median()))
    return pd.DataFrame(rows, columns=columns)
