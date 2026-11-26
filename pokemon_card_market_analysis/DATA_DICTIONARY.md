# 데이터 사전

## 원본 CSV

|열|형식과 기준|
|---|---|
|date|달력 날짜, YYYY-MM-DD 또는 YYYY/MM/DD|
|card_id|config/cards.json의 고유 ID|
|card_name, card_number, set_name|설정에 등록된 이름, 전체 번호, 카탈로그 확장팩 이름|
|language|en/English/eng 또는 ja/Japanese/jpn/jp/日本語|
|grade|PSA 10 또는 10. 다른 인증사의 10등급은 입력 대상에서 제외|
|price_usd|기존 USD 입력에서 사용하는 금액. 정제 결과에서는 환산 후 USD 금액|
|currency|원본 거래 통화. USD 또는 JPY|
|original_price|JPY 필수. USD에서는 원본 금액으로 우선 사용하며, 비어 있으면 기존 price_usd를 읽음|
|fx_rate_to_usd|JPY 필수. 1 JPY당 USD. JPY per USD 고시율은 역수를 입력|
|fx_rate_date|JPY 필수. 거래일과 같은 환율 기준일|
|fx_source_url|JPY 필수. 해당 환율 근거 URL|
|marketplace, sale_type|거래 시장과 방식. 확인 가능한 값 기록|
|sale_id|출처 및 거래 시장 범위의 고유 거래 ID|
|cert_number|PSA 인증번호. 재판매가 가능하므로 중복 제거 키로 쓰지 않음|
|source_url|거래 또는 추정가 출처 HTTP(S) URL|
|collected_at|수집 시점의 달력 날짜. 관측 날짜 이전일 수 없음|

거래 시장, 방식, 거래 ID, 인증번호 4개 열은 선택 입력이다. 거래 ID가 없다면 같은 날짜·가격도 서로 다른 거래일 수 있어 보존한다. 거래 ID가 같은데 카드·날짜·가격이 충돌하면 해당 기록을 보류한다. 파일명에 따라 `source`, `data_type`, `input_file`을 부여한다. 원본의 다른 열은 원래 파일에 보존된다. `outlier_iqr`은 출처·카드별 IQR 경계 밖 기록을 표시한다.

## 범위 입력

`data/raw/psa_coverage.csv`에는 `card_id,start_date,end_date`를 기록한다. 두 날짜를 포함하며 해당 범위 전체를 조사한 경우에만 입력한다. 이 파일이 없거나 포함하지 않는 날은 가격 관측이 없을 경우 수집 상태가 미확인이다. 조사했지만 관측 거래가 없는 날은 거래량 0, 가격은 결측이다. 월·주의 양 끝에서 분석 창에 포함된 날만 집계한다.

## 결과

- `daily_prices.csv` · 관측 일별 가격 중앙값, 관측 거래량, 7·30일 이동평균, 낙폭
- `weekly_prices.csv` · 일요일 종료 기준 주간 판매 중앙값, 거래량, 조사 범위, 전주 대비 변화율, 정규화 가격, 8주 이동 변동성
- `monthly_volume.csv` · 월초 날짜 표기, 월간 판매 중앙값, 관측 거래량, 조사 범위, 전월 대비 변화율
- `card_summary.csv` · 카드별 출처별 거래수, 관측 기간과 관측 일·주·월 수, 가격 극값, 수익률, 표준편차, 최대 낙폭, 거래량·가격 상관 및 표본 수
- `correlation_matrix.csv`, `correlation_sample_sizes.csv` · 카드 간 주간 수익률의 Pearson r 및 유효 쌍
- `market_index.csv` · 주간 PCPI, 관측 카드 수, 지수 포함 카드 수 및 기준 주
- `price_shocks.csv` · 절댓값 20% 이상 주간 가격 변동과 다음 달력 주 수익률
- `source_comparison.csv` · 동일 카드·월 PSA 거래 중앙값 대 PriceCharting 추정치 중앙값 및 차이
- `data_quality_report.csv` · 출처·유형·카드·검증 결과별 입력 행 수. accepted 및 accepted_outlier 합계가 정제 후 건수

JPY 거래는 거래일의 확인 가능한 환율이 없으면 `invalid_fx`로 기록한다. 이전 날짜의 고시를 자동 적용하지 않는다. USD 거래에는 단위 환산값 1이 기록된다. 입력 환율과 출처는 원본 제공자가 확인하며 정제 코드는 날짜·형식을 검사한다.

- `variant_availability.csv` · 판본×출처별 원본 판매 행 수, 유효 판매 수, 고유 날짜 수, 첫·마지막 판매일, 필수 정보 결측 및 IQR 표시 비율. 분모가 없는 비율은 결측이다. 서로 다른 출처는 합산하지 않는다.
- `language_comparison.csv` · 각 판본 PSA 판매 100건 이상·공통 관측 3주 이상인 검증된 동일 일러스트의 공통 창 거래량, 주간 수익률과 변동성, 주별 (일본판/영문판−1)의 중앙값. 공통 주 사이 결측을 건너뛰어 변동성을 계산하지 않는다.

- `compsniper_sales_<card_id>_<start>_<end>.csv` · eBay 판매 완료 목록에서 선별한 USD 입력. `listing_title`과 `language_evidence`는 원본 CSV에 남고, 정제 입력은 기존 공통 스키마를 사용한다. 날짜는 `endedAt`, 금액은 배송비 제외 `soldPrice`다.
- `--sales-source CompSniper`에서는 CompSniper 실거래만 기본 집계에 사용한다. 검색 표본으로 전체 조사 여부를 확인할 수 없으므로 수집 범위가 불명확한 날은 무거래 0으로 취급하지 않는다.

- `psa_sales_comp_<card_id>_<date>.csv` · CompSniper의 PSA 연동에서 반환한 개별 판매 기록. `psa_spec_id`는 PSA 카탈로그 판본 ID, `cert_number`는 제공된 PSA 인증번호다. 공급자 표시 불일치, 인증번호·거래 ID·URL이 빠진 행은 가져오지 않는다.
- `ebay_source_pairs.csv`, `ebay_source_summary.csv` · PSA와 CompSniper 양쪽에서 유일하게 확인된 같은 카드·eBay 상품 ID별 가격과 날짜 일치 여부 및 요약. 합산이나 보정을 수행하지 않는다.

- `pcpi_by_source.csv` · 같은 고정 10종과 주간 달력으로 계산한 PSA 및 CompSniper/eBay의 독립 지수. 기준 주는 출처별 첫 전 종목 관측 주이며, `missing_card_ids`는 해당 주의 누락 종목이다.
- `pcpi_basket_coverage.csv` · 고정 편입 카드별·출처별 거래 건수, 고유 관측일·주, 첫·마지막 거래일, 카드당 100건까지 부족한 수.
