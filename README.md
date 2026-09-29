# CNC 선반 보전관리

CNC 선반 12대(CNC-01 ~ CNC-12)의 수리 이력 등록, 교체 도래 점검, 고장 패턴 분석을 돕는 Streamlit 앱과 CLI 도구입니다.
요구사항은 [`prd.md`](prd.md)에 있습니다.

> 교체주기·단가·사양·샘플 이력은 모두 **데모용 가정값**입니다. 실제 기준은 제조사 매뉴얼·사내 보전기준을 따르세요.

## 로컬 실행

개발·테스트 환경은 Python 3.14입니다 (그보다 낮은 버전은 확인하지 않았습니다).

```bash
# 1. 가상환경과 패키지
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt      # macOS/Linux: .venv/bin/python

# 2. 샘플 DB 만들기 (db/maintenance.db, 기존 DB가 있으면 --yes 필요)
.venv/Scripts/python scripts/init_db.py --yes

# 3. 앱 실행 → 브라우저에서 http://localhost:8501
.venv/Scripts/python -m streamlit run streamlit_app.py
```

- 앱이 DB 파일을 열고 있으면 `init_db.py`가 DB를 지우지 못합니다. 앱을 먼저 종료하세요.
- `app_pages/_components.py`나 `scripts/`를 고친 뒤에는 앱을 다시 시작해야 반영됩니다(페이지 파일만 자동 반영).
- 다른 DB를 쓰려면 `DATABASE_URL` 환경변수나 `.streamlit/secrets.toml`(`secrets.toml.example` 참고)을 설정합니다.

## 배포 (Streamlit Community Cloud, 시연용)

1. 이 저장소를 GitHub에 올립니다 (`db/*.db`, `.streamlit/secrets.toml`, `.venv/`는 `.gitignore`로 제외됨).
2. [share.streamlit.io](https://share.streamlit.io)에서 **Create app** → 저장소·브랜치 선택, Main file path = `streamlit_app.py`.
3. Secrets는 비워 둡니다. 첫 실행 때 앱이 시연용 샘플 DB를 자동으로 만듭니다(`streamlit_app.ensure_demo_db`).
   - Cloud는 재시작·재배포 때 파일이 초기화되므로 **등록한 이력은 유지되지 않습니다.** 계속 운영하려면 외부 PostgreSQL을 만들어 Secrets에 `[database] url = "..."`를 넣습니다(5단계, 운영 DB 초기화 스크립트는 아직 없음).

## 화면

| 화면 | 하는 일 |
|---|---|
| 대시보드 | 교체 초과·30일 내 도래·이번 달 돌발고장·예방보전 비율, 설비 12대 상태 카드 |
| 설비 상세 | 구조부 10개 탭별 사양 3개, 장착 파트의 교체 도래 상태, 최근 이력 |
| 이력 등록 | 현장 표현 입력 → 해석 → 확인·수정 → 미리보기(경고 표시) → "등록할까요?" 확인 → 등록 |
| 교체 도래 | 설비·유닛·기간(7/30/90일) 필터, 상태 색 표시, CSV 저장(엑셀용) |
| 고장 분석 | 기간·설비 필터, 문제 → 추정 원인 → 권장 조치 → 확인 방법 카드, 유닛별·월별 차트 |
| 이력 조회 | 설비·파트·기간·돌발 여부 필터, 정렬·검색 가능한 표 |

## CLI

같은 기능을 명령줄에서도 쓸 수 있습니다. 모든 명령은 `-h`로 옵션을 볼 수 있고 `--format table`로 표 출력이 됩니다.

```bash
.venv/Scripts/python scripts/normalize.py "3번기 주축 베어링 소음나서 교체"
.venv/Scripts/python scripts/log_repair.py --equipment 3호기 --part BR-01 --action 교체 --breakdown --dry-run
.venv/Scripts/python scripts/due_check.py --days 30 --format table
.venv/Scripts/python scripts/analyze.py --months 6
.venv/Scripts/python scripts/equipment.py --equipment 3호기
.venv/Scripts/python scripts/history.py --equipment 3호기 --breakdown yes --format table
.venv/Scripts/python scripts/query.py "SELECT * FROM parts" --format table
```

## 테스트

```bash
.venv/Scripts/python -m pytest                                 # 전체
.venv/Scripts/python -m pytest tests/test_mapping_accuracy.py -s   # 현장 표현 매핑 정확도 출력
```

테스트는 임시 DB를 만들어 쓰므로 `db/maintenance.db`를 건드리지 않습니다.
`TEST_DATABASE_URL`에 테스트 전용 PostgreSQL(DB 이름에 `test` 포함)을 지정하면 같은 테스트를 PostgreSQL에서도 실행합니다.
