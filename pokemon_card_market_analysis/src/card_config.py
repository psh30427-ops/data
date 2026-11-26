"""Validate the fixed basket and provide per-variant research metrics."""
import json

import pandas as pd

ORIGINAL_ARTWORKS = {"svp-85", "swsh7-215", "sv3pt5-199", "swsh11-186", "swsh8-271",
                     "swsh7-218", "sv4pt5-232", "sv2-203", "swsh12-186", "sv8-238"}


def load_cards(path):
    variants = json.loads(path.read_text(encoding="utf-8"))
    ids = {card["card_id"] for card in variants}
    if len(ids) != len(variants):
        raise ValueError("카드 ID가 중복됐습니다.")
    products = {(card["card_name"], card["card_number"], card["set_name"], card["release_year"],
                 card["language"], card["artwork_id"], card["card_type"], card["grade"]) for card in variants}
    if len(products) != len(variants):
        raise ValueError("같은 상품의 카드 ID가 여러 개 있습니다.")
    if any(card["language"] not in {"en", "ja"} or card["grade"] != 10 for card in variants):
        raise ValueError("영문·일본판 PSA 10만 설정할 수 있습니다.")
    editions = {(card["artwork_id"], card["language"]) for card in variants}
    if len(editions) != len(variants) or ("svp-85", "ja") in editions:
        raise ValueError("일러스트별 허용 언어판은 하나씩만 등록할 수 있습니다.")
    selected = [card for card in variants if card["selected"]]
    artworks = {card["artwork_id"] for card in variants}
    if artworks != ORIGINAL_ARTWORKS or len(selected) != 10 or {card["artwork_id"] for card in selected} != artworks:
        raise ValueError("PCPI에는 기존 일러스트 10종의 언어 버전을 하나씩 설정해야 합니다.")
    if any(card["identity_status"] == "candidate" for card in selected):
        raise ValueError("카드 단위 근거가 확인되지 않은 후보는 PCPI에 편입할 수 없습니다.")
    return variants, selected


def availability(data, quality, variants):
    rows = []
    for card in variants:
        cid = card["card_id"]
        for source in ("PSA", "PriceCharting", "CompSniper", "Goldin"):
            sales = data.loc[data["card_id"].eq(cid) & data["source"].eq(source) & data["data_type"].eq("sale")]
            audit = quality.loc[quality["card_id"].eq(cid) & quality["source"].eq(source)
                                & quality["data_type"].eq("sale")]
            total = int(audit["rows"].sum())
            missing = int(audit["missing_required_rows"].sum()) if total else 0
            rows.append(dict(
                artwork_id=card["artwork_id"], card_id=cid, language=card["language"], source=source,
                selected=card["selected"], identity_status=card["identity_status"],
                input_rows=total, sales=len(sales), distinct_dates=sales["date"].nunique(),
                first_sale=sales["date"].min(), last_sale=sales["date"].max(),
                missing_input_ratio=missing / total if total else None,
                outlier_ratio=sales["outlier_iqr"].mean() if len(sales) else None,
            ))
    return pd.DataFrame(rows)
