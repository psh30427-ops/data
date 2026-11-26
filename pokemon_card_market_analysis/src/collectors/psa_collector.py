from csv import DictReader, DictWriter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .csv_loader import OPTIONAL, REQUIRED, load_csvs

AUCTION_URL = "https://www.psacard.com/auctionprices"


def collect(directory):
    return load_csvs(directory, "psa_sales*.csv", "PSA", "sale")


def fetch_recent(directory, card, spec, request):
    """Read the PSA card's individual sales via the documented CompSniper integration."""
    response = request("/v1/psa/card", dict(specId=spec["spec_id"], count=50, timeRange=0, grade="10"))
    identity = response.get("card") or {}
    title = " ".join(str(identity.get(k) or "") for k in ("subject", "description", "setName")).casefold()
    def normalize(value):
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    hint = normalize(spec["set_hint"])
    set_name = normalize(identity.get("setName"))
    # The PSA search and sales endpoints sometimes expand or abbreviate set names.
    if (str(identity.get("specId")) != spec["spec_id"]
            or str(identity.get("cardNumber") or "").lstrip("#0") != card["card_number"].split("/")[0].lstrip("0")
            or not all(word.lower() in title for word in card["card_name"].split())
            or str(identity.get("year")) != str(card["release_year"])
            or not set_name
            or (hint not in set_name and set_name not in hint)
            or (card["language"] == "ja") != ("japanese" in title)):
        raise ValueError(f"{card['card_id']}: PSA 카드 식별자를 재확인해야 합니다.")
    items = response.get("items")
    if not isinstance(items, list):
        raise ValueError("PSA 판매 목록 응답 형식 오류")
    if items and (response.get("summary") or {}).get("currency") != "USD":
        raise ValueError("PSA 판매 목록 통화 확인 불가")

    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    rows = {}
    for item in items:
        if (item.get("possibleMismatch") is not False or item.get("gradingCompany") != "PSA"
                or str(item.get("grade")) != "10" or not item.get("certNumber") or not item.get("saleId")):
            continue
        url = item.get("url") or ""
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or not item.get("marketplace"):
            continue
        try:
            sale_date = date.fromisoformat(str(item.get("saleDate"))[:10])
            price = Decimal(str(item.get("salePrice")))
        except (ValueError, InvalidOperation):
            continue
        if sale_date > today or not price.is_finite() or price <= 0:
            continue
        sid = str(item["saleId"])
        rows.setdefault(sid, dict(
            date=sale_date.isoformat(), card_id=card["card_id"], card_name=card["card_name"],
            card_number=card["card_number"], set_name=card["set_name"], language=card["language"], grade=10,
            original_price=format(price, "f"), currency="USD", marketplace=item["marketplace"],
            sale_type=item.get("saleType") or "", sale_id=sid, cert_number=item["certNumber"],
            source_url=url, collected_at=today.isoformat(), psa_spec_id=spec["spec_id"],
        ))
    out = directory / f"psa_sales_comp_{card['card_id']}_{today}.csv"
    directory.mkdir(exist_ok=True, parents=True)
    if out.exists():
        with out.open(encoding="utf-8", newline="") as previous:
            for row in DictReader(previous):
                rows.setdefault(row["sale_id"], row)
    with NamedTemporaryFile(mode="w", dir=directory, encoding="utf-8", newline="", delete=False) as pending:
        writer = DictWriter(pending, fieldnames=sorted(REQUIRED) + OPTIONAL + ["psa_spec_id"])
        writer.writeheader()
        writer.writerows(sorted(rows.values(), key=lambda row: (row["date"], row["sale_id"])))
    Path(pending.name).replace(out)
    return len(items), len(rows), min((row["date"] for row in rows.values()), default=None)
