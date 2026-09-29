"""성공 지표: 자연어 → 파트ID 매핑 정확도 (목표 95% 이상, prd.md 7장).

정답 기준: 후보 집합이 expected와 정확히 같아야 한다 (모호한 표현은 여러 후보가 정답).
"""

import json
from pathlib import Path

from scripts.common import read_connection
from scripts.normalize import find_parts, load_parts

PHRASES = json.loads((Path(__file__).parent / "fixtures" / "phrases.json").read_text(encoding="utf-8"))
TARGET = 0.95


def mapping_accuracy(url) -> tuple[float, list]:
    with read_connection(url) as conn:
        parts = load_parts(conn)
    misses = []
    for case in PHRASES:
        got = sorted(c["part_id"] for c in find_parts(case["text"], parts)["candidates"])
        if got != sorted(case["expected"]):
            misses.append((case["text"], case["expected"], got))
    return 1 - len(misses) / len(PHRASES), misses


def test_phrase_set_size():
    assert len(PHRASES) >= 40


def test_mapping_accuracy(db_url):
    accuracy, misses = mapping_accuracy(db_url)
    print(f"\n매핑 정확도: {accuracy:.1%} ({len(PHRASES) - len(misses)}/{len(PHRASES)})")
    for text, expected, got in misses:
        print(f"  오답: {text!r} 정답 {expected} → 결과 {got}")
    assert accuracy >= TARGET, misses
