# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 상태

CNC 선반 보전관리 에이전트. Python + Streamlit 앱으로 구현해 Streamlit Community Cloud에 배포하고 계속 운영한다.
**3단계(Streamlit UI) 완료.** PRD F1~F6이 `scripts/`에 구현되어 CLI로 동작하고, Streamlit 6개 화면(대시보드·설비 상세·이력 등록·교체 도래·고장 분석·이력 조회)이 이 함수들을 호출한다. 다음은 4단계(Playwright 검토)다.

| 파일 | 역할 |
|---|---|
| `prd.md` | 요구사항의 기준 문서. 범위·구조부·기능(F1~F6)·판정 기준·성공 지표·배포 운영 방침. 구현과 충돌하면 PRD가 우선 |
| `prompts.md` | 5단계 개발 프롬프트 (1 뼈대 → 2 기능 → 3 Streamlit UI → 4 Playwright 검토 → 5 배포·운영). 다음 단계의 상세 설계 |
| `초안.md`, `image.png` | 에이전트 행동 지침 원본, 구조부 10개의 출처인 CNC 선반 구조도 |

개발은 `prompts.md`의 단계 순서를 따른다. 단계가 끝날 때마다 이 파일의 명령과 구조를 실제 구현에 맞게 고친다(새로 만들지 않는다).

## 명령

가상환경은 `.venv`(Python 3.14). 명령은 `.venv/Scripts/python`으로 실행한다.

```
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python scripts/init_db.py --yes            # 로컬 샘플 DB 재생성 (기존 DB 삭제)
.venv/Scripts/python scripts/query.py --schema --format table
.venv/Scripts/python scripts/query.py "SELECT ..." [--limit 200] [--format table]
.venv/Scripts/python scripts/normalize.py "3번기 주축 베어링 소음나서 교체"      # 자연어 해석
.venv/Scripts/python scripts/log_repair.py --equipment 3호기 --part BR-01 --action 교체 [--breakdown] [--date YYYY-MM-DD] [--desc ..] --dry-run
.venv/Scripts/python scripts/due_check.py [--equipment] [--unit TS] [--days 30] [--all] [--save]
.venv/Scripts/python scripts/analyze.py [--months 6] [--equipment] [--save]
.venv/Scripts/python scripts/equipment.py --equipment 3호기                     # 구조부 사양·장착 파트·최근 이력
.venv/Scripts/python scripts/history.py [--equipment] [--part] [--from] [--to] [--breakdown yes|no]
.venv/Scripts/python -m pytest                           # 전체 테스트
.venv/Scripts/python -m pytest tests/test_log_repair.py::test_repeat_failure   # 단일 테스트
.venv/Scripts/python -m pytest tests/test_mapping_accuracy.py -s               # 매핑 정확도 출력
TEST_DATABASE_URL=postgresql+psycopg://…/cnc_test .venv/Scripts/python -m pytest   # PostgreSQL에서도 실행 (DB 이름에 test 필수)
.venv/Scripts/python -m streamlit run streamlit_app.py
.venv/Scripts/python -m streamlit run streamlit_app.py --server.headless true --server.port 8501   # E2E용
```

모든 CLI는 `--format json|table`을 받고, 사용자 오류는 `오류: …`를 stderr에 찍고 종료코드 2로 끝난다(`common.run_cli`).

## 아키텍처

- **계층**: Streamlit 페이지(`streamlit_app.py`가 `st.navigation`으로 `app_pages/*.py` 등록) → `scripts/`의 함수 → DB. 페이지에는 로직을 두지 않는다. 각 스크립트는 import 가능한 함수 + argparse CLI 이중 구조이고, CLI로 직접 실행될 때를 위해 파일 첫머리에서 저장소 루트를 `sys.path`에 넣은 뒤 `from scripts.… import`를 쓴다
- **스키마의 원본은 `scripts/schema.py`**(SQLAlchemy Core). 구조부 사양 테이블은 `schema.SPEC_TABLES`(구조부 코드 → Table)로 모여 있고 `_spec_table()`이 사양 컬럼이 정확히 3개인지 검사한다. 마스터 데이터(설비·구조부·파트 39개·사양 샘플)는 `scripts/master_data.py`에 있어 5단계 운영 DB 마스터 입력에서도 다시 쓴다
- **마이그레이션**: `migrations/NNN_*.py`의 `upgrade(conn)`을 `scripts/migrate_lib.apply_pending()`이 순서대로 적용하고 `schema_version`에 기록한다. 이미 있는 마이그레이션 파일은 고치지 않는다. 스키마를 바꿀 때는 `schema.py`와 새 `NNN_*.py`를 함께 추가한다
- **DB 이중 지원**: `scripts/common.py`가 SQLite(로컬)와 PostgreSQL(운영)을 모두 연결한다. URL 우선순위는 `DATABASE_URL` → `st.secrets["database"]["url"]` → `db/maintenance.db`. SQL은 두 DB 공통 문법만 쓰고 날짜 계산은 Python에서 한다
- **읽기전용 이중 안전장치**: `query.validate_sql()`이 SELECT/WITH 단일 문장만 통과시키고(문자열·주석을 지운 뒤 키워드 검사), `common.read_connection()`이 SQLite는 `mode=ro`, PostgreSQL은 `SET TRANSACTION READ ONLY`로 연다. 쓰기 경로는 `log_repair.py` 하나뿐
- **운영 DB는 외부 PostgreSQL만**: Community Cloud는 재시작·재배포 때 파일이 초기화된다. `init_db.build_database()`는 SQLite가 아닌 URL을 거부한다. 현재 배포는 시연용이다: `streamlit_app.ensure_demo_db()`가 DB URL이 기본값이고 파일이 없을 때만 샘플 DB를 만든다(`DATABASE_URL`을 준 테스트·E2E에서는 동작하지 않음)
- **4단계 검토**: `reviews/review_20260929.md`에 PRD 추적·결함 목록(B-01~B-18)이 있다. 높음 2건(B-01 짧은 별칭 오매핑, B-02 query 검사 우회)만 수정됐고 나머지는 미수정이다. E2E는 `tests/e2e/`(실행 방법은 그 conftest 문서), `E2E_BASE_URL`이 없으면 수집되지 않는다. E2E용 `playwright`·`pytest-playwright`는 requirements.txt에 넣지 않았다(Cloud 설치 제외)
- **사용량·판정의 단일 구현은 `scripts/usage.py`**. `UsageData(conn)`이 설비·파트·가동로그·이력을 한 번에 메모리로 읽고, `log_repair`(info 판정)·`due_check`·`analyze`가 모두 이것을 쓴다. 판정 수치(50%, 90일, 30일)도 여기 상수로 있다. 핵심 가정:
    - 가동로그는 설비 도입 이후 누적값이다. 첫 로그 이전 날짜는 도입일(0)과 첫 로그를 잇는 직선으로 추정한다(`counter()`). `init_db`의 이전 교체 이력 생성도 같은 가정으로 역산한다
    - 사용량 = 직전 "리셋 작업" 이후 증가분. 리셋은 기본 `교체`, 예외는 `RESET_ACTIONS`(LB-01 습동유는 `보충`, EL-03 판넬 쿨러 필터는 `청소`). 리셋 이력이 없으면 도입 이후 전체
    - 조기고장은 이전 리셋 기록이 있을 때만 판정한다(원부품은 판단하지 않음). 반복고장은 당일 포함 이전 90일 돌발
    - 일평균 사용량은 기준일 직전 30일 증가분 / 30. 교체 도래 기준일은 최근 가동로그일이지만, 그 뒤(오늘) 등록된 교체도 반영한다
- **용어 해석(`normalize.py`)**: 동의어 치환(`SYNONYMS`) → 설비 표현·조치 동사·`_STOPWORDS` 제거 → 공백을 없앤 문장에 별칭이 포함되는지 검사해 **가장 길게 일치한 파트만** 후보로 둔다. 없으면 단어가 별칭에 포함되는 파트로 넓힌다. "베어링"이 있으면 BR 유닛만 본다. 별칭은 `parts.aliases`(쉼표 구분)이고, 짧은 별칭이 일반 단어와 겹치면 오매핑이 생긴다(예: 'FAN'이 'FANUC'에 걸려 제거함). 별칭을 바꾸면 `tests/fixtures/phrases.json` 정확도 테스트를 돌린다
- **등록(`log_repair.py`)**: dry-run은 읽기전용 연결에서 `build_row` + `judge`만 한다. 실제 등록은 한 트랜잭션에서 `judge` → `_insert` → (`교체`면) `_deduct_stock`(재고 0 밑으로 내려가지 않음). info 종류는 조기고장·반복고장·예비품 부족·중복 의심
- **샘플 데이터**(`init_db.py`, seed 고정): 최근 가동로그일은 어제. 설비×파트마다 교체주기의 15~108%를 쓴 시점에 "이전 교체 이력"을 넣어 초과 약 9%·임박 약 5% 분포를 만든다. `SCENARIOS`에 조기고장(CNC-05 HS-04, CNC-09 TS-07)과 반복고장(CNC-07 TS-04, CNC-02 SD-02) 사례를 넣었고 이 조합은 이전 교체 이력에서 뺐다. `master_data`의 재고에는 예비품 부족 사례(BR-01, TS-02, HS-02)가 있다. 판정 테스트는 이 사례를 기대값으로 쓰므로 seed·시나리오를 바꾸면 테스트도 고친다. Streamlit 등이 DB 파일을 열고 있으면 재생성이 거부된다
- **테스트**: `tests/conftest.py`가 고정 종료일(2026-09-28)로 DB를 만든다. `db_url`(세션 공용, 읽기 전용)과 `writable_db_url`(쓰기 테스트용 복사본)을 구분해서 쓴다. `TEST_DATABASE_URL`이 있으면 모든 테스트가 PostgreSQL로도 한 번 더 돈다(`DATABASE_URL`은 운영일 수 있어 쓰지 않음). Streamlit은 `tests/test_streamlit_app.py`에서 `AppTest`로, `DATABASE_URL`을 테스트 DB로 바꾸고 저장소 루트로 `chdir`한 뒤 `switch_page`로 페이지를 연다. 조기고장·반복고장 경고는 `st.error`로 그려지므로 등록 화면 테스트에서 `at.error`가 비어 있기를 기대하면 안 된다
- **화면 전용 조회 함수**: 페이지가 계산하지 않도록 `scripts/equipment.py`(설비·파트 목록, 설비 상세 = 구조부 사양 + 장착 파트 도래 + 최근 이력, `SPEC_LABELS`), `scripts/history.py`(필터 이력 조회), `scripts/dashboard.py`(대시보드 요약)가 있다. 이력 필터처럼 사용자 입력이 들어가는 조회는 `query.py`에 SQL을 만들어 넘기지 말고 이런 함수에 Core 조건으로 추가한다
- **Streamlit 구조**: `app_pages/_components.py`에 `@st.cache_data(ttl=60)` 래퍼(`cached_*`, 첫 인자로 DB URL을 받아 DB별로 캐시 분리), `load()`(UserError·기타 예외를 traceback 대신 안내문으로 표시), 상태 색·표 변환·info 경고 표시가 모여 있다. 등록 성공 시 `st.cache_data.clear()`. 페이지가 아닌 모듈(`_components.py`, `scripts/`)을 고치면 실행 중인 Streamlit 서버를 재시작해야 반영된다
- **등록 화면(`app_pages/register.py`) 규칙**: 모든 입력 위젯 값은 Session State(`reg_*` 키)로만 관리한다(`index`/`value` 인자를 같이 주면 경고가 뜸). `st.form`은 쓰지 않는다(제출 전 변경을 감지할 수 없어 무효화 규칙이 깨짐). 미리보기는 `{"params", "result", "token"}`으로 저장되고, 현재 입력과 `params`가 다르면 무효 처리한다. 등록은 항상 미리보기의 `params`로만 실행되고 토큰은 1회용(`used_tokens`)이라 연타해도 1건만 들어간다. 콜백 안에서는 `current_params()`로 최신 값을 다시 읽는다(콜백은 직전 실행의 변수를 보기 때문). 확인 창은 `confirm_open` 세션 값으로 열림 상태를 유지한다(dialog를 버튼 반환값에만 묶으면 전체 재실행 때 확인 버튼이 사라짐)
- **E2E 선택자**: 위젯·주요 컨테이너마다 고유 `key`가 있다(`nl_input`, `parse_btn`, `preview_btn`, `register_btn`, `confirm_register_btn`, `cancel_register_btn`, `info_banner`, `result_info_banner`, `due_table`, `due_download`, `finding_card_<n>`, `eq_btn_<CNC-NN>`, `detail_equipment_select` 등). Playwright에서는 `.st-key-<key>` 클래스로 찾고, 클릭 뒤 재실행이 끝날 때까지 기다린다. 전체 화면 캡처는 안쪽 스크롤 영역 때문에 첫 화면만 찍히므로 `scrollIntoView` 후 찍는다

비밀값은 `.streamlit/secrets.toml`(Git 제외)에 두고 형식은 `.streamlit/secrets.toml.example`을 따른다.

## 도메인 핵심 (prd.md 3·7장 요약)

- 설비: `CNC-01` ~ `CNC-12` (12대). 범위 밖 번호는 거부하고 되묻는다
- 유닛 6개·파트 39개: HS-01~05, TS-01~07, SD-01~07, BR-01~07, LB-01~06, EL-01~07
- **베어링은 장착 위치와 무관하게 항상 BR 유닛** ("주축 베어링" → BR-01/BR-02, HS 아님)
- 분류 축이 두 개다: `parts.unit`은 유지보수 유닛(무엇을 관리하나), `parts.assembly_code`는 설비 구조도의 구조부 10개(어디에 달려 있나: GBX 기어박스, HDS 주축대, CTL 제어장치, TUR 공구대, XSL 이송대, CAR 왕복대, TLS 심압대, NCU NC장치, BED 베드, OPP 운전조작반). 이송계는 X축 → XSL, Z축 → CAR. 파트별 매핑은 prd.md 3장 표
- 구조부마다 설비별 사양 테이블 `spec_<구조부>`가 있고, `equipment_id` + 사양 컬럼 3개 + `updated_at`으로 되어 있다(prd.md 5장). 사양 샘플값도 데모용 가정값
- 조치 유형 6종만: 교체 / 수리 / 조정 / 청소 / 점검 / 보충
- 교체 기준(basis): `run_hours` / `clamp_count` / `index_count` / `months`. `interval_value`와 단가는 **데모용 가정값**
- 판정 기준: 조기고장 = 돌발 교체·수리 시 사용량 < 교체주기의 50% · 반복고장 = 같은 설비·파트 돌발 90일 내 재발 · 예비품 부족 = 재고 ≤ 안전재고(기본 1) 또는 30일 내 도래 수량보다 적음

## 에이전트 운영 규칙 (이 저장소에서 보전관리 에이전트로 동작할 때)

사용자는 생산관리/설비보전 엔지니어와 현장 작업자다. 답변은 한국어, 현장 용어 그대로.

- 설비 호칭: "3호기", "3번기", "03번" → `CNC-03`
- 현장 문장은 먼저 `normalize.py "<문장>"`으로 해석한다. `questions`가 비어 있지 않으면 그 내용을 되묻고, 파트 후보가 여러 개면 후보를 보여주고 고르게 한다
- 그래도 모르는 파트 표현은 조회: `python scripts/query.py "SELECT part_id, part_name, aliases FROM parts WHERE aliases LIKE '%키워드%'"`
- 동의어: 죠=조=jaw, 공구대=터렛, 라이브센터=회전센터, 솔밸브=솔레노이드 밸브, 앱솔 배터리=APC 배터리, 웨이오일=습동유, MC=마그네트 접촉기
- 돌발(`--breakdown`): 알람, 정지, 파손, 누유, 불량 등 예정에 없던 대응. "주기 도래", "PM", "예방", "정기"는 예방 작업

1. DB 쓰기 전 반드시 `log_repair.py --dry-run` 결과를 표로 보여주고 "등록할까요?"에 승인받은 뒤 실행한다.
2. 설비·파트를 특정할 수 없으면 추측하지 말고 후보를 제시해 되묻는다. 존재하지 않는 파트ID를 만들지 않는다.
3. DB를 직접 수정하거나 스키마를 바꾸지 않는다(`sqlite3`, `psql` 포함). 조회는 `query.py`, 쓰기는 `log_repair.py`만.
4. `log_repair.py` 결과의 `info`(조기고장, 반복고장, 예비품 부족, 중복 의심)는 반드시 강조해 전달한다.
5. 분석 결과는 표를 나열하지 말고 **문제 → 추정 원인 → 권장 조치** 순으로 해석한다. `analyze.py`의 `findings`를 바탕으로 하되, 원인은 "추정"임을 밝히고 확인 방법(압력·진동 측정, 배관 점검 등)을 함께 제시한다.
6. 날짜 미지정 시 등록은 오늘, 점검·분석은 최근 가동로그일 기준.
7. 교체주기·단가를 답할 때 데모용 가정값이며 실제 기준은 제조사 매뉴얼·사내 보전기준을 따라야 한다고 안내한다.
8. `init_db.py`는 기존 DB를 삭제하므로 사용자 확인 없이 실행하지 않는다. `DATABASE_URL`이 운영 DB를 가리키면 쓰기·마이그레이션 전에 반드시 확인받는다.
