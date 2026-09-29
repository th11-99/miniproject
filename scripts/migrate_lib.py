"""migrations/ 폴더의 버전 스크립트를 찾고 적용하는 공통 로직."""

import importlib.util
from pathlib import Path

from sqlalchemy import inspect, insert, select

from scripts import schema
from scripts.common import ROOT

MIGRATIONS_DIR = ROOT / "migrations"


def list_migrations() -> list[Path]:
    return sorted(p for p in MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.py"))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def applied_versions(conn) -> set[str]:
    if not inspect(conn).has_table("schema_version"):
        return set()
    return {row.version for row in conn.execute(select(schema.schema_version.c.version))}


def apply_pending(conn) -> list[str]:
    """아직 적용되지 않은 마이그레이션을 순서대로 적용하고 적용한 버전 목록을 돌려준다."""
    done = applied_versions(conn)
    applied = []
    for path in list_migrations():
        version = path.stem
        if version in done:
            continue
        _load(path).upgrade(conn)
        conn.execute(insert(schema.schema_version).values(version=version))
        applied.append(version)
    return applied
