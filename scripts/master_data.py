"""마스터 데이터: 설비 12대, 구조부 10개, 파트 39개, 구조부 사양.

interval_value, unit_price, stock_qty, 사양값은 모두 데모용 가정값이다.
실제 운영 전 제조사 매뉴얼·사내 보전기준·설비 사양서 값으로 바꿔야 한다.
"""

from datetime import date

EQUIPMENT = [
    {"equipment_id": f"CNC-{n:02d}", "name": f"CNC 선반 {n}호기", "installed_at": date(2014 + (n + 1) // 2, (n * 5) % 12 + 1, 1)}
    for n in range(1, 13)
]

# prd.md 3장 "구조부" 표
ASSEMBLIES = [
    ("GBX", "기어박스", "주축 변속·감속"),
    ("HDS", "주축대", "주축·척 회전"),
    ("CTL", "제어장치", "전기 제어반: 전원·앰프·접촉기"),
    ("TUR", "공구대", "터렛·공구 인덱싱"),
    ("XSL", "이송대", "X축 이송"),
    ("CAR", "왕복대", "Z축 이송"),
    ("TLS", "심압대", "긴 공작물 지지"),
    ("NCU", "NC장치", "CNC 컨트롤러"),
    ("BED", "베드", "본체·습동면, 윤활 유니트"),
    ("OPP", "운전조작반", "화면·스위치·MPG"),
]
ASSEMBLY_ROWS = [
    {"assembly_code": code, "name": name, "description": desc, "sort_order": i}
    for i, (code, name, desc) in enumerate(ASSEMBLIES, start=1)
]

# (part_id, 구조부, 파트명, 별칭, basis, interval_value, 단가(원), 재고, 안전재고)
# 데모용 가정값. 재고는 예비품 부족 사례(BR-01, TS-02, HS-02)가 생기도록 일부러 낮게 둔 것이 있다.
_PARTS = [
    # HS 주축대
    ("HS-01", "HDS", "유압척", "유압척,척,파워척,chuck", "clamp_count", 1_000_000, 3_500_000, 1, 1),
    ("HS-02", "HDS", "척 조", "척 조,조,죠,jaw,소프트조,생조", "clamp_count", 300_000, 180_000, 2, 4),
    ("HS-03", "HDS", "척 로터리 실린더", "로터리 실린더,척 실린더,유압 실린더", "run_hours", 15_000, 2_800_000, 1, 1),
    ("HS-04", "HDS", "스핀들 구동벨트", "구동벨트,스핀들 벨트,벨트,V벨트,타이밍벨트", "run_hours", 8_000, 120_000, 4, 2),
    ("HS-05", "HDS", "스핀들 인코더", "인코더,포지션코더,주축 인코더", "run_hours", 30_000, 950_000, 1, 1),
    # TS 심압대 (유압유니트 포함)
    ("TS-01", "TLS", "유압 작동유", "작동유,유압유,유압오일", "months", 12, 150_000, 6, 2),
    ("TS-02", "TLS", "유압 필터", "유압필터,석션필터,리턴필터", "months", 6, 45_000, 1, 2),
    ("TS-03", "TLS", "유압 펌프", "유압펌프,베인펌프,펌프", "run_hours", 20_000, 1_600_000, 1, 1),
    ("TS-04", "TLS", "솔레노이드 밸브", "솔밸브,솔레노이드,전자밸브,sol", "run_hours", 15_000, 320_000, 3, 1),
    ("TS-05", "TLS", "압력스위치", "압력스위치,압스,PS", "run_hours", 20_000, 180_000, 2, 1),
    ("TS-06", "TLS", "심압대 클램프 실린더", "클램프 실린더,심압대 실린더,퀼 실린더", "run_hours", 15_000, 1_200_000, 1, 1),
    ("TS-07", "TLS", "회전센터", "회전센터,라이브센터,센터,live center", "run_hours", 5_000, 420_000, 2, 1),
    # SD 새들
    ("SD-01", "TUR", "터렛 커플링", "터렛 커플링,커빅 커플링,공구대 커플링", "index_count", 2_000_000, 2_400_000, 1, 1),
    ("SD-02", "TUR", "터렛 클램프 씰", "클램프 씰,터렛 씰,공구대 씰,오링", "months", 24, 85_000, 3, 2),
    ("SD-03", "TUR", "터렛 인덱싱 모터", "인덱싱 모터,터렛 모터,공구대 모터", "index_count", 3_000_000, 1_900_000, 1, 1),
    ("SD-04", "XSL", "X축 볼스크류", "X 볼스크류,X축 볼스크류,X볼", "run_hours", 30_000, 2_200_000, 1, 1),
    ("SD-05", "CAR", "Z축 볼스크류", "Z 볼스크류,Z축 볼스크류,Z볼", "run_hours", 30_000, 2_600_000, 1, 1),
    ("SD-06", "CAR", "와이퍼", "와이퍼,스크레이퍼,커버 와이퍼", "months", 12, 35_000, 8, 4),
    ("SD-07", "XSL", "서보축 커플링", "서보 커플링,모터 커플링,축 커플링", "run_hours", 20_000, 150_000, 2, 1),
    # BR 베어링류 (장착 위치와 무관하게 항상 BR)
    ("BR-01", "HDS", "스핀들 전면 베어링", "주축 베어링,주축 전면 베어링,스핀들 베어링,주축 앞 베어링", "run_hours", 20_000, 1_800_000, 0, 1),
    ("BR-02", "HDS", "스핀들 후면 베어링", "주축 베어링,주축 후면 베어링,스핀들 베어링,주축 뒤 베어링", "run_hours", 20_000, 1_300_000, 1, 1),
    ("BR-03", "XSL", "X축 서포트 베어링", "X 서포트 베어링,X축 서포트,X 지지 베어링", "run_hours", 25_000, 380_000, 1, 1),
    ("BR-04", "CAR", "Z축 서포트 베어링", "Z 서포트 베어링,Z축 서포트,Z 지지 베어링", "run_hours", 25_000, 420_000, 1, 1),
    ("BR-05", "XSL", "X축 LM가이드 블록", "X LM,X축 LM블록,X 리니어,X LM가이드", "run_hours", 30_000, 650_000, 2, 1),
    ("BR-06", "CAR", "Z축 LM가이드 블록", "Z LM,Z축 LM블록,Z 리니어,Z LM가이드", "run_hours", 30_000, 720_000, 2, 1),
    ("BR-07", "TUR", "터렛 베어링", "터렛 베어링,공구대 베어링", "index_count", 3_000_000, 560_000, 1, 1),
    # LB 윤활라인
    ("LB-01", "BED", "습동유", "습동유,웨이오일,way oil,윤활유", "months", 3, 60_000, 10, 4),
    ("LB-02", "BED", "윤활 필터", "윤활필터,루브 필터", "months", 12, 25_000, 4, 2),
    ("LB-03", "BED", "집중윤활 펌프", "윤활펌프,루브 펌프,집중윤활기", "run_hours", 20_000, 480_000, 1, 1),
    ("LB-04", "BED", "분배기", "분배기,분배밸브,디스트리뷰터", "run_hours", 25_000, 90_000, 2, 1),
    ("LB-05", "BED", "윤활 배관/호스", "배관,윤활 호스,윤활 배관,호스", "months", 36, 40_000, 5, 2),
    ("LB-06", "HDS", "오일쿨러 필터", "오일쿨러 필터,쿨러 필터", "months", 6, 30_000, 4, 2),
    # EL 전기판넬
    ("EL-01", "NCU", "APC 배터리", "APC 배터리,앱솔 배터리,앱솔루트 배터리,엡솔 배터리,절대위치 배터리", "months", 12, 45_000, 6, 3),
    ("EL-02", "NCU", "CNC 백업 배터리", "CNC 배터리,메모리 배터리,백업 배터리", "months", 12, 38_000, 4, 2),
    ("EL-03", "CTL", "판넬 쿨러 필터", "판넬쿨러 필터,패널 필터,판넬 필터,에어컨 필터", "months", 3, 15_000, 8, 4),
    ("EL-04", "CTL", "냉각팬", "냉각팬,팬,쿨링팬", "run_hours", 20_000, 70_000, 3, 1),
    ("EL-05", "CTL", "서보 앰프", "서보앰프,서보 드라이브,서보 앰프", "run_hours", 50_000, 2_900_000, 1, 1),
    ("EL-06", "CTL", "스핀들 앰프", "스핀들앰프,주축 앰프,스핀들 드라이브", "run_hours", 50_000, 3_400_000, 1, 1),
    ("EL-07", "CTL", "마그네트 접촉기", "MC,마그네트,전자접촉기,접촉기", "run_hours", 30_000, 65_000, 4, 2),
]
PARTS = [
    {
        "part_id": pid, "unit": pid[:2], "assembly_code": asm, "part_name": name, "aliases": aliases,
        "basis": basis, "interval_value": float(interval), "unit_price": price,
        "stock_qty": stock, "safety_stock": safety,
    }
    for pid, asm, name, aliases, basis, interval, price, stock, safety in _PARTS
]


def spec_rows(equipment_id: str) -> dict[str, dict]:
    """구조부 코드 → 사양 행. CNC-01~06은 박스웨이급, CNC-07~12는 LM가이드급 (데모용 가정값)."""
    n = int(equipment_id[-2:])
    box_way = n <= 6
    specs = {
        "GBX": dict(gear_ranges=2, gear_oil_grade="ISO VG 68", gear_oil_capacity_l=5.0) if box_way
        else dict(gear_ranges=1, gear_oil_grade="ISO VG 32", gear_oil_capacity_l=3.0),
        "HDS": dict(spindle_max_rpm=4000, spindle_nose="A2-6", spindle_motor_kw=18.5) if box_way
        else dict(spindle_max_rpm=6000, spindle_nose="A2-5", spindle_motor_kw=15.0),
        "CTL": dict(power_capacity_kva=23.0, supply_voltage_v=220, rated_current_a=60) if box_way
        else dict(power_capacity_kva=20.0, supply_voltage_v=220, rated_current_a=50),
        "TUR": dict(tool_stations=12, index_time_sec=0.12, tool_shank_mm=25) if box_way
        else dict(tool_stations=12, index_time_sec=0.15, tool_shank_mm=20),
        "XSL": dict(x_travel_mm=215, x_rapid_m_min=24.0, x_ballscrew_dia_mm=32) if box_way
        else dict(x_travel_mm=205, x_rapid_m_min=30.0, x_ballscrew_dia_mm=28),
        "CAR": dict(z_travel_mm=580, z_rapid_m_min=30.0, z_ballscrew_dia_mm=40) if box_way
        else dict(z_travel_mm=340, z_rapid_m_min=36.0, z_ballscrew_dia_mm=32),
        "TLS": dict(quill_dia_mm=65, quill_stroke_mm=80, quill_taper="MT4") if box_way
        else dict(quill_dia_mm=55, quill_stroke_mm=70, quill_taper="MT4"),
        "NCU": dict(controller_model="FANUC 0i-TF Plus" if n >= 3 else "FANUC 0i-TF", controlled_axes=2, usb_max_gb=32),
        "BED": dict(slant_angle_deg=45, guideway_type="박스웨이" if box_way else "LM가이드",
                    swing_over_bed_mm=550 if box_way else 520),
        "OPP": dict(display_size_inch=10.4, is_touchscreen=False, has_mpg=True) if box_way
        else dict(display_size_inch=15.0, is_touchscreen=True, has_mpg=True),
    }
    return {code: {"equipment_id": equipment_id, **values} for code, values in specs.items()}
