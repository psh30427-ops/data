from .csv_loader import load_csvs

API_DOCS_URL = "https://www.pricecharting.com/api-documentation"


def collect(directory):
    return (
        load_csvs(directory, "pricecharting_sales*.csv", "PriceCharting", "sale"),
        load_csvs(directory, "pricecharting_market*.csv", "PriceCharting", "market_estimate"),
    )
