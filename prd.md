# CNC 선반 보전관리 에이전트 PRD

작성일: 2026-09-29

## 1. 개요

현장 작업자와 보전 엔지니어가 한국어 현장 용어로 말하면, CNC 선반의 수리 이력을 등록·조회하고 교체 도래와 고장 패턴을 알려주는 대화형 보전관리 에이전트를 만든다.

### 배경과 문제

- 수리 이력이 작업자마다 다른 표현("3번기 죠 교체", "공구대 클램프 누유")으로 남아 집계와 검색이 어렵다.
- 파트별 교체주기(가동시간, 클램핑 횟수, 인덱싱 횟수, 개월)를 사람이 따로 계산해야 해서 예방보전 시점을 놓친다.
- 돌발고장과 예방작업이 섞여 기록되어 반복고장, 조기고장을 찾아내기 어렵다.

### 목표

1. 자연어 한 문장으로 표준화된 수리 이력(설비·파트ID·조치 유형·돌발 여부)을 등록한다.
2. 교체 도래 파트를 설비·유닛별로 미리 알려 예방보전 계획을 세우게 한다.
3. 고장 이력을 분석해 "문제 → 추정 원인 → 권장 조치" 형태로 해석해 준다.
4. DB 쓰기는 사용자 승인 없이 일어나지 않게 해 데이터 신뢰성을 지킨다.

## 2. 사용자와 사용 시나리오

사용자는 두 부류이며, 에이전트는 모두에게 한국어 현장 용어로 답한다.

| 사용자 | 주요 니즈 | 대표 요청 |
| --- | --- | --- |
| 생산관리/설비보전 엔지니어 | 교체 계획, 고장 경향 파악, 예비품 관리 | "다음 달 교체 도래 파트 뽑아줘", "최근 6개월 고장 패턴 분석해줘" |
| 현장 작업자 | 조치 내용을 빠르게 기록, 이전 이력 확인 | "3호기 죠 교체했어", "5번기 터렛 전에도 고장났어?" |

### 핵심 시나리오

1. **이력 등록** — 작업자: "3번기 주축 베어링 소음 나서 전면 교체했어". 에이전트는 CNC-03, BR-01(베어링 분류 규칙), 교체, 돌발로 해석하고 `--dry-run` 결과를 표로 보여준 뒤 승인을 받아 등록한다.
2. **교체 도래 점검** — 엔지니어: "30일 내 교체 도래 부품 알려줘". 에이전트는 `due_check.py --days 30`을 실행하고, 주기가 데모용 가정값임을 밝힌다.
3. **고장 패턴 분석** — 엔지니어: "최근 6개월 심압대 고장 분석해줘". 에이전트는 `analyze.py --months 6`의 결과를 문제 → 추정 원인 → 권장 조치와 확인 방법으로 해석한다.
4. **모호한 요청** — 작업자: "벨트 갈았어". 설비가 빠진 경우 추측하지 않고 설비와 후보 파트(HS-04 스핀들 구동벨트 등)를 제시해 되묻는다.

## 3. 범위

관리 대상은 CNC 선반 12대(CNC-01 ~ CNC-12)의 6개 유닛, 39개 파트이며 파트ID는 `유닛코드-순번` 형식이다.

| 코드 | 유닛 | 포함 범위 | 파트ID |
| --- | --- | --- | --- |
| HS | 주축대 | 유압척, 척 조, 척 로터리 실린더, 스핀들 구동벨트, 인코더 | HS-01 ~ HS-05 |
| TS | 심압대 | 유압유니트(작동유, 필터, 펌프, 솔밸브, 압력스위치), 클램프 실린더, 회전센터 | TS-01 ~ TS-07 |
| SD | 새들 | 터렛(커플링, 클램프 씰, 인덱싱 모터), X/Z 볼스크류, 와이퍼, 서보축 커플링 | SD-01 ~ SD-07 |
| BR | 베어링류 | 스핀들 전·후면, X/Z 서포트, X/Z LM가이드 블록, 터렛 베어링 | BR-01 ~ BR-07 |
| LB | 윤활라인 | 습동유, 윤활 필터, 집중윤활 펌프, 분배기, 배관/호스, 오일쿨러 필터 | LB-01 ~ LB-06 |
| EL | 전기판넬 | APC·CNC 백업 배터리, 판넬 쿨러 필터, 냉각팬, 서보/스핀들 앰프, MC | EL-01 ~ EL-07 |

**베어링 분류 규칙**: 베어링은 장착 위치와 무관하게 항상 BR 유닛으로 기록한다. "주축 베어링 교체"는 HS가 아니라 BR-01/BR-02다.

### 포함

- 수리·예방작업 이력 등록과 조회
- 교체 기준(가동시간, 클램핑 횟수, 인덱싱 횟수, 개월) 기반 도래 점검
- 고장 패턴 분석과 해석, 예비품 부족 알림

### 제외

- 설비 제어나 NC 프로그램 수정 등 기계에 직접 명령하는 기능
- 실시간 센서 연동(진동·온도 모니터링)
- 구매·발주 처리, DB 스키마 변경

### 구조부 (설비 구조도 기준)

파트가 장착된 위치는 CNC 선반 구조도의 10개 구조부로 따로 기록한다. 유닛은 "무엇을 관리하나", 구조부는 "어디에 달려 있나"다. 그래서 베어링은 유닛이 항상 BR이고, 위치는 구조부로 구분한다.

| 코드 | 구조부 | 역할 | 장착 파트 |
| --- | --- | --- | --- |
| GBX | 기어박스 | 주축 변속·감속 | (현재 없음) |
| HDS | 주축대 | 주축·척 회전 | HS 전체, BR 스핀들 전·후면, LB 오일쿨러 필터 |
| CTL | 제어장치 | 전기 제어반: 전원·앰프·접촉기 | EL 판넬 쿨러 필터·냉각팬·서보/스핀들 앰프·MC |
| TUR | 공구대 | 터렛·공구 인덱싱 | SD 터렛 커플링·클램프 씰·인덱싱 모터, BR 터렛 베어링 |
| XSL | 이송대 | X축 이송 | SD X 볼스크류·서보축 커플링, BR X 서포트·X LM가이드 블록 |
| CAR | 왕복대 | Z축 이송 | SD Z 볼스크류·와이퍼, BR Z 서포트·Z LM가이드 블록 |
| TLS | 심압대 | 긴 공작물 지지 | TS 전체 |
| NCU | NC장치 | CNC 컨트롤러 | EL APC·CNC 백업 배터리 |
| BED | 베드 | 본체·습동면, 윤활 유니트 | LB 습동유·윤활 필터·집중윤활 펌프·분배기·배관/호스 |
| OPP | 운전조작반 | 화면·스위치·MPG | (현재 없음) |

- 이송계 파트는 축 기준으로 배정한다: X축 → 이송대, Z축 → 왕복대. 서보축 커플링은 X/Z 공용 파트 1개라 대표 위치를 이송대로 둔다.
- 제어장치(전기 제어반)와 NC장치(컨트롤러)의 구분, 윤활 유니트의 베드 장착, 오일쿨러의 주축대 배정은 일반적인 구조를 가정한 것이다.

## 4. 기능 요구사항

MVP는 F1~F5 다섯 기능이며, 모두 기존 `scripts/` 스크립트 호출로 동작한다.

### F1. 현장 용어 해석 (P0)

- 설비 호칭 정규화: "3호기", "3번기", "03번" → `CNC-03`
- 파트 호칭은 `parts.aliases`에서 조회한다. 모르는 표현은 등록 전에 반드시 `query.py`로 후보를 찾는다.
  - 예: `python scripts/query.py "SELECT part_id, part_name, aliases FROM parts WHERE aliases LIKE '%키워드%'"`
- 기본 동의어: 죠=조=jaw, 공구대=터렛, 라이브센터=회전센터, 솔밸브=솔레노이드 밸브, 앱솔 배터리=APC 배터리, 웨이오일=습동유, MC=마그네트 접촉기
- 조치 유형은 6가지로만 분류: 교체 / 수리 / 조정 / 청소 / 점검 / 보충
- 돌발고장 판단: 알람, 정지, 파손, 누유, 불량 등 예정에 없던 대응이면 `--breakdown`. "주기 도래", "PM", "예방", "정기"는 예방(계획) 작업.

### F2. 수리 이력 등록 (P0)

- 자연어 입력을 설비·파트ID·조치 유형·돌발 여부·날짜로 변환한다. 날짜가 없으면 오늘.
- `log_repair.py --dry-run` 결과를 표로 보여주고 "등록할까요?" 승인 후에만 실제 등록한다.
- 결과의 `info`(조기고장, 반복고장, 예비품 부족)는 눈에 띄게 강조해 전달한다.

### F3. 이력·마스터 조회 (P0)

- "5번기 터렛 이력", "심압대 필터 단가" 같은 질문을 읽기전용 SELECT문으로 변환해 `query.py`로 조회한다.
- 필요 시 `query.py --schema`로 스키마를 먼저 확인한다.

### F4. 교체 도래 점검 (P0)

- `due_check.py`를 설비(`--equipment`)·유닛(`--unit`)·기간(`--days N`)으로 걸러 실행한다. 기준일은 최근 가동로그일.
- 교체 기준(basis)은 `run_hours` / `clamp_count` / `index_count` / `months` 4종이다.
- 답변마다 `interval_value`와 단가가 **데모용 가정값**이며 실제 기준은 제조사 매뉴얼·사내 보전기준을 따라야 한다고 안내한다.
- `--save`로 결과를 저장할 수 있다.

### F5. 고장 패턴 분석 (P0)

- `analyze.py --months N [--equipment]`를 실행하고 표를 나열하지 않는다.
- **무엇이 문제인지 → 추정 원인 → 권장 조치** 순으로 해석하고, 원인은 "추정"임을 밝힌다.
- 확인 방법(압력 측정, 진동 측정, 배관 점검 등)을 함께 제시한다.

### F6. 샘플 DB 재생성 (P2)

- `init_db.py`는 기존 DB를 삭제하므로 사용자의 명시적 확인 후에만 실행한다.

## 5. 데이터 모델과 스크립트 인터페이스

데이터는 로컬 개발 시 `db/maintenance.db`(SQLite), 운영(배포) 시 외부 PostgreSQL에 둔다. 접속 대상은 `DATABASE_URL` 하나로 전환하고, 에이전트와 Streamlit 앱은 모두 `scripts/`의 Python 함수로만 접근한다. 아래 테이블 구성은 초안에서 유추한 제안이며 구현 시 확정한다.

### 테이블 (제안)

| 테이블 | 역할 | 주요 컬럼 |
| --- | --- | --- |
| `equipment` | 설비 마스터 | equipment_id(CNC-01 ~ CNC-12), 설비명, 설치일 |
| `parts` | 파트 마스터 | part_id, unit, part_name, aliases, basis, interval_value, 단가, 예비품 재고 |
| `repair_logs` | 수리·예방작업 이력 | 일자, equipment_id, part_id, 조치 유형(6종), breakdown 여부, 내용 |
| `run_logs` | 가동로그 | 일자, equipment_id, run_hours, clamp_count, index_count |

구조부는 마스터 테이블 `assemblies`(assembly_code, name, description, sort_order)에 두고, `parts.assembly_code`(FK)로 각 파트의 장착 위치를 가리킨다.

### 구조부 사양 테이블

설비 12대마다 구조부별 사양을 1행씩 기록한다. 각 테이블은 `equipment_id`(PK·FK)와 `updated_at` 외에 사양 컬럼 3개를 가진다. 컬럼은 CNC 선반 제조사 사양표 항목에서 골랐고, 예시값은 8인치 척급 45° 슬랜트 베드 선반의 공개 사양이다. 샘플 데이터는 데모용 가정값이다.

| 구조부 | 테이블 | 컬럼 1 | 컬럼 2 | 컬럼 3 |
| --- | --- | --- | --- | --- |
| 기어박스 | `spec_gearbox` | gear_ranges 변속 단수(단) — 예: 2 | gear_oil_grade 기어오일 점도등급 — 예: ISO VG 68 | gear_oil_capacity_l 기어오일 용량(L) — 예: 5 |
| 주축대 | `spec_headstock` | spindle_max_rpm 최고 회전수(rpm) — 예: 4,000 | spindle_nose 주축단 규격 — 예: A2-6 | spindle_motor_kw 주축 모터 출력(kW) — 예: 18.5 |
| 제어장치 | `spec_control_cabinet` | power_capacity_kva 전원 용량(kVA) — 예: 23 | supply_voltage_v 전원 전압(V, 3상) — 예: 220 | rated_current_a 정격 전류(A) — 예: 60 |
| 공구대 | `spec_turret` | tool_stations 공구 스테이션 수 — 예: 12 | index_time_sec 인덱싱 시간(s) — 예: 0.12 | tool_shank_mm 공구 섕크(mm) — 예: 25 |
| 이송대 | `spec_cross_slide` | x_travel_mm X축 이동량(mm) — 예: 215 | x_rapid_m_min X축 급이송(m/min) — 예: 24 | x_ballscrew_dia_mm X축 볼스크류 직경(mm) — 예: 32 |
| 왕복대 | `spec_carriage` | z_travel_mm Z축 이동량(mm) — 예: 580 | z_rapid_m_min Z축 급이송(m/min) — 예: 30 | z_ballscrew_dia_mm Z축 볼스크류 직경(mm) — 예: 40 |
| 심압대 | `spec_tailstock` | quill_dia_mm 퀼 직경(mm) — 예: 65 | quill_stroke_mm 퀼 스트로크(mm) — 예: 80 | quill_taper 퀼 테이퍼 — 예: MT4 |
| NC장치 | `spec_nc_unit` | controller_model 컨트롤러 모델 — 예: FANUC 0i-TF Plus | controlled_axes 제어 축 수 — 예: 2 | usb_max_gb USB 메모리 최대 용량(GB) — 예: 32 |
| 베드 | `spec_bed` | slant_angle_deg 경사각(°, 평베드 0) — 예: 45 | guideway_type 습동면 방식(LM가이드/박스웨이) — 예: 박스웨이 | swing_over_bed_mm 베드 위 스윙(mm) — 예: 550 |
| 운전조작반 | `spec_operator_panel` | display_size_inch 화면 크기(inch) — 예: 15 | is_touchscreen 터치스크린 여부 — 예: 예 | has_mpg MPG(수동 펄스 발생기) 유무 — 예: 예 |

### 스크립트

| 목적 | 명령 | DB 접근 |
| --- | --- | --- |
| 스키마 확인 | `python scripts/query.py --schema` | 읽기 |
| 조회 | `python scripts/query.py "<SELECT문>"` | 읽기 전용 (SELECT 외 거부) |
| 이력 등록 | `python scripts/log_repair.py ... [--dry-run]` | 쓰기 (유일한 쓰기 경로) |
| 교체 도래 점검 | `python scripts/due_check.py [--equipment] [--unit] [--days N] [--save]` | 읽기 |
| 고장 패턴 분석 | `python scripts/analyze.py [--months N] [--equipment] [--save]` | 읽기 |
| 샘플 DB 재생성 | `python scripts/init_db.py` | 삭제 후 재생성 (확인 필수) |

### `log_repair.py` 출력 요구사항

- `--dry-run` 시 DB를 바꾸지 않고 등록될 행을 돌려준다.
- `info` 필드에 조기고장(교체주기 대비 조기 교체), 반복고장(동일 설비·파트 재발), 예비품 부족 경고를 담는다.
- 존재하지 않는 equipment_id·part_id는 오류로 거부한다.

## 6. 에이전트 행동 규칙과 안전장치

핵심 원칙은 "승인 없는 쓰기 금지, 추측 금지"다.

1. **DB 쓰기 전 반드시 확인받는다.** 이력 등록은 항상 `--dry-run` 결과를 표로 보여주고 "등록할까요?"에 승인받은 뒤 실행한다.
2. **추측하지 않는다.** 설비·파트를 특정할 수 없으면 후보를 제시해 되묻는다. 존재하지 않는 파트ID를 만들지 않는다.
3. **정해진 경로만 쓴다.** `sqlite3`로 DB를 직접 수정하거나 스키마를 바꾸지 않는다. 조회는 `query.py`, 쓰기는 `log_repair.py`만 사용한다.
4. **경고는 강조한다.** `log_repair.py`의 `info`(조기고장, 반복고장, 예비품 부족)는 반드시 강조해 전달한다.
5. **해석해서 전한다.** 분석 결과는 문제 → 추정 원인 → 권장 조치 순으로, 확인 방법과 함께 제시한다.
6. **날짜 기본값을 지킨다.** 날짜가 없으면 등록은 오늘, 점검·분석은 최근 가동로그일 기준이다.
7. **가정값을 밝힌다.** 교체주기·단가는 데모용 가정값임을 매번 알린다.
8. **파괴적 작업은 이중 확인한다.** `init_db.py`는 기존 DB 삭제 사실을 알리고 명시적 동의를 받는다.

### 이력 등록 흐름

1. 자연어 입력 수신
2. 설비 호칭 정규화, 파트 별칭 조회(`query.py`) — 특정 불가 시 후보 제시 후 되묻기
3. 조치 유형·돌발 여부·날짜 결정
4. `log_repair.py --dry-run` 실행, 결과를 표로 제시
5. "등록할까요?" — 거절 시 수정 내용 반영 후 4단계로
6. 승인 시 실제 등록, `info` 경고 강조 전달

## 7. 비기능 요구사항, 성공 지표, 마일스톤, 리스크

### 비기능 요구사항

- 언어: 모든 응답과 화면은 한국어, 현장 용어 유지
- 데이터 무결성: 쓰기는 `log_repair.py` 단일 경로, 승인 후에만 실행 (Streamlit 화면도 동일)
- 실행 환경: Python + Streamlit. 로컬은 SQLite, 운영은 외부 PostgreSQL
- 추적성: 에이전트가 실행한 명령을 사용자가 확인할 수 있어야 함

### 배포와 운영

화면은 Streamlit 멀티페이지 앱으로 만들고, GitHub 저장소와 연동해 배포한 뒤 계속 운영한다.

- 배포 대상: Streamlit Community Cloud (기본안). `main` 브랜치 push 시 자동 재배포
- 운영 DB: 앱 서버 파일은 재시작·재배포 때 초기화되므로 SQLite 파일을 운영에 쓰지 않는다. 외부 PostgreSQL(예: Supabase, Neon)에 둔다
- 비밀값: DB 접속 정보는 `st.secrets`(로컬 `.streamlit/secrets.toml`, Git 제외)
- 접근 제한: 앱 비공개 설정 + 허용된 사용자만 접속
- 품질 관리: GitHub Actions에서 push마다 pytest 실행, 실패 시 배포 전 수정
- 스키마 변경: 버전 번호가 붙은 마이그레이션 스크립트로만 수행, 운영 DB는 적용 전 백업
- `init_db.py`: 운영 DB 대상 실행은 차단 (로컬·테스트 전용)

### 성공 지표

| 지표 | 목표 | 측정 방법 |
| --- | --- | --- |
| 자연어 → 파트ID 매핑 정확도 | 95% 이상 | 현장 표현 테스트셋 기준 정답률 |
| 베어링 분류 규칙 준수율 | 100% | 베어링 관련 입력 중 BR로 기록된 비율 |
| 승인 없는 쓰기 건수 | 0건 | 실행 로그 중 승인 없이 실행된 `log_repair.py` 건수 |
| 이력 등록 소요 시간 | 1분 이내 | 입력부터 등록 완료까지 |
| 예방보전 비율 | 70% 이상 | 전체 작업 중 예방(비돌발) 작업 비율, 월별 추이 |

### 마일스톤

1. **M1 데이터 기반** — 스키마 확정, `init_db.py` 샘플 DB, `query.py`, SQLite/PostgreSQL 공용 DB 계층
2. **M2 등록** — `log_repair.py`(dry-run, info 경고), 용어 해석 규칙
3. **M3 점검·분석** — `due_check.py`, `analyze.py`
4. **M4 Streamlit 화면** — 대시보드, 이력 등록, 교체 도래, 고장 분석, 이력 조회
5. **M5 검토** — PRD 대비 검토, Playwright E2E
6. **M6 배포** — GitHub 연동, 운영 DB 이관, CI, Community Cloud 배포

### 리스크

- 교체주기·단가가 데모용 가정값 → 실제 운영 전 제조사 매뉴얼·사내 보전기준으로 교체 필요
- 등록되지 않은 현장 표현 → 오매핑 위험. `aliases` 지속 보강 필요
- 가동로그 누락 → 도래 점검 결과 부정확
- 추정 원인을 확정으로 오해 → "추정" 표기와 확인 방법 제시로 완화
- 배포 환경에서 SQLite를 쓰면 재시작 시 이력 유실 → 운영은 외부 PostgreSQL만 허용
- SQLite와 PostgreSQL의 SQL 차이(날짜 함수 등) → 두 DB 모두에서 테스트
- 공개 URL 노출 → 비공개 앱 설정과 허용 사용자 관리

### 판정 기준

설비 대수는 12대로 확정했고, 나머지는 업계에서 흔히 쓰는 기준을 기본값으로 둔다. 사내 기준이 정해지면 바꾼다.

| 항목 | 기준 |
| --- | --- |
| 관리 대상 설비 | CNC-01 ~ CNC-12 (12대). 범위 밖 번호("13호기" 등)는 등록하지 않고 되묻는다. |
| 조기고장 | 돌발 교체·수리 시점의 누적 사용량이 교체주기(`interval_value`)의 50% 미만 |
| 반복고장 | 같은 설비·같은 파트에서 돌발고장이 90일 안에 다시 발생 |
| 예비품 부족 | 재고가 안전재고(기본 1개) 이하, 또는 30일 안에 교체 도래하는 수량보다 적음 |

### 미결 사항

- [ ] 실제 DB 스키마와 컬럼명 확정 (안전재고 컬럼 포함)
- [ ] 운영 PostgreSQL 제공자 선택 (Supabase / Neon / 사내 서버)
- [ ] 배포 대상 확정 (Community Cloud 외 사내 서버 필요 여부)
- [ ] 접속 허용 사용자와 권한(조회 전용 / 등록 가능) 구분
- [ ] 기어박스·운전조작반 소모품 파트 추가 여부 (기어오일, MPG 등 — 현재 39개 파트에 없음)
- [ ] 제어장치/NC장치 구분과 윤활 유니트·오일쿨러 장착 위치를 실제 설비 기준으로 확인
- [ ] 설비 12대의 실제 사양값 입력 (제조사 사양서 기준)

## 출처

- 구조부 명칭: 사용자 제공 이미지 "CNC 선반 구조 및 각부 명칭" (`image.png`)
- [Hyundai WIA HD2200 사양 (Hillary Machinery)](https://hillaryllc.com/en/equipment/6819110-hyundai-wia-hd2200-2-axis-cnc-lathes) — 주축, 터렛, X/Z축, 심압대, 전원 항목과 예시값
- [DN Solutions LYNX 2100 사양 (MachineToolIndex)](https://machinetoolindex.com/machines/dn-solutions-lynx-2100) — 컨트롤러·터치스크린 화면
- [Understand spindle speed limiting on turning centers (CNCCI)](https://www.cncci.com/post/understand-spindle-speed-limiting-on-turning-centers) — 주축 변속 단수
- [Lubrication for Gear Box (Lehigh Machinery)](https://lehighlathe.com/lubrication-for-headstock-gear-box/) — 기어오일 등급
- [FANUC 0i-TF Plus (FANUC America)](https://www.fanucamerica.com/products/cnc/0i-tf-plus) — 컨트롤러 모델·제어 축
- [Fanuc 0i USB Program Load (Industrial Monitor Direct)](https://industrialmonitordirect.com/blogs/knowledgebase/fanuc-0i-series-usb-program-load-step-by-step-procedure) — USB 메모리 용량
