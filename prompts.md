# CNC 선반 보전관리 에이전트 — 단계별 개발 프롬프트

`prd.md`를 기준으로 한 단계별 프롬프트다. 단계마다 이전 단계가 끝난 뒤 그대로 붙여 넣어 사용한다.
모든 단계는 `prd.md`와 `CLAUDE.md`를 먼저 읽고 시작한다.

- 1단계: 기본 뼈대 (DB 계층, 스크립트 골격, Streamlit 골격)
- 2단계: 기능 추가 (F1~F6 로직 완성)
- 3단계: UI 디자인 (Streamlit 멀티페이지 앱)
- 4단계: PRD 대비 검토 + 버그 점검 (Playwright)
- 5단계: 배포와 지속 운영 (GitHub, 운영 DB, CI, Streamlit Community Cloud)

---

## 1단계 — 기본 뼈대 작성

```
prd.md와 CLAUDE.md를 먼저 끝까지 읽고, CNC 선반 보전관리 에이전트의 기본 뼈대를 만들어줘.
최종 결과물은 Python + Streamlit 앱이며 Streamlit Community Cloud에 배포해 계속 운영한다.
이 단계에서는 "구조와 데이터"만 만들고, 판정 로직(조기고장·반복고장·예비품 부족, 도래 계산, 패턴 분석)은 2단계에서 채운다.

[만들 것]
1. 폴더 구조
   - streamlit_app.py        : Streamlit 진입점 (st.navigation으로 페이지 등록, 이 단계에서는 빈 페이지)
   - app_pages/              : 페이지 파일 (dashboard, register, due, analysis, history)
   - scripts/                : common.py, query.py, log_repair.py, due_check.py, analyze.py, init_db.py
   - migrations/             : 버전 번호가 붙은 스키마 변경 SQL/스크립트 (001_init 등)
   - db/                     : 로컬 SQLite 파일 위치 (Git 제외)
   - reports/                : --save 결과 저장 위치 (Git 제외)
   - tests/
   - .streamlit/config.toml, .streamlit/secrets.toml.example
   - requirements.txt, .gitignore (db/*.db, reports/, .streamlit/secrets.toml 제외)

2. DB 계층 (scripts/common.py)
   - SQLAlchemy로 SQLite와 PostgreSQL을 모두 지원
   - 접속 URL 우선순위: 환경변수 DATABASE_URL → st.secrets["database"]["url"] → 기본값 sqlite:///db/maintenance.db
   - 읽기전용 연결 함수 제공: SQLite는 mode=ro, PostgreSQL은 SET TRANSACTION READ ONLY
   - SQL은 두 DB에서 모두 동작하게 작성. 날짜 계산은 SQL 함수 대신 Python에서 처리

3. DB 스키마 — PRD 5장 제안안을 확정 (SQLAlchemy Core 메타데이터로 정의, migrations/001_init 으로 생성)
   - equipment(equipment_id PK 'CNC-01'~'CNC-12', name, installed_at)
   - assemblies(assembly_code PK, name, description, sort_order)  -- prd.md 3장 "구조부" 10개
       GBX 기어박스, HDS 주축대, CTL 제어장치, TUR 공구대, XSL 이송대, CAR 왕복대, TLS 심압대, NCU NC장치, BED 베드, OPP 운전조작반
   - parts(part_id PK, unit, assembly_code FK, part_name, aliases,
           basis CHECK IN ('run_hours','clamp_count','index_count','months'),
           interval_value, unit_price, stock_qty, safety_stock DEFAULT 1)
       unit = 유지보수 유닛(HS/TS/SD/BR/LB/EL), assembly_code = 장착 위치. 매핑은 prd.md 3장 구조부 표를 그대로 따른다
   - 구조부 사양 테이블 10개: prd.md 5장 "구조부 사양 테이블" 표의 테이블명·컬럼명·단위를 그대로 사용
       각 테이블 = equipment_id(PK, FK) + 사양 컬럼 3개 + updated_at
       (spec_gearbox, spec_headstock, spec_control_cabinet, spec_turret, spec_cross_slide,
        spec_carriage, spec_tailstock, spec_nc_unit, spec_bed, spec_operator_panel)
       숫자 컬럼은 숫자형, 여부 컬럼(is_touchscreen, has_mpg)은 BOOLEAN, 규격 컬럼은 문자열
   - repair_logs(id PK, log_date, equipment_id FK, part_id FK,
                 action_type CHECK IN ('교체','수리','조정','청소','점검','보충'),
                 is_breakdown BOOLEAN, description, created_at)
   - run_logs(id PK, log_date, equipment_id FK, run_hours, clamp_count, index_count)  -- 누적값
   - schema_version 테이블로 적용된 마이그레이션 기록

4. 샘플 데이터 (init_db.py)
   - 설비 12대: CNC-01 ~ CNC-12
   - 파트 39개: PRD 3장 표의 파트ID 범위를 정확히 지킨다
     (HS-01~05, TS-01~07, SD-01~07, BR-01~07, LB-01~06, EL-01~07)
   - 베어링은 모두 BR 유닛 (스핀들 전면 BR-01, 후면 BR-02 …)
   - aliases에 PRD F1 동의어를 넣는다 (죠/조/jaw, 공구대→터렛, 라이브센터→회전센터, 솔밸브,
     앱솔 배터리→APC 배터리, 웨이오일→습동유, MC→마그네트 접촉기)
   - interval_value, unit_price는 "데모용 가정값"임을 코드 주석에 명시
   - 구조부 10개와 모든 파트의 assembly_code (prd.md 3장 표 기준, 39개 모두 채움)
   - 구조부 사양: 설비 12대 × 10개 테이블. prd.md 예시값을 기준으로 설비별로 조금씩 다르게(예: CNC-01~06 박스웨이,
     CNC-07~12 LM가이드) 만들고 "데모용 가정값"임을 주석에 명시
   - run_logs: 설비별 최근 12개월 일별 누적 가동로그
   - repair_logs: 최근 12개월 이력 150건 이상. 조기고장·반복고장(90일 내 재발)·예비품 부족 사례를 일부러 섞는다. seed 고정
   - 안전장치: --yes 없이는 기존 DB를 삭제하지 않고, 접속 URL이 sqlite가 아니면(운영 DB) 무조건 거부

5. 스크립트 골격
   - 각 스크립트는 "import 가능한 함수 + argparse CLI" 구조로 만든다 (Streamlit 페이지가 함수를 직접 호출)
   - CLI: -h 도움말, 결과는 JSON(기본) 또는 --format table, 한국어 메시지
   - query.py: --schema 구현, SELECT/WITH 단일 문장만 허용(그 외 거부), 읽기전용 연결 사용
   - log_repair.py: 함수 인자와 CLI 옵션(--equipment --part --action --breakdown --date --desc --dry-run) 정의,
     없는 equipment_id/part_id 거부까지 구현, 결과에 "info": [] 자리 마련
   - due_check.py, analyze.py: 인자만 정의하고 "미구현" 반환

6. Streamlit 골격
   - streamlit run streamlit_app.py 로 5개 빈 페이지가 사이드바에 보이면 된다
   - DB 엔진은 @st.cache_resource로 한 번만 생성

7. CLAUDE.md
   - 이미 있는 CLAUDE.md를 새로 만들지 말고, 실제 구현된 명령·구조에 맞게 고친다

8. 테스트
   - init_db 후 테이블, 설비 12대, 파트 39개, 유닛별 파트 수 확인
   - 구조부 10개, 모든 파트에 assembly_code가 있고 베어링(BR)이 prd.md 표대로 HDS/TUR/XSL/CAR에 배정됐는지
   - 사양 테이블 10개 × 설비 12행, 각 테이블 사양 컬럼이 정확히 3개인지
   - query.py가 INSERT/UPDATE/DELETE/DROP/다중 문장을 거부하는지
   - init_db가 postgresql:// URL을 거부하는지

[완료 조건]
- python scripts/init_db.py --yes 로 로컬 DB 생성 성공
- python scripts/query.py --schema 가 스키마 출력
- streamlit run streamlit_app.py 실행 성공
- pytest 통과
- 마지막에 만든 파일 목록과 각 파일 역할을 표로 정리해줘
```

---

## 2단계 — 기능 추가

```
prd.md, CLAUDE.md와 1단계 코드를 읽고, PRD 4장 기능 요구사항 F1~F6를 완성해줘.
스키마를 바꿔야 한다면 먼저 이유를 설명하고 확인받은 뒤 migrations/에 새 버전으로 추가해.
모든 로직은 scripts/의 함수에 두고, Streamlit 페이지는 3단계에서 이 함수를 호출만 한다.

[F1 현장 용어 해석] scripts/normalize.py
- 설비 호칭 정규화: "3호기", "3번기", "03번", "3번", "CNC3", "cnc-03" → CNC-03
- CNC-01~CNC-12 범위 밖이면 오류 ("13호기는 관리 대상이 아닙니다")
- 파트 별칭 검색: 키워드로 parts.aliases/part_name 검색 → 후보 목록 반환 (0개/1개/여러 개 구분)
- 베어링 키워드가 들어가면 항상 BR 유닛 후보만 반환 ("주축 베어링" → BR-01/BR-02)
- 조치 유형 6종 매핑 (갈았다/교환 → 교체, 고쳤다 → 수리, 맞췄다 → 조정, 닦았다 → 청소, 봤다 → 점검, 채웠다 → 보충)
- 돌발 판단: 알람/정지/파손/누유/불량 → breakdown, 주기 도래/PM/예방/정기 → 예방
- CLI: python scripts/normalize.py "3번기 주축 베어링 소음나서 교체" → 해석 결과 JSON

[F2 이력 등록] log_repair.py
- dry-run: DB 변경 없이 등록될 행 + info 반환
- 날짜 미지정 시 오늘
- info 판정 (prd.md 7장 판정 기준):
  - 조기고장: 돌발 교체·수리 시점 사용량 < interval_value × 50%
    (사용량 = 직전 교체 이후 run_logs 증가분, months 기준이면 경과 개월)
  - 반복고장: 같은 설비·같은 파트 돌발고장이 90일 내 재발
  - 예비품 부족: 교체 후 stock_qty가 safety_stock 이하, 또는 30일 내 도래 수량보다 적음
- 실제 등록 시 action_type='교체'이면 stock_qty 1 차감. 이력 추가와 재고 차감은 하나의 트랜잭션

[F3 조회] query.py
- --format table 가독성 개선, 결과 행 수 표시, 기본 LIMIT 200

[F4 교체 도래 점검] due_check.py
- 기준일: 최근 run_logs 일자
- 설비×파트별 직전 교체 이후 사용량, 남은 양, 일평균 사용량으로 예상 도래일 계산
- equipment / unit / days 필터, 상태: 초과 / N일 이내 / 여유
- 결과에 "교체주기·단가는 데모용 가정값" 문구 포함
- --save 시 reports/due_YYYYMMDD.csv (UTF-8 BOM, 엑셀 한글 깨짐 방지)

[F5 고장 패턴 분석] analyze.py
- months(기본 6), equipment 필터
- 설비별·유닛별·파트별 돌발고장 건수, 반복고장 목록, 조기고장 목록, 월별 예방보전 비율, 수리비 합계
- 결과에 "findings": [{문제, 추정 원인, 권장 조치, 확인 방법}] 형태의 규칙 기반 해석 포함
  (예: TS 유압 계통 반복 → 추정 원인: 작동유 오염/필터 막힘 → 권장: 필터 교체·작동유 분석 → 확인: 압력 측정)
- --save 시 reports/analysis_YYYYMMDD.json

[F6 샘플 DB 재생성] init_db.py
- 1단계 안전장치 유지 (--yes 필수, 운영 DB 거부)

[테스트]
- 설비 호칭 변형 10개 이상, 범위 밖 설비, 동의어 전부, 베어링 분류 규칙
- dry-run이 DB를 바꾸지 않는지, 조기/반복/예비품 부족 각각 발생하는 케이스, 등록 실패 시 재고 롤백
- due_check 필터 조합, analyze findings 존재
- tests/fixtures/phrases.json에 현장 표현 40개 + 정답 파트ID를 만들고 매핑 정확도(목표 95%) 출력
- DATABASE_URL로 PostgreSQL을 지정하면 같은 테스트가 PostgreSQL에서도 돌도록 구성 (없으면 skip)

[완료 조건]
- pytest 전부 통과, 매핑 정확도 수치 보고
- CLAUDE.md의 명령과 옵션을 실제 구현에 맞게 갱신
- PRD F1~F6 각각 "구현 위치 / 테스트 이름"을 표로 정리해줘
```

---

## 3단계 — UI 디자인 (Streamlit)

```
prd.md, CLAUDE.md와 1·2단계 코드를 읽고, Streamlit 멀티페이지 앱 화면을 완성해줘.
페이지는 새 로직을 만들지 말고 반드시 scripts/의 함수(normalize, log_repair, due_check, analyze, query)를 호출한다.
DB 직접 쓰기 금지와 "미리보기 → 확인 → 등록" 규칙은 화면에도 똑같이 적용된다.

[구성]
- streamlit_app.py: st.set_page_config(layout="wide", page_title="CNC 보전관리"), st.navigation으로 페이지 등록
- app_pages/ 의 5개 페이지, 공통 UI 조각은 app_pages/_components.py
- 차트는 Streamlit 기본 차트 또는 Altair (추가 의존성 최소화)
- 조회 결과는 @st.cache_data(ttl=60), 등록 성공 시 st.cache_data.clear()

[화면]
1. 대시보드
   - st.metric 4개: 교체 초과 건수, 30일 내 도래 건수, 이번 달 돌발고장 건수, 예방보전 비율(목표 70% 대비)
   - 설비 12대 현황 그리드 (CNC-01~12, 도래/초과 건수로 상태 표시), 설비 선택 시 설비 상세로 이동
   - 설비 상세: 구조부 10개 탭(또는 확장 패널)마다 사양 3개, 그 구조부에 장착된 파트의 도래 상태와 최근 이력
2. 이력 등록
   - 자연어 입력(st.text_input) → 해석 결과(설비·파트·조치·돌발·날짜)를 수정 가능한 st.form으로 표시
   - 파트 후보가 여러 개면 st.radio로 선택, 0개면 "파트를 찾지 못했습니다" + 유닛→파트 선택
   - [미리보기] = dry-run 결과를 st.dataframe으로 표시하고 결과를 st.session_state에 보관
   - [등록] 버튼은 미리보기가 있을 때만 활성화. 등록 직전 "등록할까요?" 확인(st.dialog)
   - 미리보기 후 입력값이 바뀌면 미리보기를 무효화하고 다시 미리보기를 요구 (다른 내용이 등록되는 것 방지)
   - 등록 버튼 연타로 중복 등록되지 않게 처리
   - info 경고(조기고장/반복고장/예비품 부족)는 st.warning / st.error로 눈에 띄게 강조
3. 교체 도래
   - 설비·유닛·기간(7/30/90일) 필터, 상태별 색(초과=빨강, 임박=주황, 여유=초록), st.download_button으로 CSV 저장
   - 상단 st.info: "교체주기·단가는 데모용 가정값 — 실제 기준은 제조사 매뉴얼·사내 보전기준"
4. 고장 분석
   - 기간·설비 필터
   - findings를 st.container(border=True) 카드로: 문제 → 추정 원인("추정" 표시) → 권장 조치 → 확인 방법
   - 유닛별 돌발고장 막대 차트, 월별 예방보전 비율 선 차트(70% 목표선)
5. 이력 조회
   - 설비·파트·기간·돌발 여부 필터, st.dataframe (정렬·검색), 최근 등록 순

[디자인 기준]
- 공장 현장 태블릿 사용 가정: 글자 16px 이상, 버튼은 use_container_width=True로 크게
- .streamlit/config.toml에 테마 지정 (primaryColor 등), 라이트/다크 모두 읽기 좋게
- 색은 상태 의미로만 사용
- 로딩(st.spinner), 오류(st.error + 해결 방법), 빈 결과(st.info) 상태를 모두 처리
- Playwright 검증을 위해 모든 입력·버튼·주요 컨테이너에 고유 key 부여
  (예: key="nl_input", "preview_btn", "register_btn", "info_banner", "due_table", "finding_card_0")
  → Streamlit이 .st-key-<key> 클래스를 붙이므로 4단계에서 선택자로 사용

[완료 조건]
- streamlit run streamlit_app.py 후 5개 화면이 모두 열리고 실제 DB 데이터가 표시됨
- streamlit.testing.v1.AppTest로 페이지별 기본 동작 테스트 추가, 기존 테스트 포함 전부 통과
- README.md에 로컬 실행 방법 정리
- 화면별 주요 기능을 표로 정리해줘
```

---

## 4단계 — PRD 대비 검토 및 버그 점검 (Playwright)

```
prd.md를 기준으로 1~3단계 결과물이 PRD대로 개발됐는지, 버그가 없는지 자세히 검토해줘.
Playwright로 실제 브라우저에서 Streamlit 앱을 조작해 확인한다.
검토 중 코드는 고치지 말고, 먼저 보고서를 만든 뒤 수정 여부를 나에게 물어봐.

[준비]
- 로컬 SQLite만 사용 (DATABASE_URL이 운영 DB를 가리키면 중단)
- db/maintenance.db를 db/maintenance.backup.db로 백업 후 python scripts/init_db.py --yes
- streamlit run streamlit_app.py --server.headless true --server.port 8501 을 백그라운드 실행
- pytest 전체 실행 결과 먼저 기록

[Streamlit + Playwright 주의]
- 선택자는 .st-key-<key> 클래스와 텍스트 우선
- 조작 후 재실행(rerun)이 끝날 때까지 기다린다: [data-testid="stStatusWidget"]가 사라질 때까지 대기
- 페이지 이동은 사이드바 링크 클릭 또는 URL 직접 접근 둘 다 확인

[A. PRD 요구사항 추적 검토]
prd.md의 모든 요구사항을 항목별로 뽑아 "충족 / 부분 충족 / 미충족"으로 판정하고 근거(파일:줄, 화면, 테스트)를 적어라.
- 3장: 설비 12대, 유닛 6개, 파트 39개와 파트ID 범위, 베어링 분류 규칙, 제외 범위 침범 여부,
  구조부 10개와 파트별 장착 위치가 표와 일치하는지
- 5장: 구조부 사양 테이블 10개의 테이블명·컬럼명·단위가 표와 일치하는지
- 4장: F1~F6 세부 항목 전부
- 5장: 스크립트 옵션이 PRD 표와 일치하는지, query.py 읽기전용, log_repair.py 단일 쓰기 경로, 페이지가 DB에 직접 쓰지 않는지
- 6장: 행동 규칙 8개 (승인 없는 쓰기, 추측 금지, 가정값 고지, init_db 이중 확인)
- 7장: 판정 기준 4개가 정확한 수치(50%, 90일, 안전재고 1개, 30일)로 구현됐는지, 성공 지표 5개 측정 가능 여부
- 7장 배포와 운영: DATABASE_URL 전환, secrets 사용, init_db 운영 DB 거부, 마이그레이션 구조, .gitignore
- CLAUDE.md가 PRD·실제 코드와 어긋나는 곳이 없는지

[B. Playwright E2E 시나리오] tests/e2e/ 에 스크립트로 남기고 실행
1. 대시보드: 지표 4개와 설비 12대 그리드 표시, 수치가 scripts 함수 결과와 일치
2. 이력 등록 정상 흐름: "3번기 주축 베어링 소음나서 교체" → CNC-03 / BR-01·BR-02 후보 / 교체 / 돌발
   → 미리보기 → 확인 → 등록 → DB에 1건 추가, 재고 1 차감
3. 승인 없는 쓰기 차단: 미리보기 없이 등록 불가, 확인에서 취소 시 DB 변화 없음,
   미리보기 후 설비/파트를 바꾸고 바로 등록 시 막히는지, 등록 버튼 연타 시 1건만 등록되는지
4. 모호한 입력: "벨트 갈았어"(설비 없음) → 되묻기, "13호기 척 교체" → 범위 밖 오류, 없는 파트 → 후보 제시
5. 동의어: 죠, 공구대, 라이브센터, 솔밸브, 앱솔 배터리, 웨이오일, MC 각각 올바른 파트로 해석
6. info 경고: 조기고장·반복고장·예비품 부족 케이스를 각각 만들어 경고가 뜨는지
7. 교체 도래: 필터 조합, 상태 색, 가정값 고지 문구, CSV 다운로드 파일 내용과 한글 인코딩
8. 고장 분석: 기간 필터, findings 카드의 문제/추정 원인/권장 조치/확인 방법과 "추정" 표시, 차트 렌더링
9. 이력 조회: 필터, 방금 등록한 건이 캐시 때문에 안 보이는 문제가 없는지
10. 반응형: 1280px / 768px / 375px 스크린샷, 가로 스크롤, 글자 크기, 다크 테마
11. 오류 상황: DB 연결 실패(잘못된 DATABASE_URL), 빈 결과, 잘못된 날짜 입력 시 화면 처리,
    Streamlit 예외 화면(빨간 traceback)이 사용자에게 노출되는지, 브라우저 콘솔 에러 수집

[C. 코드·버그 검토]
- SQL 인젝션: query.py 우회(세미콜론 다중문, PRAGMA, ATTACH, 주석), 필터 입력값이 SQL에 직접 들어가는지
- 트랜잭션: 등록 중 오류 시 재고만 차감되는 등 부분 반영이 없는지
- 날짜 경계: 월말, 윤년, 가동로그 없는 설비, 교체 이력이 없는 파트
- 계산 검증: 조기고장·도래일 계산을 샘플 3건 이상 손으로 계산해 결과와 대조
- Streamlit 특유 문제: session_state 초기화 누락, 캐시 무효화 누락, 재실행 시 중복 실행되는 쓰기
- 이식성: SQLite 전용 SQL 사용 여부 (PostgreSQL에서 깨질 부분)
- 비밀값: secrets.toml이나 접속 문자열이 코드·Git에 들어가 있지 않은지

[보고서] reviews/review_YYYYMMDD.md 로 저장
1. 요약: 충족률(충족 항목 수 / 전체), 치명·높음·중간·낮음 건수
2. PRD 추적 표: 요구사항 | 판정 | 근거
3. 버그 목록: 심각도 | 재현 절차 | 기대 결과 | 실제 결과 | 원인 추정 | 수정 제안 | 스크린샷 경로
4. E2E 결과 표: 시나리오 | 통과/실패 | 비고
5. 성공 지표 측정값 (매핑 정확도, 베어링 규칙 준수율, 승인 없는 쓰기 건수, 등록 소요 시간, 예방보전 비율)
6. 수정 우선순위 제안

[마무리]
- 검토가 끝나면 Streamlit 서버를 종료하고 DB를 백업본으로 복원
- 보고서 요약을 보여주고 "어떤 항목부터 수정할까요?"라고 물어봐
```

---

## 5단계 — 배포와 지속 운영

```
prd.md 7장 "배포와 운영"과 CLAUDE.md를 읽고, 4단계 수정까지 끝난 앱을 Streamlit Community Cloud에 배포하고
계속 운영할 수 있는 체계를 만들어줘. 외부 서비스 계정 생성·비밀값 입력·배포 버튼처럼 내가 직접 해야 하는 일은
단계별 안내로 정리해 주고, 내 확인 없이 push하거나 운영 DB에 쓰지 마.

[1. 저장소 준비]
- git 초기화, .gitignore 점검 (db/*.db, reports/, reviews/ 스크린샷, .streamlit/secrets.toml, __pycache__, .venv)
- requirements.txt 버전 고정 (streamlit, sqlalchemy, psycopg[binary] 등), runtime 파이썬 버전 명시
- README.md: 로컬 실행, 테스트, 배포, 운영 절차
- 내가 만든 GitHub 저장소에 push하는 명령 안내 (push는 내가 승인한 뒤)

[2. 운영 DB]
- 외부 PostgreSQL(Supabase 또는 Neon 무료 플랜 기준) 연결 절차 안내
- scripts/migrate.py: migrations/를 순서대로 적용, schema_version으로 중복 적용 방지, 적용 전 --dry-run
- scripts/seed_master.py: 운영 DB에 설비 12대·파트 39개 마스터만 넣기 (샘플 이력 제외), 이미 있으면 건너뜀
- scripts/backup.py: 운영 DB를 CSV/SQL로 내보내기, 마이그레이션 전 필수 실행
- 운영 DB에서 init_db.py가 거부되는지 다시 확인

[3. Streamlit Community Cloud 배포]
- 진입점 streamlit_app.py, 파이썬 버전, Secrets 입력 형식 예시(.streamlit/secrets.toml.example과 동일):
  [database]
  url = "postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME"
- 앱 비공개 설정과 접속 허용 사용자(이메일) 등록 방법 안내
- 배포 후 확인 목록: 5개 화면 동작, 운영 DB 연결, 등록 1건 테스트 후 삭제 방법(마이그레이션 아닌 관리용 스크립트로)

[4. CI (GitHub Actions)]
- .github/workflows/ci.yml: push·PR마다 pytest (SQLite) + PostgreSQL 서비스 컨테이너로 같은 테스트
- 실패 시 main 병합을 막도록 브랜치 보호 설정 방법 안내
- 선택: Playwright E2E를 수동 실행(workflow_dispatch) 작업으로 추가

[5. 지속 운영 절차] docs/operations.md
- 배포 흐름: 기능 브랜치 → PR → CI 통과 → main 병합 → 자동 재배포
- 스키마 변경 절차: 마이그레이션 추가 → 로컬·CI 검증 → 운영 백업 → migrate.py 적용
- 기준값 변경 절차: 교체주기·단가를 실제 제조사/사내 기준으로 바꾸는 방법 (데모 가정값 교체)
- 별칭 보강 절차: 오매핑 사례 수집 → parts.aliases 추가 → phrases.json에 테스트 추가
- 월간 점검: 성공 지표 5개 측정 방법과 기록 위치, 백업 주기, 의존성 업데이트
- 장애 대응: 앱이 안 뜰 때(로그 확인 위치), DB 연결 실패, 잘못 등록된 이력 정정 방법

[완료 조건]
- 로컬에서 DATABASE_URL을 PostgreSQL로 바꿔 앱과 pytest가 동작
- CI 워크플로 파일과 운영 문서 작성 완료
- CLAUDE.md에 배포·운영 명령 반영
- 내가 직접 해야 할 일을 순서대로 체크리스트로 정리해줘
```
