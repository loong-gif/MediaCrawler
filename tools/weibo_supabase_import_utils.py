#!/usr/bin/env python3
"""Utilities for generating Supabase import SQL from Weibo flat export files."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
WEIBO_CSV_DIR = ROOT_DIR / "data" / "weibo" / "csv"
WEIBO_JSON_DIR = ROOT_DIR / "data" / "weibo" / "json"
SUPABASE_DIR = ROOT_DIR / "supabase"


def _iter_csv_rows(csv_dir: Path, pattern: str) -> Iterable[tuple[Path, int, Dict[str, str]]]:
    for csv_path in sorted(csv_dir.glob(pattern)):
        if csv_path.name.startswith("."):
            continue
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_number, row in enumerate(reader, start=2):
                yield csv_path, row_number, row


def _iter_json_rows(json_dir: Path, pattern: str) -> Iterable[tuple[Path, int, Dict[str, str]]]:
    for json_path in sorted(json_dir.glob(pattern)):
        if json_path.name.startswith("."):
            continue
        with json_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise ValueError(f"Expected a list of row dicts in {json_path}")
        for row_number, row in enumerate(payload, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"Expected row {row_number} in {json_path} to be a dict")
            normalized = {
                key: "" if value is None else str(value)
                for key, value in row.items()
            }
            yield json_path, row_number, normalized


def iter_rows(patterns: List[str], *, csv_dir: Path = WEIBO_CSV_DIR, json_dir: Path = WEIBO_JSON_DIR) -> Iterable[tuple[Path, int, Dict[str, str]]]:
    for pattern in patterns:
        if pattern.endswith(".csv"):
            yield from _iter_csv_rows(csv_dir, pattern)
            continue
        if pattern.endswith(".json"):
            yield from _iter_json_rows(json_dir, pattern)
            continue
        raise ValueError(f"Unsupported file pattern: {pattern}")


def select_latest_rows(
    patterns: List[str],
    key_field: str,
    timestamp_field: str,
    *,
    csv_dir: Path = WEIBO_CSV_DIR,
    json_dir: Path = WEIBO_JSON_DIR,
) -> Dict[str, Dict[str, str]]:
    latest: Dict[str, tuple[int, str, int, Dict[str, str]]] = {}

    for source_path, row_number, row in iter_rows(patterns, csv_dir=csv_dir, json_dir=json_dir):
        key = require_text(row, key_field)
        timestamp = require_int(row, timestamp_field)
        candidate = (timestamp, source_path.name, row_number, row)
        current = latest.get(key)
        if current is None or candidate[:3] > current[:3]:
            latest[key] = candidate

    return {key: value[3] for key, value in latest.items()}


def require_text(row: Dict[str, str], field: str) -> str:
    value = row.get(field)
    if value is None or value == "":
        raise ValueError(f"Missing required field: {field}")
    return value


def require_int(row: Dict[str, str], field: str) -> int:
    value = require_text(row, field)
    return int(value)


def parse_nullable_text(row: Dict[str, str], field: str) -> Optional[str]:
    value = row.get(field, "")
    return value if value != "" else None


def parse_timestamptz(row: Dict[str, str], field: str) -> str:
    value = require_text(row, field)
    return datetime.fromisoformat(value).isoformat(sep=" ")


def parse_json_array(row: Dict[str, str], field: str) -> List[str]:
    value = row.get(field, "")
    if value == "":
        return []

    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError(f"{field} must be a JSON array")
    return parsed


def build_weibo_image_rows(*, note_id: int, image_urls: List[str]) -> list[dict[str, int | str]]:
    rows: list[dict[str, int | str]] = []
    for image_index, image_url in enumerate(image_urls, start=1):
        if not image_url:
            continue
        rows.append(
            {
                "note_id": note_id,
                "image_url": image_url,
                "image_index": image_index,
            }
        )
    return rows


def plan_weibo_image_upserts(
    *,
    existing_rows: List[Dict[str, int | str]],
    desired_rows: List[Dict[str, int | str]],
) -> dict[str, list]:
    existing_by_index: dict[int, Dict[str, int | str]] = {}
    stale_ids: list[int] = []

    for existing_row in existing_rows:
        image_index = int(existing_row["image_index"])
        if image_index in existing_by_index:
            if "id" in existing_row and existing_row["id"] is not None:
                stale_ids.append(int(existing_row["id"]))
            continue
        existing_by_index[image_index] = existing_row

    desired_indexes = {int(row["image_index"]) for row in desired_rows}
    for image_index, existing_row in existing_by_index.items():
        if image_index in desired_indexes:
            continue
        if "id" in existing_row and existing_row["id"] is not None:
            stale_ids.append(int(existing_row["id"]))

    return {
        "stale_ids": sorted(set(stale_ids)),
        "upsert_rows": desired_rows,
    }


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_text(value: str) -> str:
    return sql_quote(value)


def sql_nullable_text(value: Optional[str]) -> str:
    if value is None:
        return "NULL"
    return sql_quote(value)


def sql_bigint(value: int) -> str:
    return str(value)


def sql_integer(value: int) -> str:
    return str(value)


def sql_timestamptz(value: str) -> str:
    return f"{sql_quote(value)}::timestamptz"


def sql_jsonb(value: List[str]) -> str:
    compact = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return f"{sql_quote(compact)}::jsonb"


def chunked(items: List[str], size: int) -> Iterable[List[str]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def build_upsert_sql(
    *,
    table_name: str,
    column_names: List[str],
    value_rows: List[str],
    conflict_target: str,
    update_assignments: List[str],
) -> str:
    statements = [
        "begin;",
        "set local search_path = public;",
    ]

    columns_sql = ", ".join(column_names)
    updates_sql = ",\n    ".join(update_assignments)

    for rows in chunked(value_rows, 200):
        rows_sql = ",\n".join(rows)
        statements.append(
            f"insert into public.{table_name} ({columns_sql})\n"
            f"values\n{rows_sql}\n"
            f"on conflict ({conflict_target}) do update\n"
            f"set\n    {updates_sql}\n"
            f"where excluded.last_modify_ts >= public.{table_name}.last_modify_ts;"
        )

    statements.append("commit;")
    statements.append("")
    return "\n\n".join(statements)


def write_sql_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
