"""현재 DB 스키마 정의 (SQLAlchemy Core).

SQLite(로컬)와 PostgreSQL(운영)에서 모두 동작하도록 공통 타입만 사용한다.
스키마를 바꿀 때는 이 파일과 함께 migrations/ 에 새 버전 스크립트를 추가한다.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

metadata = MetaData()

UNITS = ("HS", "TS", "SD", "BR", "LB", "EL")
BASES = ("run_hours", "clamp_count", "index_count", "months")
ACTION_TYPES = ("교체", "수리", "조정", "청소", "점검", "보충")


def _in(column, values):
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=f"ck_{column}")


equipment = Table(
    "equipment",
    metadata,
    Column("equipment_id", String(10), primary_key=True),  # CNC-01 ~ CNC-12
    Column("name", String(50), nullable=False),
    Column("installed_at", Date),
)

assemblies = Table(
    "assemblies",
    metadata,
    Column("assembly_code", String(3), primary_key=True),
    Column("name", String(20), nullable=False),
    Column("description", String(100)),
    Column("sort_order", Integer, nullable=False),
)

parts = Table(
    "parts",
    metadata,
    Column("part_id", String(5), primary_key=True),
    Column("unit", String(2), nullable=False),  # 유지보수 유닛: 무엇을 관리하나
    Column("assembly_code", String(3), ForeignKey("assemblies.assembly_code"), nullable=False),  # 장착 위치
    Column("part_name", String(50), nullable=False),
    Column("aliases", Text, nullable=False, default=""),  # 쉼표 구분 현장 호칭
    Column("basis", String(12), nullable=False),
    Column("interval_value", Float, nullable=False),
    Column("unit_price", Integer, nullable=False),
    Column("stock_qty", Integer, nullable=False, default=0),
    Column("safety_stock", Integer, nullable=False, default=1, server_default="1"),
    _in("unit", UNITS),
    _in("basis", BASES),
)

repair_logs = Table(
    "repair_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("log_date", Date, nullable=False),
    Column("equipment_id", String(10), ForeignKey("equipment.equipment_id"), nullable=False),
    Column("part_id", String(5), ForeignKey("parts.part_id"), nullable=False),
    Column("action_type", String(4), nullable=False),
    Column("is_breakdown", Boolean, nullable=False, default=False),
    Column("description", Text, nullable=False, default=""),
    Column("created_at", DateTime, nullable=False, server_default=func.current_timestamp()),
    _in("action_type", ACTION_TYPES),
)
Index("ix_repair_logs_eq_part_date", repair_logs.c.equipment_id, repair_logs.c.part_id, repair_logs.c.log_date)

run_logs = Table(
    "run_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("log_date", Date, nullable=False),
    Column("equipment_id", String(10), ForeignKey("equipment.equipment_id"), nullable=False),
    # 모두 설비 도입 이후 누적값
    Column("run_hours", Float, nullable=False),
    Column("clamp_count", Integer, nullable=False),
    Column("index_count", Integer, nullable=False),
    UniqueConstraint("equipment_id", "log_date", name="uq_run_logs_eq_date"),
)


def _spec_table(name, *spec_columns):
    """구조부 사양 테이블: equipment_id + 사양 컬럼 3개 + updated_at (prd.md 5장)."""
    assert len(spec_columns) == 3, name
    return Table(
        name,
        metadata,
        Column("equipment_id", String(10), ForeignKey("equipment.equipment_id"), primary_key=True),
        *spec_columns,
        Column("updated_at", DateTime, nullable=False, server_default=func.current_timestamp()),
    )


# 구조부 코드 → 사양 테이블
SPEC_TABLES = {
    "GBX": _spec_table(
        "spec_gearbox",
        Column("gear_ranges", Integer),  # 변속 단수(단)
        Column("gear_oil_grade", String(20)),  # 기어오일 점도등급 (예: ISO VG 68)
        Column("gear_oil_capacity_l", Float),  # 기어오일 용량(L)
    ),
    "HDS": _spec_table(
        "spec_headstock",
        Column("spindle_max_rpm", Integer),
        Column("spindle_nose", String(10)),  # 예: A2-6
        Column("spindle_motor_kw", Float),
    ),
    "CTL": _spec_table(
        "spec_control_cabinet",
        Column("power_capacity_kva", Float),
        Column("supply_voltage_v", Integer),  # 3상
        Column("rated_current_a", Integer),
    ),
    "TUR": _spec_table(
        "spec_turret",
        Column("tool_stations", Integer),
        Column("index_time_sec", Float),
        Column("tool_shank_mm", Integer),
    ),
    "XSL": _spec_table(
        "spec_cross_slide",
        Column("x_travel_mm", Integer),
        Column("x_rapid_m_min", Float),
        Column("x_ballscrew_dia_mm", Integer),
    ),
    "CAR": _spec_table(
        "spec_carriage",
        Column("z_travel_mm", Integer),
        Column("z_rapid_m_min", Float),
        Column("z_ballscrew_dia_mm", Integer),
    ),
    "TLS": _spec_table(
        "spec_tailstock",
        Column("quill_dia_mm", Integer),
        Column("quill_stroke_mm", Integer),
        Column("quill_taper", String(10)),  # 예: MT4
    ),
    "NCU": _spec_table(
        "spec_nc_unit",
        Column("controller_model", String(40)),
        Column("controlled_axes", Integer),
        Column("usb_max_gb", Integer),
    ),
    "BED": _spec_table(
        "spec_bed",
        Column("slant_angle_deg", Integer),  # 평베드 0
        Column("guideway_type", String(10)),  # LM가이드 / 박스웨이
        Column("swing_over_bed_mm", Integer),
    ),
    "OPP": _spec_table(
        "spec_operator_panel",
        Column("display_size_inch", Float),
        Column("is_touchscreen", Boolean),
        Column("has_mpg", Boolean),
    ),
}

schema_version = Table(
    "schema_version",
    metadata,
    Column("version", String(50), primary_key=True),
    Column("applied_at", DateTime, nullable=False, server_default=func.current_timestamp()),
)
