# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from tools.generate_weibo_images_backfill_sql import generate_sql
from tools.sync_weibo_exports_to_supabase import build_image_rows
from tools.weibo_supabase_import_utils import (
    build_weibo_image_rows,
    parse_json_array,
    plan_weibo_image_upserts,
)


def test_build_weibo_image_rows_empty_values():
    assert build_weibo_image_rows(note_id=100, image_urls=[]) == []
    assert build_weibo_image_rows(note_id=100, image_urls=["", "https://img.example/2.jpg"]) == [
        {
            "note_id": 100,
            "image_url": "https://img.example/2.jpg",
            "image_index": 2,
        }
    ]


def test_build_image_rows_keeps_order_and_one_based_index():
    note_rows = [
        {
            "note_id": 200,
            "image_list": [
                "https://img.example/1.jpg",
                "https://img.example/2.jpg",
            ],
        },
        {
            "note_id": 201,
            "image_list": ["https://img.example/3.jpg"],
        },
    ]

    assert build_image_rows(note_rows) == [
        {
            "note_id": 200,
            "image_url": "https://img.example/1.jpg",
            "image_index": 1,
        },
        {
            "note_id": 200,
            "image_url": "https://img.example/2.jpg",
            "image_index": 2,
        },
        {
            "note_id": 201,
            "image_url": "https://img.example/3.jpg",
            "image_index": 1,
        },
    ]


def test_parse_json_array_raises_on_invalid_json():
    try:
        parse_json_array({"image_list": "not-json"}, "image_list")
    except json.JSONDecodeError:
        return
    raise AssertionError("Expected json.JSONDecodeError")


def test_generate_backfill_sql_replaces_existing_note_images():
    latest_rows = {
        "200": {
            "note_id": "200",
            "last_modify_ts": "10",
            "image_list": json.dumps(["https://img.example/1.jpg", "https://img.example/2.jpg"]),
        },
        "201": {
            "note_id": "201",
            "last_modify_ts": "11",
            "image_list": json.dumps([]),
        },
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "import_weibo_images_latest.sql"
        with patch("tools.generate_weibo_images_backfill_sql.select_latest_rows", return_value=latest_rows):
            note_count, image_count = generate_sql(output_path)

        sql = output_path.read_text(encoding="utf-8")

    assert note_count == 2
    assert image_count == 2
    assert "delete from public.weibo_images where note_id in (200, 201);" in sql
    assert "on conflict (note_id, image_index) do update" in sql
    assert "https://img.example/1.jpg" in sql
    assert "https://img.example/2.jpg" in sql


def test_plan_weibo_image_upserts_marks_duplicates_and_removed_indexes():
    desired_rows = [
        {
            "note_id": 300,
            "image_url": "https://img.example/new-1.jpg",
            "image_index": 1,
        },
        {
            "note_id": 300,
            "image_url": "https://img.example/new-2.jpg",
            "image_index": 2,
        },
    ]
    existing_rows = [
        {"id": 1, "image_index": 1, "image_url": "https://img.example/old-1.jpg"},
        {"id": 2, "image_index": 3, "image_url": "https://img.example/old-3.jpg"},
        {"id": 3, "image_index": 1, "image_url": "https://img.example/dup-1.jpg"},
    ]

    sync_plan = plan_weibo_image_upserts(
        existing_rows=existing_rows,
        desired_rows=desired_rows,
    )

    assert sync_plan["stale_ids"] == [2, 3]
    assert sync_plan["upsert_rows"] == desired_rows
