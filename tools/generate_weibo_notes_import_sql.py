#!/usr/bin/env python3
"""Generate idempotent upsert SQL for the latest Weibo note records."""

from __future__ import annotations

import argparse
from pathlib import Path

from weibo_supabase_import_utils import (
    SUPABASE_DIR,
    build_upsert_sql,
    parse_json_array,
    parse_nullable_text,
    parse_timestamptz,
    require_int,
    require_text,
    select_latest_rows,
    sql_bigint,
    sql_jsonb,
    sql_nullable_text,
    sql_text,
    sql_timestamptz,
    write_sql_file,
)


DEFAULT_OUTPUT = SUPABASE_DIR / "import_weibo_notes_latest.sql"


def build_row_sql(row: dict[str, str]) -> str:
    values = [
        sql_bigint(require_int(row, "note_id")),
        sql_text(row.get("content", "")),
        sql_bigint(require_int(row, "create_time")),
        sql_timestamptz(parse_timestamptz(row, "create_date_time")),
        sql_bigint(require_int(row, "liked_count")),
        sql_bigint(require_int(row, "comments_count")),
        sql_bigint(require_int(row, "shared_count")),
        sql_bigint(require_int(row, "last_modify_ts")),
        sql_text(require_text(row, "note_url")),
        sql_nullable_text(parse_nullable_text(row, "ip_location")),
        sql_jsonb(parse_json_array(row, "image_list")),
        sql_bigint(require_int(row, "user_id")),
        sql_text(require_text(row, "nickname")),
        sql_text(require_text(row, "gender")),
        sql_text(require_text(row, "profile_url")),
    ]
    return "    (" + ", ".join(values) + ")"


def generate_sql(output_path: Path) -> int:
    latest_creators = select_latest_rows(
        patterns=["creator_creators_*.csv", "creator_creators_*.json"],
        key_field="user_id",
        timestamp_field="last_modify_ts",
    )
    latest_notes = select_latest_rows(
        patterns=["creator_contents_*.csv", "creator_contents_*.json"],
        key_field="note_id",
        timestamp_field="last_modify_ts",
    )

    missing_user_ids = sorted(
        {
            row["user_id"]
            for row in latest_notes.values()
            if row["user_id"] not in latest_creators
        },
        key=int,
    )
    if missing_user_ids:
        raise ValueError(f"Notes reference creators missing from latest creator data: {missing_user_ids}")

    ordered_rows = [
        latest_notes[note_id]
        for note_id in sorted(latest_notes.keys(), key=int)
    ]

    value_rows = [build_row_sql(row) for row in ordered_rows]
    sql = build_upsert_sql(
        table_name="weibo_notes",
        column_names=[
            "note_id",
            "content",
            "create_time",
            "create_date_time",
            "liked_count",
            "comments_count",
            "shared_count",
            "last_modify_ts",
            "note_url",
            "ip_location",
            "image_list",
            "user_id",
            "nickname",
            "gender",
            "profile_url",
        ],
        value_rows=value_rows,
        conflict_target="note_id",
        update_assignments=[
            "content = excluded.content",
            "create_time = excluded.create_time",
            "create_date_time = excluded.create_date_time",
            "liked_count = excluded.liked_count",
            "comments_count = excluded.comments_count",
            "shared_count = excluded.shared_count",
            "last_modify_ts = excluded.last_modify_ts",
            "note_url = excluded.note_url",
            "ip_location = excluded.ip_location",
            "image_list = excluded.image_list",
            "user_id = excluded.user_id",
            "nickname = excluded.nickname",
            "gender = excluded.gender",
            "profile_url = excluded.profile_url",
        ],
    )
    write_sql_file(output_path, sql)
    return len(ordered_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Weibo note import SQL for Supabase")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to the generated SQL file",
    )
    args = parser.parse_args()

    total = generate_sql(args.output)
    print(f"Wrote {total} latest notes to {args.output}")


if __name__ == "__main__":
    main()
