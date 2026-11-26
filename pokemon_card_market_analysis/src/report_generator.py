"""Write Korean results directly from the persisted analysis tables."""
import pandas as pd

from .cleaning import START, END
from .visualization import LABELS

QUESTIONS = [
    "공통 기간 가격이 가장 많이 오른 카드는 무엇인가?",
    "관측 거래량이 가장 많은 카드는 무엇인가?",
    "주간 가격 변동성이 가장 낮거나 높은 카드는 무엇인가?",
    "관측 거래량 변화와 가격 변화 사이에 상관관계가 있는가?",
    "어떤 카드가 유사한 주간 가격 흐름을 보이는가?",
    "주간 가격이 20% 이상 급등하거나 급락한 다음 주에는 어떤 변화가 나타나는가?",
    "PSA 실거래와 PriceCharting 추정 시장 시세의 차이는 얼마인가?",
]


def number(value, percent=False):
    if pd.isna(value):
        return "산출 불가"
    return f"{value:.2%}" if percent else f"{value:,.2f}"


def day(value):
    return str(value)[:10] if pd.notna(value) else "—"


def write_report(path, cards, tables=None, figures=(), quality=None, sales_source="PSA"):
    names = {c["card_id"]: c["card_name"] for c in cards}
    summary = tables["card_summary"] if tables is not None else pd.DataFrame()
    total = int(summary["observed_sales"].sum()) if not summary.empty else 0
    answers = [f"검증을 통과한 {sales_source} 거래 입력이 없어 산출할 수 없다."] * 7
    observations = []

    def insight(question, observation, evidence, interpretation, hypothesis, limit):
        answers[question] = observation
        observations.append(
            f"### 질문 {question + 1}\n\n"
            f"- 관찰 · {observation}\n- 근거 · {evidence}\n- 해석 · {interpretation}\n"
            f"- 가설 · {hypothesis}\n- 한계 · {limit}"
        )

    if total:
        answers = [
            "전 종목 가격이 있는 공통 주가 두 개 이상 필요하다.",
            "기간 내 검증된 거래 건수를 집계했다.",
            "연속 주간 수익률이 두 개 이상 필요하다.",
            "수집 범위가 완전한 연속 주와 유효한 쌍 3개 이상이 필요하다.",
            "카드 쌍마다 유효한 공통 수익률이 3개 이상 필요하다.",
            "20% 이상 변동 직후의 연속 관측 주가 필요하다.",
            f"동일 카드·월에 {sales_source} 거래와 PriceCharting 추정가가 모두 필요하다.",
        ]
        gains = summary["cumulative_return"].dropna()
        if len(gains):
            winners = ", ".join(names[cid] for cid in gains.index[gains.eq(gains.max())])
            first, last = summary.iloc[0][["common_start_week", "common_end_week"]]
            insight(0, f"{day(first)}~{day(last)} 공통 주에서 최고 수익률은 "
                    f"{winners}의 {number(gains.max(), True)}였다.", "누적 수익률 그래프와 card_summary.csv.",
                    "동일한 두 주의 거래 중앙값을 비교한 상대 성과다.",
                    "중간 구간을 바꾸어도 순위가 유지되는지 확인할 수 있다.",
                    "기준·종료 주의 판매 구성과 관측 건수에 민감하다.")
        volumes = summary["observed_sales"]
        leaders = ", ".join(names[cid] for cid in volumes.index[volumes.eq(volumes.max())])
        insight(1, f"가장 많이 관측된 카드는 {leaders}이며 각각 {volumes.max():,}건이었다.",
                "월간 관측 거래 그래프와 card_summary.csv.",
                f"제공된 {sales_source} 자료에서 해당 카드의 판매 기록이 가장 많이 나타났다.",
                "카드별 수집 범위를 맞춘 뒤에도 차이가 유지되는지 확인할 수 있다.",
                "거래 건수에는 출처와 수집 범위 차이가 반영된다.")
        vol = summary["weekly_volatility"].dropna()
        if len(vol):
            low, high = (", ".join(names[cid] for cid in vol.index[vol.eq(v)]) for v in (vol.min(), vol.max()))
            insight(2, f"주간 수익률 표준편차 최저는 {low} {number(vol.min(), True)}, 최고는 "
                    f"{high} {number(vol.max(), True)}였다.",
                    "변동성 그래프와 card_summary.csv.", "값이 큰 카드의 관측 주간 수익률이 더 넓게 흩어졌다.",
                    "표본 주를 일치시키거나 등급 검증이 더 강한 거래만 남겨 비교할 수 있다.",
                    "카드별 유효 주 수와 관측일이 다를 수 있다.")
        relation = summary["volume_price_r"].dropna()
        if len(relation):
            cid = relation.abs().idxmax()
            insight(3, f"절댓값이 가장 큰 거래량·가격 변화 상관은 {names[cid]}의 "
                    f"r={relation[cid]:.3f}, {int(summary.loc[cid, 'volume_price_pairs'])}쌍이었다.",
                    "거래량·가격 산점도와 card_summary.csv.",
                    "같은 주에 측정한 두 변화율의 선형 동행 정도다.",
                    "공통 기간에서 순위 상관을 함께 계산해 민감도를 점검할 수 있다.",
                    "표본이 적거나 특정 급변 주가 있으면 계수가 크게 변할 수 있다.")
        corr, n = tables["correlation_matrix"], tables["correlation_sample_sizes"]
        pairs = [(a, b, corr.loc[a, b]) for i, a in enumerate(corr.index)
                 for b in corr.index[i + 1:] if pd.notna(corr.loc[a, b])]
        if pairs:
            a, b, value = max(pairs, key=lambda pair: pair[2])
            insight(4, f"가장 높은 카드 쌍 상관은 {names[a]}·{names[b]}의 "
                    f"r={value:.3f}, {int(n.loc[a, b])}쌍이었다.",
                    "상관 히트맵과 두 상관 결과 표.", "두 카드의 유효 공통 주에서 계산한 동행 정도다.",
                    "확장팩이 같은 카드의 상관이 추가 기간에도 유지되는지 확인할 수 있다.",
                    "카드 쌍마다 분석 주가 다르고 상관계수로 인과를 판단할 수 없다.")
        shocks = tables["price_shocks"]
        directions = []
        for label, rows in (("급등", shocks.loc[shocks["price_return"].gt(0)]),
                            ("급락", shocks.loc[shocks["price_return"].lt(0)])):
            follow = rows["next_return"].dropna()
            directions.append(f"{label} {len(rows)}건, 다음 주 유효 {len(follow)}건, 중앙값 {number(follow.median(), True)}")
        if len(shocks):
            observation = " · ".join(directions) + ". 후속 표본이 있는 사건만 중앙값에 포함했다."
            if shocks["next_return"].notna().any():
                insight(5, observation, "price_shocks.csv의 사건별 다음 주 수익률.",
                        "급변 직후에 관측된 변화의 중심과 방향을 비교할 수 있다.",
                        "상승·하락 사건별로 평상시 다음 주 수익률과 비교해 차이가 유지되는지 확인할 수 있다.",
                        "이벤트가 같은 시장 충격을 공유할 수 있고, 다음 주 결측의 영향도 남는다.")
            else:
                answers[5] = observation
        comparison = tables["source_comparison"]
        if len(comparison):
            insight(6, f"{len(comparison)}개 동일 카드·월의 가격 차이({sales_source}−PriceCharting) 중앙값은 "
                    f"USD {number(comparison['difference_usd'].median())}, "
                    f"{number(comparison['difference_pct'].median(), True)}였다.",
                    "출처 비교 그래프와 source_comparison.csv.",
                    "거래 중앙값과 별도로 추정한 시장 시세의 관측 차이다.",
                    "같은 날짜에 관측된 값으로 범위를 좁혀도 차이가 유지되는지 볼 수 있다.",
                    "추정 방식과 양쪽에 공통으로 반영된 거래의 범위는 이 자료로 확정할 수 없다.")

    card_lines = "\n".join(f"|{c['card_id']}|{c['card_name']}|{c['card_number']}|{c['set_name']}|{c['language']}|" for c in cards)
    result_lines = []
    for card in cards:
        cid = card["card_id"]
        if summary.empty:
            result_lines.append(f"|{cid}|0|—|—|0 / 0 / 0|—|—|—|0 / 0|")
            continue
        r = summary.loc[cid]
        result_lines.append(
            f"|{cid}|{r.observed_sales}|{day(r.first_sale)}|{day(r.last_sale)}|"
            f"{r.observed_days} / {r.observed_weeks} / {r.observed_months}|"
            f"{number(r.cumulative_return, True)}|{number(r.weekly_volatility, True)}|"
            f"{number(r.mdd, True)}|{r.weekly_returns} / {r.volume_price_pairs}|"
        )
    gallery = "\n\n".join(f"![{LABELS[key]}](figures/{key}.png)" for key in figures)
    index = tables["market_index"]["pcpi"].dropna() if tables is not None else pd.Series(dtype=float)
    index_text = (f"{day(index.index[0])}에 100에서 시작했고, {day(index.index[-1])}의 지수는 "
                  f"{number(index.iloc[-1])}이다. 지수를 계산한 주는 {len(index)}개다."
                  if len(index) else "전 종목의 관측 가격이 있는 공통 기준 주가 없어 지수를 산출하지 못했다.")
    if len(index) and day(index.index[-1]) > END:
        index_text += f" 마지막 주의 날짜는 일요일 종료 라벨이며, {END}까지만 포함한 부분 주다."
    indices = tables.get("pcpi_by_source") if tables is not None else None
    basket_coverage = tables.get("pcpi_basket_coverage") if tables is not None else None
    source_index_section = ""
    if indices is not None and basket_coverage is not None:
        psa_index = indices.loc[indices["source"].eq("PSA") & indices["pcpi"].notna()]
        ebay_all = indices.loc[indices["source"].eq("CompSniper")]
        ebay_index = ebay_all.loc[ebay_all["pcpi"].notna()]
        ebay_coverage = basket_coverage.loc[basket_coverage["source"].eq("CompSniper")]
        common = set(psa_index["date"]) & set(ebay_index["date"])
        max_observed = int(ebay_all["observed_cards"].max())
        ebay_points = ", ".join(f"{day(r.date)} {number(r.pcpi)}" for r in ebay_index.itertuples())
        if not ebay_points:
            ebay_points = f"결측. 한 주에 최대 {max_observed}/10종만 관측했다."
        coverage_lines = "\n".join(
            f"|{names[r.card_id]}|{r.sales}|{r.observed_weeks}|{r.sales_shortfall_to_100}|"
            for r in ebay_coverage.itertuples()
        )
        source_index_section = f"""
### 같은 10종의 eBay 지수 재계산

CompSniper/eBay의 고정 바스켓 거래는 {int(ebay_coverage['sales'].sum()):,}건이다. PSA 지수 {len(psa_index)}주, eBay 지수 {len(ebay_index)}주가 산출됐고 양쪽 지수가 있는 날짜는 {len(common)}개다. eBay 지수 · {ebay_points}

각 출처의 첫 완전 관측 주를 각각 100으로 두었다. 서로 다른 기준 주에 정규화한 지수 수준을 직접 비교하지 않으며, 빠진 카드가 있는 주는 결측으로 둔다. 주별 누락 종목은 [출처별 PCPI 표](results/pcpi_by_source.csv)에 있다.

|카드|eBay 거래|관측 주|100건까지 부족|
|---|---:|---:|---:|
{coverage_lines}
"""
    accepted = quality["outcome"].isin(["accepted", "accepted_outlier"]) if quality is not None else pd.Series(dtype=bool)
    rejected = int(quality.loc[~accepted, "rows"].sum()) if quality is not None else 0
    flagged = int(quality.loc[quality["outcome"].eq("accepted_outlier"), "rows"].sum()) if quality is not None else 0
    questions = [q.replace("PSA 실거래", f"{sales_source} 실거래") for q in QUESTIONS]
    question_rows = "\n".join(f"{i}. {q}\n   {a}" for i, (q, a) in enumerate(zip(questions, answers), 1))
    sections = "\n\n".join(observations)
    secondary = int(summary["pricecharting_sales"].sum()) if not summary.empty else 0
    estimates = int(quality.loc[accepted & quality["data_type"].eq("market_estimate"), "rows"].sum()) if quality is not None else 0
    below_target = len(cards) if summary.empty else int(summary["observed_sales"].lt(100).sum())
    en_count = sum(c["language"] == "en" for c in cards)
    comparison = tables.get("language_comparison") if tables is not None else None
    language_text = f"두 판본 모두 {sales_source} 100건 이상이고 공통 관측 주가 3개 이상인 검증된 쌍이 없다."
    if comparison is not None and len(comparison):
        language_text = "\n".join(
            f"- {r.artwork_id} · 공통 {r.paired_weeks}주, 일본판 가격 프리미엄 중앙값 "
            f"{number(r.ja_premium_pct, True)}, 공통 창의 영문판 {r.en_observed_sales}건·일본판 {r.ja_observed_sales}건, "
            f"수익률 영문 {number(r.en_return, True)}·일본 {number(r.ja_return, True)}, "
            f"변동성 영문 {number(r.en_volatility, True)}·일본 {number(r.ja_volatility, True)}."
            for r in comparison.itertuples(index=False)
        )
    source_dates = tables.get("source_date_coverage") if tables is not None else None
    history = "2025년 출처별 관측 자료가 없다."
    if source_dates is not None:
        year_rows = source_dates.loc[source_dates["year"].eq(2025)]
        if len(year_rows):
            history = "2025년에 확보한 관측은 출처별로 " + ", ".join(
                f"{r.source} {r.sales:,}건({day(r.first_sale)}~{day(r.last_sale)})"
                for r in year_rows.itertuples(index=False)
            ) + "이다. 출처 간 거래 중복 가능성이 있어 합계를 제시하지 않는다."
    source_summary = tables.get("ebay_source_summary") if tables is not None else None
    cross_check = "공통 eBay 상품 ID 대조를 실행하지 않았다."
    if source_summary is not None:
        counts = source_summary[["matched_listings", "same_date", "same_price", "same_date_and_price"]].sum()
        cross_check = (f"PSA와 CompSniper의 eBay 상품 ID가 같은 기록 {counts['matched_listings']}건 중 "
                       f"날짜 일치 {counts['same_date']}건, 가격 일치 {counts['same_price']}건, "
                       f"날짜·가격 모두 일치 {counts['same_date_and_price']}건이었다. "
                       "불일치 거래는 각 출처에 그대로 보관했다. 세부 대조는 ebay_source_summary.csv에 기록했다.")
    source_limit = ("CompSniper 표본의 등급·판본은 목록 제목과 카드 식별 정보로 확인했다. "
                    "PSA 인증번호를 개별 대조하거나 전체 판매를 확인하지 않았다."
                    if sales_source == "CompSniper" else "")
    status = ("수치는 입력 CSV에서 검증된 관측에 근거한다." if total else
              "이 보고서는 포켓몬 카드 분석 상태를 보여준다. 제출 요건인 실측 시각화와 수치 인사이트는 아직 확보되지 않았다.")
    path.write_text(f"""# Pokémon Card Market Analysis

## 1. 프로젝트 개요

영문판·일본판 PSA 10 포켓몬 카드의 USD 실거래 가격과 관측 거래량을 분석한다. {status}

## 2. 분석 주제 및 선정 이유

확장팩과 발매 시기가 다른 인기 카드의 수집 시장을 가격 흐름, 거래 빈도, 변동 위험의 관점에서 비교한다.

## 3. 분석 질문

{question_rows}

## 4. 분석 대상 카드 소개

|ID|카드|번호|확장팩|언어|
|---|---|---|---|---|
{card_lines}

## 5. 데이터 출처 및 수집 방법

이번 분석 실행의 거래 출처는 {sales_source}다. PSA, CompSniper와 PriceCharting 데이터는 출처별로 분리한다. {source_limit} [출처 검토](DATA_SOURCE_REVIEW.md)

## 6. 데이터 기본 정보

목표 범위는 {START}~{END}이다. 정제 후 {sales_source} 실거래 {total:,}건, PriceCharting 실거래 {secondary:,}건, 추정 시세 {estimates:,}점이다. {sales_source} 거래 100건 미만인 카드는 {below_target}종이다. [데이터 사전](DATA_DICTIONARY.md)

## 7. 결측치 및 이상치 처리

허용 기준 위반으로 제외한 행은 {rejected:,}개, IQR 경계 밖 표시 후 유지한 거래는 {flagged:,}건이다. 가격 결측은 빈 값으로 유지한다. 수집 확인일에만 무거래 0을 기록한다. 전후 건수와 제외 사유는 data_quality_report.csv에 기록한다.

## 8. 시계열 분석 방법

7·30일 달력 창의 일별 중앙값 평균으로 단기 노이즈를 완화한다. 주·월 중앙값은 각 거래에서 직접 산출한다. 연속 달력 구간만 변화율을 계산한다. 8주 이동 변동성은 유효 수익률 4개 이상에서 계산한다. 최대 낙폭은 관측 일별 중앙값의 이전 최고점 대비 하락률이다. Pearson 상관에는 유효 쌍 3개 이상이 필요하다. 추세는 이 기간의 가격 방향, 계절성은 반복되는 달력 주기, 노이즈는 단기 변동을 뜻한다. 여기서는 계절성 검정을 수행하지 않는다.

## 9. 시각화 결과

{gallery or "검증된 데이터가 없어 생성된 그래프가 없다."}

## 10. 카드별 분석 결과

|ID|{sales_source} 거래|첫 거래|마지막 거래|관측 일 / 주 / 월|누적 수익률|주간 변동성|최대 낙폭|주간 수익률 / 거래량-가격 쌍|
|---|---:|---|---|---|---:|---:|---:|---|
{chr(10).join(result_lines)}

## 11. 자체 가격 지수 분석

고정 바스켓은 영문판 {en_count}종, 일본판 {len(cards) - en_count}종이다. 표의 각 언어판을 전 분석 기간에 고정한다. [판본 선정과 자료 확보 상태](DATA_SOURCE_REVIEW.md)

{index_text} 첫 공통 관측 주의 카드별 중앙값을 각각 100으로 놓고 동일 가중치로 평균한다. 종목이 빠진 주의 지수는 결측이다. 선정 카드의 자체 지수이며 전체 시장 공식 지수가 아니다.

{source_index_section}

## 12. 두 데이터 출처 비교

질문 7에 월별 매칭 결과를 기록한다. 같은 eBay 거래가 양쪽에 존재할 수 있어 양쪽 실거래를 합산하지 않는다.

### 2025년 표본

{history} Goldin의 구매자 수수료 포함 가격과 eBay 가격은 별도로 보관했다.

### PSA와 CompSniper 교차 검증

{cross_check}

### 판본별 비교

{language_text}

## 13. 주요 인사이트

{sections or "실거래 입력 확보 전까지 관찰이나 가설을 수치 결과로 제시하지 않는다."}

## 14. 결론

{("질문별 결과는 관측 거래와 공통 관측 주의 범위에서 해석한다." if total else "현재 확보된 포켓몬 실거래 입력은 0건이다. 가격 순위와 시장 흐름 판단은 보류한다.")}

## 15. 분석 한계점

관측 거래량은 자료에서 확인한 거래 건수다. 출처의 보고 범위 밖 거래, 거래 취소, 플랫폼 수수료와 배송비 포함 여부는 확인 가능한 범위에 의존한다. 카드당 목표 100건을 충족하지 못한 종목을 공개하고 대체 후보는 실제 자료를 확인한 뒤 선택한다.

## 16. 참고 자료

- [PSA Auction Prices Realized](https://www.psacard.com/auctionprices)
- [PriceCharting API 문서](https://www.pricecharting.com/api-documentation)
- [Pokémon TCG 영어 카드 목록](https://github.com/PokemonTCG/pokemon-tcg-data)

## 17. AI 활용 및 검증 과정

AI로 코드와 보고서 초안을 작성했다. 테스트용 관측은 임시 디렉터리에 격리했다. 결과를 검토할 때는 원본 행의 출처·등급을 대조하고 결과 CSV, 그래프의 축과 보고서 수치를 함께 확인한다.
""", encoding="utf-8")
