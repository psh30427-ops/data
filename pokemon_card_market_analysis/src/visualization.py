"""Save headless PNG charts of available results with English glyphs."""
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from .cleaning import START, END

LABELS = {
    "trade_prices": "실거래 가격과 이동평균", "normalized_prices": "정규화 주간 가격",
    "cumulative_returns": "공통 구간 누적 수익률", "monthly_volume": "월간 관측 거래",
    "volatility": "주간 수익률 변동성", "volume_return": "거래량과 가격의 변화율",
    "correlation": "카드 간 주간 수익률 상관관계", "source_comparison": "실거래와 PriceCharting 비교",
    "pcpi": "자체 가격 지수", "drawdown": "최대 낙폭",
}


def plot_all(data, tables, cards, directory, sales_source="PSA"):
    directory.mkdir(parents=True, exist_ok=True)
    ids = [c["card_id"] for c in cards]
    names = {c["card_id"]: f"{c['card_name']} {c['card_number']} ({c['language'].upper()})" for c in cards}
    made = []
    primary_label = "PSA Auction Prices Realized" if sales_source == "PSA" else "CompSniper (eBay sold listings)"
    sales = data.loc[data["source"].eq(sales_source) & data["data_type"].eq("sale")]

    def save(fig, key, title, source=primary_label):
        fig.suptitle(f"{title} | {START} to {END}", fontsize=12)
        fig.supxlabel(f"Source: {source} | English or Japanese PSA 10, USD where applicable", fontsize=9)
        fig.savefig(directory / f"{key}.png", dpi=220)
        plt.close(fig)
        made.append(key)

    def panels(frame, field, key, title, xlabel, ylabel, draw, source=primary_label):
        available = [cid for cid in ids if frame.loc[frame["card_id"].eq(cid), field].notna().any()]
        if len(available) == 0:
            return
        nr = math.ceil(len(available) / 2)
        fig, axes = plt.subplots(nr, 2, figsize=(12, 3.15 * nr), squeeze=False, layout="constrained")
        for ax, cid in zip(axes.flat, available):
            part = frame.loc[frame["card_id"].eq(cid)]
            draw(ax, part, cid)
            ax.set(title=names[cid], xlabel=xlabel, ylabel=ylabel)
            ax.tick_params(axis="x", labelrotation=25)
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(fontsize=7)
        for ax in list(axes.flat)[len(available):]:
            ax.set_visible(False)
        save(fig, key, title, source)

    def trades(ax, part, cid):
        rows = sales.loc[sales["card_id"].eq(cid)]
        ax.scatter(rows["date"], rows["price_usd"], s=9, alpha=.45, label="Sale")
        for days in (7, 30):
            points = part.dropna(subset=[f"ma{days}"])
            ax.plot(points["date"], points[f"ma{days}"], label=f"{days}-day mean")

    daily, weekly, monthly = (tables[key] for key in ("daily_prices", "weekly_prices", "monthly_volume"))
    panels(daily, "price", "trade_prices", "Sales and moving averages", "Sale date", "Price (USD)", trades)
    panels(weekly, "normalized_price", "normalized_prices", "Normalized weekly median prices",
           "Week ending", "Index (common base = 100)",
           lambda ax, p, _: ax.plot(p["date"], p["normalized_price"], marker=".", label="Weekly median"))
    panels(monthly, "observed_sales", "monthly_volume", "Monthly observed sales", "Month", "Observed sales (count)",
           lambda ax, p, _: ax.bar(p["date"], p["observed_sales"], width=20, label="Observed sales"))

    def bars(field, key, title):
        series = tables["card_summary"][field].dropna().sort_values().mul(100)
        if series.empty:
            return
        fig, ax = plt.subplots(figsize=(10, max(3, len(series) * .43)), layout="constrained")
        ax.barh([names[cid] for cid in series.index], series, label="Card metric")
        ax.set(xlabel="Percent (%)", ylabel="Card")
        ax.legend()
        save(fig, key, title)

    bars("cumulative_return", "cumulative_returns", "Cumulative return between common weeks")
    bars("weekly_volatility", "volatility", "Weekly return standard deviation")
    bars("mdd", "drawdown", "Maximum drawdown")
    pair = weekly.dropna(subset=["volume_change", "price_return"])
    panels(pair, "volume_change", "volume_return", "Observed volume and price changes",
           "Weekly sales change (%)", "Weekly price return (%)",
           lambda ax, p, _: ax.scatter(p["volume_change"] * 100, p["price_return"] * 100, label="Covered week pair"))

    corr = tables["correlation_matrix"].copy()
    # Self-correlation alone provides no card-to-card comparison.
    for cid in corr.index:
        corr.loc[cid, cid] = float("nan")
    available = corr.index[corr.notna().any()]
    if len(available):
        fig, ax = plt.subplots(figsize=(9, 7), layout="constrained")
        sns.heatmap(corr.loc[available, available], vmin=-1, vmax=1, center=0, annot=True,
                    fmt=".2f", cmap="vlag", ax=ax, cbar_kws={"label": "Pearson r (at least 3 paired weeks)"})
        ax.set(xlabel="Card ID", ylabel="Card ID")
        save(fig, "correlation", "Pairwise weekly return correlation")

    price_column = "psa_price" if sales_source == "PSA" else "compsniper_price"

    def compare(ax, p, _):
        ax.plot(p["date"], p[price_column], marker=".", label=f"{sales_source} sales median")
        ax.plot(p["date"], p["market_estimate"], marker=".", label="PriceCharting estimates median")

    panels(tables["source_comparison"], price_column, "source_comparison", f"{sales_source} sales vs. PriceCharting estimates",
           "Month", "Price (USD)", compare, f"{primary_label}, PriceCharting")
    index = tables["market_index"]["pcpi"]
    if index.notna().any():
        fig, ax = plt.subplots(figsize=(10, 4), layout="constrained")
        ax.plot(index.index, index, marker=".", label=f"PCPI ({len(ids)} cards)")
        ax.set(xlabel="Week ending", ylabel="Index (base = 100)")
        ax.legend()
        save(fig, "pcpi", "Pokémon Card Price Index")
    for key in LABELS.keys() - set(made):
        (directory / f"{key}.png").unlink(missing_ok=True)
    return made
