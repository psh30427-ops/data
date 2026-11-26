# Pokémon Card Market Analysis

영문판·일본판 PSA 10 카드 실거래의 가격·거래량·변동성·상관관계와 10종 고정 바스켓 지수를 분석하는 교육용 Python 프로젝트다. [포켓몬 분석 상태](REPORT.md)와 [출처 확인 결과](DATA_SOURCE_REVIEW.md)를 참고한다.


## 분석 대상

Pikachu with Grey Felt Hat 085/SVP, Umbreon VMAX 215/203, Charizard ex 199/165, Giratina V 186/196, Gengar VMAX 271/264, Rayquaza VMAX 218/203, Mew ex 232/091, Magikarp 203/193, Lugia V 186/195, Pikachu ex 238/191. 상세 식별자는 [카드 설정](config/cards.json)에 있다.

## 설치와 실행

Python 3.11 이상을 사용한다. 바탕화면에 프로젝트 폴더를 복사한 뒤 해당 폴더에서 실행한다.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest
python main.py --validate-sources
python main.py --all
```

Windows PowerShell에서는 활성화 명령을 `.venv\Scripts\Activate.ps1`로 바꾼다. 클라우드에서는 `.venv/bin/python`으로 직접 실행할 수도 있다.

## 포켓몬 입력과 분석

1. PSA Auction Prices Realized에서 사용이 허가된 영문판·일본판 PSA 10 거래를 확인한다. 원본 파일을 `data/raw/psa_sales.csv` 또는 `psa_sales_*.csv`로 저장한다.
2. PriceCharting의 자료는 `pricecharting_sales*.csv`(개별 판매)와 `pricecharting_market*.csv`(추정 시세)로 구분한다. 열과 수집 범위 규칙은 [데이터 사전](DATA_DICTIONARY.md)을 따른다.
3. `python main.py --all`로 정제·분석·보고서를 실행한다. 단계별 명령은 `--collect`, `--clean`, `--analyze`, `--report`다. `--collect`는 로컬 입력을 검사하며 원본을 변경하지 않는다. `--validate-sources`는 페이지 접근을 진단한다.
4. `results/`의 관측일·주·월 개수, 유효 표본 수, 수집 범위를 먼저 확인한다. 실거래 입력이 필요한 공통 비교와 PCPI는 빈 값을 유지한다. 입력이 적은 카드는 변동성 순위와의 비교에 주의한다.

가격은 USD이고, 관측 거래량은 입력 출처에서 확인된 건수다. 시세와 판매 자료를 합산하지 않는다. 이상값은 IQR로 표시하되 유지한다. 두 출처의 수집·재배포 조건이 확인되기 전까지 원본과 생성 결과는 Git에 추가하지 않는다. 현재 CSV 방식은 API 키를 사용하지 않으며 `.env.example`에는 비밀값이 없다.

## 파일 구조

- `main.py`, `src/` · CLI, CSV 수집, 정제, 분석, 시각화, 지수, 보고서
- `config/`, `data/raw/`, `data/processed/` · 카드 구성, 원본과 정제 관측
- `results/`, `figures/` · 포켓몬 표 및 PNG 생성 경로
- `tests/` · 기능 검증용 테스트

## CompSniper·ReefAPI 키 준비

프로젝트 폴더에서 `.env.example`을 같은 폴더의 `.env`로 복사한다. 기존 `.env`가 있으면 그대로 사용한다.

- Windows PowerShell에서 `if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }`를 실행한다.
- macOS·Linux에서 `(umask 077; set -C; [ -e .env ] || cat .env.example > .env)`를 실행한다.

프로젝트의 `main.py` 옆에 있는 `.env`를 편집기로 열고 각 줄의 등호 오른쪽에 해당 서비스에서 발급받은 키를 입력한다. `COMPSNIPER_API_KEY`에는 CompSniper 키를, `REEFAPI_API_KEY`에는 ReefAPI 키를 입력한다. `.env.example`의 값은 비워 둔다. Windows에서 확장자가 `.env.txt`가 되지 않도록 파일명을 확인한다.

`python main.py --collect`는 이미 확보한 로컬 CSV를 읽는다. CompSniper의 새 조회는 별도 옵션으로 실행하며 프로세스의 `COMPSNIPER_API_KEY`를 읽는다. 클라우드에서는 환경 설정에 키와 `api.compsniper.com`을 연결한다. 로컬에서는 사용하는 실행 환경에서 `.env`를 환경변수로 로드한 뒤 실행한다. ReefAPI 연동은 아직 없다.

```sh
python main.py --fetch-compsniper --card svp-85 --from-date 2026-08-28 --to-date 2026-11-25 --max-pages 2
python main.py --fetch-compsniper-history --card svp-85 --from-date 2025-01-01 --to-date 2025-12-31 --max-pages 1
python main.py --fetch-psa --card svp-85
python main.py --fetch-goldin --card svp-85 --max-pages 2
python main.py --all --sales-source CompSniper
```

조회는 계정 사용량을 먼저 확인하며 Basic 잔여량과 지정한 페이지 한도 안에서 실행한다. 다른 카드 ID도 설정 파일에서 선택할 수 있다. eBay의 판매일과 USD 판매가를 사용하며 판매 제목으로 PSA 10과 판본을 판별한다. 제목에 명시되지 않은 다른 카드의 언어와 공개되지 않은 협상가는 제외한다. 반 고흐 피카츄는 동일 일본판이 없다는 카탈로그 근거를 사용할 수 있다. 원본 CSV는 기존 Git 제외 경로에 보관한다. `--fetch-psa`는 CompSniper의 PSA 연동으로 `config/psa_specs.json`에 등록한 정확한 판본의 최근 판매를 최대 50건 조회한다. 인증번호·등급·통화·거래 URL을 확인하고 공급자가 판본 불일치로 표시한 행은 제외한다. 이 API에는 개별 거래의 과거 페이지 또는 종료일 지정 기능이 없다. 기본 분석 출처는 PSA이며 CompSniper를 지정할 때도 가격·거래량을 출처 간 합산하지 않는다.

Codex Cloud에서 CompSniper를 실행하려면 프로젝트 파일 대신 해당 환경의 **Settings → Secrets**에서 동일한 이름으로 키를 등록한다. 환경에서 외부 HTTPS 목적지 연결을 설정해야 한다면 서비스 공식 문서에 나오는 API 호스트에만 연결한다. 키 값은 비밀 입력란이나 로컬 `.env`에 입력하며 채팅, 명령줄, 로그, GitHub에는 넣지 않는다.

## GitHub 제출

프로젝트 루트에서 `git check-ignore -v -- .env`로 제외 규칙을 확인한다. `git ls-files -- .env`는 아무 경로도 출력하지 않아야 한다. `.env.example`은 두 변수명과 빈 값만 포함한 상태로 제출할 수 있다.

## 판본 선정과 환율

[카드 설정](config/cards.json)의 `artwork_id`는 일러스트, `card_id`는 거래 상품을 구분한다. `selected`가 참인 판본만 핵심 분석과 PCPI에 사용한다. 현재 시험 PCPI는 영어판 4종과 일본판 6종을 고정한다. PSA 표본에서 전 종목 동시 관측 주가 가장 많은 조합을 고르고, 동률은 고유 거래일 합으로 비교했다. 분석 기간 전체의 빈 주는 그대로 남아 있다. 같은 일러스트를 두 번 편입할 수 없다. `variant_availability.csv`의 출처별 관측과 품질을 검토한다.

USD 자료는 기존 `price_usd` 형식을 그대로 사용할 수 있다. JPY 자료는 `original_price`, `fx_rate_to_usd`, `fx_rate_date`, `fx_source_url`을 함께 제공한다. USD로 판매한 일본판은 USD 자료로 입력한다. [상세 입력 형식](DATA_DICTIONARY.md)

GitHub 제출 전 `git status --short`로 업로드 대상과 재배포 권한을 확인한다. 검토한 파일을 커밋한 뒤 연결된 저장소가 있을 때 `git push -u origin main`으로 제출한다.


`--fetch-compsniper-history`는 eBay 기간 조회에서 단일 판매와 개별 판매가가 있는 행만 읽는다. 표시 통화는 USD이며 원 결제 통화를 증명하지 않는다. `--fetch-goldin`은 반 고흐 피카츄 한정 경매 수집이다. 구매자 수수료 포함 USD 종가를 별도 출처로 보관하고 기본 분석에 합산하지 않는다.
