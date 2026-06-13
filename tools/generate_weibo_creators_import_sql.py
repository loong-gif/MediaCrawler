#!/usr/bin/env python3
"""Generate idempotent upsert SQL for the latest Weibo creator records."""

from __future__ import annotations

import argparse
from pathlib import Path

from weibo_supabase_import_utils import (
    SUPABASE_DIR,
    build_upsert_sql,
    parse_nullable_text,
    require_int,
    require_text,
    select_latest_rows,
    sql_bigint,
    sql_integer,
    sql_nullable_text,
    sql_text,
    write_sql_file,
)


DEFAULT_OUTPUT = SUPABASE_DIR / "import_weibo_creators_latest.sql"


def build_row_sql(row: dict[str, str]) -> str:
    values = [
        sql_bigint(require_int(row, "user_id")),
        sql_text(require_text(row, "nickname")),
        sql_text(require_text(row, "gender")),
        sql_text(require_text(row, "avatar")),
        sql_nullable_text(parse_nullable_text(row, "desc")),
        sql_nullable_text(parse_nullable_text(row, "ip_location")),
        sql_integer(require_int(row, "follows")),
        sql_text(require_text(row, "fans")),
        sql_nullable_text(parse_nullable_text(row, "tag_list")),
        sql_bigint(require_int(row, "last_modify_ts")),
    ]
    return "    (" + ", ".join(values) + ")"


def generate_sql(output_path: Path) -> int:
    latest_rows = select_latest_rows(
        patterns=["creator_creators_*.csv", "creator_creators_*.json"],
        key_field="user_id",
        timestamp_field="last_modify_ts",
    )

    ordered_rows = [
        latest_rows[user_id]
        for user_id in sorted(latest_rows.keys(), key=int)
    ]

    value_rows = [build_row_sql(row) for row in ordered_rows]
    sql = build_upsert_sql(
        table_name="weibo_creators",
        column_names=[
            "user_id",
            "nickname",
            "gender",
            "avatar",
            '"desc"',
            "ip_location",
            "follows",
            "fans",
            "tag_list",
            "last_modify_ts",
        ],
        value_rows=value_rows,
        conflict_target="user_id",
        update_assignments=[
            "nickname = excluded.nickname",
            "gender = excluded.gender",
            "avatar = excluded.avatar",
            '"desc" = excluded."desc"',
            "ip_location = excluded.ip_location",
            "follows = excluded.follows",
            "fans = excluded.fans",
            "tag_list = excluded.tag_list",
            "last_modify_ts = excluded.last_modify_ts",
        ],
    )
    write_sql_file(output_path, sql)
    return len(ordered_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Weibo creator import SQL for Supabase")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to the generated SQL file",
    )
    args = parser.parse_args()

    total = generate_sql(args.output)
    print(f"Wrote {total} latest creators to {args.output}")


if __name__ == "__main__":
    main()
