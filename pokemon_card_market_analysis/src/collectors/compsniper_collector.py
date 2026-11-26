"""Collect completed eBay listings through the documented CompSniper API."""
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from .csv_loader import OPTIONAL, REQUIRED, load_csvs

BASE_URL = "https://api.compsniper.com"
SOURCE = "CompSniper"
VAN_GOGH = "svp-85"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get_json(path, params=None):
    key = os.getenv("COMPSNIPER_API_KEY")
    if not key:
        raise ValueError("COMPSNIPER_API_KEY가 환경 변수에 없습니다.")
    query = "?" + urlencode(params) if params else ""
    request = Request(BASE_URL + path + query, headers={"Authorization": "Bearer " + key})
    try:
        with build_opener(NoRedirect()).open(request, timeout=75) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise ValueError(f"CompSniper {path} HTTP {exc.code}") from None
    except (OSError, URLError, ValueError):
        raise ValueError(f"CompSniper {path} 연결 또는 응답 형식 오류") from None
    if not isinstance(result, dict):
        raise ValueError(f"CompSniper {path} 응답 형식 오류")
    return result


def collect(directory):
    return load_csvs(directory, "compsniper_sales*.csv", SOURCE, "sale")


def row_from_item(item, card, start, end, collected_at):
    title = str(item.get("title") or "")
    number = card["card_number"].split("/")[0]
    id_match = re.search(rf"(?<!\d)0*{int(number)}(?!\d)", title)
    grade_match = re.search(r"\bPSA\s*10\b", title, re.I)
    mismatch = re.search(r"\b(?:lot|bundle|reprint|proxy|custom|replica|autographed|signed)\b", title, re.I)
    grade_labels = re.findall(r"\b(?:PSA|CGC|BGS|SGC)\s*([0-9]+(?:\.[0-9]+)?)", title, re.I)
    if not id_match or not grade_match or mismatch or grade_labels not in (["10"], ["10.0"]):
        return None
    language = card["language"]
    english = re.search(r"\b(?:EN|English|ENG)\b", title, re.I)
    japanese = re.search(r"\b(?:JP|JPN|Japanese)\b|日本語", title, re.I)
    other = re.search(r"\b(?:Chinese|Korean|French|German|Italian|Spanish|Portuguese)\b", title, re.I)
    if other:
        return None
    if language == "en":
        if japanese or not all(word.casefold() in title.casefold() for word in card["card_name"].split()):
            return None
        if card["card_id"] != VAN_GOGH and not english:
            return None
    elif english or not japanese or not card.get("local_name"):
        return None
    elif card["local_name"].casefold() not in title.casefold() and card["card_name"].casefold() not in title.casefold():
        return None

    sale_id = str(item.get("itemId") or "")
    if (not sale_id.isascii() or not sale_id.isdecimal() or item.get("listingType") != "sold"
            or item.get("soldCurrency") != "USD" or item.get("bestOfferAccepted") is True):
        return None
    if not re.search(r"\b(?:best offer accepted|or best offer|best offer)\b", title, re.I):
        try:
            sale_date = date.fromisoformat(str(item.get("endedAt") or "")[:10])
            price = Decimal(str(item.get("soldPrice")))
        except (ValueError, InvalidOperation):
            return None
        if start <= sale_date <= min(end, collected_at) and price.is_finite() and price > 0:
            return dict(
                date=sale_date.isoformat(), card_id=card["card_id"], card_name=card["card_name"],
                card_number=card["card_number"], set_name=card["set_name"], language=language,
                grade=10, original_price=format(price, "f"), currency="USD", marketplace="eBay",
                sale_type=item.get("buyingFormat") or "", sale_id=sale_id,
                source_url=f"https://www.ebay.com/itm/{sale_id}", collected_at=collected_at.isoformat(),
                listing_title=title, language_evidence="title" if (english or japanese) else "english_only_card",
            )
    return None


def fetch_card(directory, card, start, end, max_pages, *, history=False):
    if start > end or not 1 <= max_pages <= 10:
        raise ValueError("조회 시작일/종료일 및 페이지 한도(1~10)를 확인하세요.")
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    short_number = card["card_number"].split("/")[0]
    # Full printed number is especially important for editions sharing a name.
    keyword = f"{card['card_name']} {card['card_number']} PSA 10"
    if card["language"] == "en":
        keyword += " English"
    if card["card_id"] == VAN_GOGH:
        keyword = f"Pikachu Grey Felt Hat {short_number} PSA 10"
    rows = {}
    counts = {"pages": 0, "returned": 0, "eligible": 0, "has_more": False}
    for page in range(1, max_pages + 1):
        if history:
            result = get_json("/v1/research/sold", dict(
                keyword=keyword, ebaySite="ebay.com", startDate=start.isoformat(), endDate=end.isoformat(),
                singleUnitOnly="true", sort="quantityAscending", limit=50, page=page,
            ))
            source_rows = result.get("results")
            items = [history_listing(row) for row in source_rows] if isinstance(source_rows, list) else None
        else:
            result = get_json("/v1/scrape", dict(
                keyword=keyword, ebaySite="ebay.com", sold="true", count=240, page=page,
                soldAfter=start.isoformat(), soldBefore=end.isoformat(),
            ))
            items = result.get("items")
        if not isinstance(items, list):
            raise ValueError("CompSniper 거래 목록 응답 형식이 예상과 다릅니다.")
        counts["pages"] += 1
        counts["returned"] += len(items)
        counts["has_more"] = result.get("hasNextPage") is True
        for item in items:
            if item is None:
                continue
            row = row_from_item(item, card, start, end, today)
            if row:
                rows.setdefault(row["sale_id"], row)
        if not items or not counts["has_more"]:
            break

    counts["eligible"] = len(rows)
    counts["first_sale"] = min((row["date"] for row in rows.values()), default=None)
    counts["last_sale"] = max((row["date"] for row in rows.values()), default=None)
    counts["distinct_dates"] = len({row["date"] for row in rows.values()})
    counts["title_language"] = sum(row["language_evidence"] == "title" for row in rows.values())
    directory.mkdir(exist_ok=True, parents=True)
    prefix = "history_" if history else ""
    out = directory / f"compsniper_sales_{prefix}{card['card_id']}_{start}_{end}.csv"
    # Merge overlapping attempts by stable eBay listing ID while retaining the first stored observation.
    if out.is_file():
        with out.open(encoding="utf-8", newline="") as previous:
            for row in csv.DictReader(previous):
                rows[row["sale_id"]] = row
    fields = sorted(REQUIRED) + OPTIONAL + ["listing_title", "language_evidence"]
    with NamedTemporaryFile(mode="w", dir=directory, encoding="utf-8", newline="", delete=False) as pending:
        writer = csv.DictWriter(pending, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows.values(), key=lambda row: (row["date"], row["sale_id"])))
    Path(pending.name).replace(out)
    return counts


def history_listing(row):
    """Convert a single-unit historical listing, rejecting listing-level averages."""
    if row.get("recordType") != "single_unit_listing" or row.get("soldUnits") != 1:
        return None
    price = row.get("soldPrice") or {}
    return dict(
        title=row.get("title"), itemId=row.get("itemId"), endedAt=row.get("soldDate"),
        soldPrice=price.get("amount"), soldCurrency=price.get("currency"), listingType="sold",
        buyingFormat=row.get("listingFormat"),
    )
