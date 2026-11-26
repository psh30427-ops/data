"""Pokémon card analysis CLI."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

import pandas as pd
import requests

from src.analysis import analyze
from src.source_validation import compare_ebay_sales
from src.market_index import compare_source_indices
from src.card_config import availability, load_cards
from src.cleaning import clean
from src.collectors import compsniper_collector, goldin_collector, pricecharting_collector, psa_collector
from src.cleaning import END, START
from src.report_generator import write_report
from src.visualization import LABELS, plot_all

PROJECT = Path(__file__).resolve().parent
SOURCE_URLS = (
    psa_collector.AUCTION_URL, "https://www.psacard.com/termsandconditions",
    "https://www.psacard.com/robots.txt", pricecharting_collector.API_DOCS_URL,
    "https://www.pricecharting.com/page/terms-of-service",
    "https://www.pricecharting.com/robots.txt",
    "https://www.pricecharting.com/game/pokemon-promo/pikachu-with-grey-felt-hat-85",
    "https://developer.ebay.com/api-docs/buy/marketplace-insights/overview.html",
    "https://developer.ebay.com/api-docs/buy/browse/overview.html",
    "https://snkrdunk.com/", "https://jp.mercari.com/",
    "https://auctions.yahoo.co.jp/closedsearch/closedsearch",
    "https://www.pokemon-card.com/card-search/",
    "https://fred.stlouisfed.org/series/DEXJPUS",

)


def validate_sources():
    passed = True
    for url in SOURCE_URLS:
        try:
            with requests.get(url, timeout=10, stream=True) as response:
                response.raise_for_status()
            print(f"HTTP {response.status_code} {url}")
        except requests.RequestException as exc:
            passed = False
            print(f"접근 확인 실패 {url} ({exc})", file=sys.stderr)
    print("접근 가능 여부와 자동 수집 권한은 별도입니다. DATA_SOURCE_REVIEW.md를 확인하세요.")
    return passed


def collect(raw_dir):
    psa = psa_collector.collect(raw_dir)
    pc_sales, pc_market = pricecharting_collector.collect(raw_dir)
    print(f"입력 행 PSA 실거래 {len(psa)} | PriceCharting 실거래 {len(pc_sales)} | 추정 시세 {len(pc_market)}")
    comp = compsniper_collector.collect(raw_dir)
    if len(comp):
        print(f"입력 행 CompSniper eBay 실거래 {len(comp)}")
    goldin = goldin_collector.collect(raw_dir)
    if len(goldin):
        print(f"입력 행 Goldin 실거래 {len(goldin)}")
    if not len(psa) + len(pc_sales) + len(pc_market) + len(comp) + len(goldin):
        raise ValueError("허용된 원본 CSV가 없거나 비어 있습니다. data/raw의 파일 규칙은 README.md를 확인하세요.")
    return pd.concat([psa, pc_sales, pc_market, comp, goldin], ignore_index=True)


def write_table(table, path, index=False):
    temporary = path.with_suffix(".tmp")
    table.to_csv(temporary, index=index)
    temporary.replace(path)


def run(action, project=PROJECT, sales_source="PSA"):
    if action == "validate_sources":
        return 0 if validate_sources() else 1
    variants, cards = load_cards(project / "config/cards.json")
    raw_dir, processed, results, figures = (project / path for path in
                                             ("data/raw", "data/processed", "results", "figures"))
    selected_ids = [card["card_id"] for card in cards]
    report = project / "REPORT.md"
    for path in (raw_dir, processed, results, figures):
        path.mkdir(parents=True, exist_ok=True)
    indexed = {"card_summary", "correlation_matrix", "correlation_sample_sizes", "market_index"}
    if action == "report":
        if not (results / "analysis_manifest.json").exists():
            raise ValueError("--analyze를 실행하여 보고서에 사용할 분석 결과를 생성하세요.")
        keys = json.loads((results / "analysis_manifest.json").read_text(encoding="utf-8"))
        if keys.get("selected_ids") != selected_ids:
            raise ValueError("분석 결과의 고정 판본이 현재 설정과 다릅니다. --analyze를 다시 실행하세요.")
        tables = {key: pd.read_csv(results / f"{key}.csv", index_col=0 if key in indexed else None)
                  for key in keys["tables"]}
        missing = [key for key in keys["figures"] if not (figures / f"{key}.png").is_file()]
        if missing:
            raise ValueError("그래프 파일 누락. --analyze를 다시 실행하세요.")
        write_report(report, cards, tables, keys["figures"], pd.read_csv(results / "data_quality_report.csv"),
                     keys.get("sales_source", "PSA"))
        print(f"보고서 {report}")
        return 0
    if action == "collect":
        collect(raw_dir)
        return 0
    if action in {"clean", "all"}:
        try:
            raw = collect(raw_dir)
        except ValueError:
            if action == "all" and not report.exists():
                write_report(report, cards)
            raise
        data, quality = clean(raw, variants)
        (results / "analysis_manifest.json").unlink(missing_ok=True)
        write_table(data, processed / "observations.csv")
        write_table(quality, results / "data_quality_report.csv")
        print(f"정제 {len(raw)}행 → {len(data)}행")
        if action == "clean":
            return 0
    if not (processed / "observations.csv").exists():
        raise ValueError("--clean으로 먼저 정제 데이터를 생성하세요.")
    (results / "analysis_manifest.json").unlink(missing_ok=True)
    data = pd.read_csv(processed / "observations.csv", parse_dates=["date", "collected_at"])
    quality = pd.read_csv(results / "data_quality_report.csv")
    if "missing_required_rows" not in quality:
        raise ValueError("기존 정제 파일을 현재 형식으로 갱신하려면 --clean을 다시 실행하세요.")
    coverage_file = "psa_coverage.csv" if sales_source == "PSA" else "compsniper_coverage.csv"
    tables = analyze(data, cards, raw_dir / coverage_file, variants, sales_source)
    tables["variant_availability"] = availability(data, quality, variants)
    if {"PSA", "CompSniper"}.issubset(set(data["source"])):
        tables["pcpi_by_source"], tables["pcpi_basket_coverage"] = compare_source_indices(
            data, selected_ids, START, END
        )
    sales_rows = data.loc[data["data_type"].eq("sale")]
    tables["source_date_coverage"] = (
        sales_rows.assign(year=sales_rows["date"].dt.year)
        .groupby(["source", "year"])["date"]
        .agg(sales="size", first_sale="min", last_sale="max", distinct_days="nunique")
        .reset_index()
    )
    if {"PSA", "CompSniper"}.issubset(set(data["source"])):
        tables["ebay_source_pairs"], tables["ebay_source_summary"] = compare_ebay_sales(data)
    for key, table in tables.items():
        write_table(table, results / f"{key}.csv", key in indexed)
    charts = plot_all(data, tables, cards, figures, sales_source)
    (results / "analysis_manifest.json").write_text(
        json.dumps({"figures": [key for key in LABELS if key in charts], "tables": list(tables),
                    "selected_ids": selected_ids, "sales_source": sales_source}),
        encoding="utf-8",
    )
    print(f"분석 표 {len(tables)}개, PNG {len(charts)}개")
    if action == "all":
        return run("report", project, sales_source)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    for action in ("validate-sources", "collect", "clean", "analyze", "report", "all"):
        group.add_argument(f"--{action}", action="store_const", const=action.replace("-", "_"), dest="action")
    group.add_argument("--fetch-compsniper", action="store_const", const="fetch_compsniper", dest="action")
    group.add_argument("--fetch-compsniper-history", action="store_const", const="fetch_history", dest="action")
    group.add_argument("--fetch-psa", action="store_const", const="fetch_psa", dest="action")
    group.add_argument("--fetch-goldin", action="store_const", const="fetch_goldin", dest="action")
    parser.add_argument("--card", default="svp-85", help="CompSniper 카드 ID")
    parser.add_argument("--from-date", type=date.fromisoformat, default=date.fromisoformat(START))
    parser.add_argument("--to-date", type=date.fromisoformat, default=date.fromisoformat(END))
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--sales-source", choices=["PSA", "CompSniper"], default="PSA")
    args = parser.parse_args()
    try:
        if args.action in {"fetch_compsniper", "fetch_history", "fetch_psa", "fetch_goldin"}:
            variants, _ = load_cards(PROJECT / "config/cards.json")
            card = next((card for card in variants if card["card_id"] == args.card), None)
            if card is None:
                raise ValueError("알 수 없는 카드 ID입니다. config/cards.json을 확인하세요.")
            quota = compsniper_collector.get_json("/v1/account/usage")
            if quota.get("plan") != "basic" or not isinstance(quota.get("remaining"), int):
                raise ValueError("Basic 무료 플랜의 남은 요청 수를 확인할 수 없습니다.")
            if args.action == "fetch_psa":
                if quota["remaining"] < 1:
                    raise ValueError("Basic 무료 잔여 한도가 없습니다.")
                specs = json.loads((PROJECT / "config/psa_specs.json").read_text(encoding="utf-8"))
                if args.card not in specs:
                    raise ValueError("이 판본에 대해 검증한 PSA 카드 번호가 없습니다.")
                returned, accepted, first = psa_collector.fetch_recent(
                    PROJECT / "data/raw", card, specs[args.card], compsniper_collector.get_json)
                print(json.dumps(dict(returned=returned, cached=accepted, first_sale=first), ensure_ascii=False))
                return 0
            if args.max_pages > quota["remaining"]:
                raise ValueError("요청 페이지 수가 무료 잔여 한도를 초과합니다.")
            if args.action == "fetch_goldin":
                if args.card != compsniper_collector.VAN_GOGH or not 1 <= args.max_pages <= 10 or args.from_date > args.to_date:
                    raise ValueError("Goldin 시험 수집은 svp-85, 올바른 날짜와 1~10페이지를 지원합니다.")
                for page in range(1, args.max_pages + 1):
                    payload = compsniper_collector.get_json(
                        "/v1/goldin/sold", dict(keyword="Pikachu Grey Felt Hat 085 PSA 10", page=page))
                    returned, accepted, more = goldin_collector.store_page(
                        PROJECT / "data/raw", card, payload, page, args.from_date, args.to_date)
                    print(json.dumps(dict(page=page, returned=returned, accepted=accepted, has_more=more)))
                    if not more:
                        break
                return 0
            result = compsniper_collector.fetch_card(PROJECT / "data/raw", card, args.from_date,
                                                     args.to_date, args.max_pages, history=args.action == "fetch_history")
            print(json.dumps(result, ensure_ascii=False))
            return 0
        return run(args.action, sales_source=args.sales_source)
    except (OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
