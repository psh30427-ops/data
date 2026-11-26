"""Validate Goldin completed auction rows for the Grey Felt Hat Pikachu."""
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from tempfile import NamedTemporaryFile
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .csv_loader import OPTIONAL, REQUIRED, load_csvs

SOURCE = "Goldin"


def collect(directory):
    return load_csvs(directory, "goldin_sales*.csv", SOURCE, "sale")


def store_page(directory, card, response, page, start, end):
    items = response.get("items")
    if not isinstance(items, list):
        raise ValueError("Goldin 거래 목록 응답 형식 오류.")
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    rows = {}
    for item in items:
        title = (item.get("title") or "").casefold()
        url = item.get("url") or ""
        parsed = urlsplit(url)
        if (not re.search(r"(?<!\d)0?85(?!\d)", title)
                or not all(word in title for word in ("pikachu", "grey felt hat"))
                or not re.search(r"\b(?:promos?|svp)\b", title)
                or re.search(r"\b(?:lot of|bundle|signed|autographed|auto|inscribed|reprint|custom|japanese)\b", title)
                or item.get("gradingService") != "PSA" or str(item.get("grade")) != "10"
                or item.get("currency") != "USD" or not item.get("saleId")
                or parsed.scheme != "https" or parsed.hostname not in {"goldin.co", "www.goldin.co"}
                or not parsed.path.startswith("/item/")):
            continue
        try:
            sold = date.fromisoformat(str(item.get("soldAt"))[:10])
            price = Decimal(str(item.get("price")))
        except (ValueError, InvalidOperation):
            continue
        if not (start <= sold <= min(end, today)) or not price.is_finite() or price <= 0:
            continue
        sid = str(item["saleId"])
        rows[sid] = dict(
            date=sold.isoformat(), card_id=card["card_id"], card_name=card["card_name"],
            card_number=card["card_number"], set_name=card["set_name"], language=card["language"], grade=10,
            original_price=format(price, "f"), currency="USD", marketplace=SOURCE, sale_id=sid,
            sale_type=item.get("saleType") or "", cert_number=item.get("certNumber") or "",
            source_url=url, collected_at=today.isoformat(), listing_title=item.get("title"),
            hammer_price=item.get("hammerPrice"), buyers_premium_pct=item.get("buyersPremiumPercent"),
        )
    directory.mkdir(exist_ok=True, parents=True)
    out = directory / f"goldin_sales_svp-85_p{page}_{start}_{end}_{today}.csv"
    with NamedTemporaryFile(mode="w", dir=directory, encoding="utf-8", newline="", delete=False) as pending:
        writer = csv.DictWriter(pending, fieldnames=sorted(REQUIRED) + OPTIONAL + [
            "listing_title", "hammer_price", "buyers_premium_pct",
        ])
        writer.writeheader()
        writer.writerows(sorted(rows.values(), key=lambda row: (row["date"], row["sale_id"])))
    Path(pending.name).replace(out)
    return len(items), len(rows), response.get("hasNextPage") is True
