#!/usr/bin/env python3
"""Generate idempotent SQL to backfill weibo_images from latest Weibo note exports."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from tools.weibo_supabase_import_utils import (
        SUPABASE_DIR,
        build_weibo_image_rows,
        chunked,
        parse_json_array,
        select_latest_rows,
        sql_bigint,
        sql_integer,
        sql_text,
        write_sql_file,
    )
except ImportError:
    from weibo_supabase_import_utils import (
        SUPABASE_DIR,
        build_weibo_image_rows,
        chunked,
        parse_json_array,
        select_latest_rows,
        sql_bigint,
        sql_integer,
        sql_text,
        write_sql_file,
    )


DEFAULT_OUTPUT = SUPABASE_DIR / "import_weibo_images_latest.sql"


def build_value_row(row: dict[str, int | str]) -> str:
    return "    (" + ", ".join(
        [
            sql_bigint(int(row["note_id"])),
            sql_text(str(row["image_url"])),
            sql_integer(int(row["image_index"])),
        ]
    ) + ")"


def generate_sql(output_path: Path) -> tuple[int, int]:
    latest_notes = select_latest_rows(
        patterns=["creator_contents_*.csv", "creator_contents_*.json"],
        key_field="note_id",
        timestamp_field="last_modify_ts",
    )

    ordered_note_ids = sorted((int(note_id) for note_id in latest_notes.keys()))
    note_image_rows: dict[int, list[dict[str, int | str]]] = {}
    total_image_rows = 0

    for note_id in ordered_note_ids:
        note_row = latest_notes[str(note_id)]
        image_rows = build_weibo_image_rows(
            note_id=note_id,
            image_urls=parse_json_array(note_row, "image_list"),
        )
        note_image_rows[note_id] = image_rows
        total_image_rows += len(image_rows)

    statements = [
        "begin;",
        "set local search_path = public;",
    ]

    for note_id_chunk in chunked(ordered_note_ids, 200):
        note_ids_sql = ", ".join(str(note_id) for note_id in note_id_chunk)
        statements.append(f"delete from public.weibo_images where note_id in ({note_ids_sql});")

        value_rows = [
            build_value_row(image_row)
            for note_id in note_id_chunk
            for image_row in note_image_rows[note_id]
        ]
        if not value_rows:
            continue

        rows_sql = ",\n".join(value_rows)
        statements.append(
            "insert into public.weibo_images (note_id, image_url, image_index)\n"
            f"values\n{rows_sql}\n"
            "on conflict (note_id, image_index) do update\n"
            "set image_url = excluded.image_url;"
        )

    statements.append("commit;")
    statements.append("")

    write_sql_file(output_path, "\n\n".join(statements))
    return len(ordered_note_ids), total_image_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Weibo image backfill SQL for Supabase")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to the generated SQL file",
    )
    args = parser.parse_args()

    note_count, image_count = generate_sql(args.output)
    print(f"Wrote {image_count} image rows across {note_count} notes to {args.output}")


if __name__ == "__main__":
    main()
