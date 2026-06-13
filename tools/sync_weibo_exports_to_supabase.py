#!/usr/bin/env python3
"""Sync local Weibo flat exports into Supabase via REST upsert."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable

try:
    from tools.weibo_supabase_import_utils import (
        build_weibo_image_rows,
        parse_json_array,
        parse_nullable_text,
        require_int,
        require_text,
        select_latest_rows,
    )
except ImportError:
    from weibo_supabase_import_utils import (
        build_weibo_image_rows,
        parse_json_array,
        parse_nullable_text,
        require_int,
        require_text,
        select_latest_rows,
    )


ROOT_DIR = Path(__file__).resolve().parents[1]
SUPABASE_TEMP_DIR = ROOT_DIR / "supabase" / ".temp"
DEFAULT_PROJECT_REF_PATH = SUPABASE_TEMP_DIR / "project-ref"
DEFAULT_EXPORT_ROOT = ROOT_DIR / "data" / "weibo"
REST_CHUNK_SIZE = 200


def load_project_ref() -> str:
    if not DEFAULT_PROJECT_REF_PATH.exists():
        raise RuntimeError(f"Supabase project ref file not found: {DEFAULT_PROJECT_REF_PATH}")
    return DEFAULT_PROJECT_REF_PATH.read_text(encoding="utf-8").strip()


def load_service_role_key(project_ref: str) -> str:
    cmd = ["supabase", "projects", "api-keys", "--project-ref", project_ref, "-o", "json"]
    result = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to fetch Supabase API keys")

    payload = json.loads(result.stdout)
    for item in payload:
        if item.get("name") == "service_role" and item.get("api_key"):
            return item["api_key"]
        if item.get("type") == "secret" and isinstance(item.get("secret_jwt_template"), dict):
            if item["secret_jwt_template"].get("role") == "service_role" and item.get("api_key"):
                return item["api_key"]
    raise RuntimeError("No usable service_role API key found for the Supabase project")


def build_creator_rows(*, csv_dir: Path, json_dir: Path) -> list[dict]:
    latest_rows = select_latest_rows(
        patterns=["creator_creators_*.csv", "creator_creators_*.json"],
        key_field="user_id",
        timestamp_field="last_modify_ts",
        csv_dir=csv_dir,
        json_dir=json_dir,
    )
    rows = []
    for user_id in sorted(latest_rows.keys(), key=int):
        row = latest_rows[user_id]
        rows.append(
            {
                "user_id": require_int(row, "user_id"),
                "nickname": require_text(row, "nickname"),
                "gender": require_text(row, "gender"),
                "avatar": require_text(row, "avatar"),
                "desc": parse_nullable_text(row, "desc"),
                "ip_location": parse_nullable_text(row, "ip_location"),
                "follows": require_int(row, "follows"),
                "fans": require_text(row, "fans"),
                "tag_list": parse_nullable_text(row, "tag_list"),
                "last_modify_ts": require_int(row, "last_modify_ts"),
            }
        )
    return rows


def build_note_rows(*, csv_dir: Path, json_dir: Path) -> list[dict]:
    latest_rows = select_latest_rows(
        patterns=["creator_contents_*.csv", "creator_contents_*.json"],
        key_field="note_id",
        timestamp_field="last_modify_ts",
        csv_dir=csv_dir,
        json_dir=json_dir,
    )
    rows = []
    for note_id in sorted(latest_rows.keys(), key=int):
        row = latest_rows[note_id]
        rows.append(
            {
                "note_id": require_int(row, "note_id"),
                "content": row.get("content", ""),
                "post_date": require_text(row, "create_date_time"),
                "liked_count": require_int(row, "liked_count"),
                "comments_count": require_int(row, "comments_count"),
                "shared_count": require_int(row, "shared_count"),
                "last_modify_ts": require_int(row, "last_modify_ts"),
                "note_url": require_text(row, "note_url"),
                "ip_location": parse_nullable_text(row, "ip_location"),
                "image_list": parse_json_array(row, "image_list"),
                "user_id": require_int(row, "user_id"),
                "nickname": require_text(row, "nickname"),
                "gender": require_text(row, "gender"),
                "profile_url": require_text(row, "profile_url"),
                "created_at": require_text(row, "create_date_time"),
            }
        )
    return rows


def build_image_rows(note_rows: list[dict]) -> list[dict]:
    image_rows: list[dict] = []
    for note_row in note_rows:
        image_rows.extend(
            build_weibo_image_rows(
                note_id=note_row["note_id"],
                image_urls=note_row["image_list"],
            )
        )
    return image_rows


def chunked(items: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def upsert_rows(*, project_ref: str, api_key: str, table_name: str, conflict_field: str, rows: list[dict]) -> None:
    base_url = f"https://{project_ref}.supabase.co/rest/v1/{table_name}"
    url = f"{base_url}?on_conflict={urllib.parse.quote(conflict_field)}"
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    for batch_number, batch in enumerate(chunked(rows, REST_CHUNK_SIZE), start=1):
        request = urllib.request.Request(
            url,
            data=json.dumps(batch, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120):
                print(f"{table_name}: batch {batch_number} ok ({len(batch)} rows)")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Failed to upsert {table_name} batch {batch_number}: HTTP {exc.code} {body[:500]}"
            ) from exc


def delete_rows(*, project_ref: str, api_key: str, table_name: str, filters: dict[str, str]) -> None:
    if not filters:
        return

    base_url = f"https://{project_ref}.supabase.co/rest/v1/{table_name}"
    query = urllib.parse.urlencode(filters)
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Prefer": "return=minimal",
    }
    request = urllib.request.Request(
        f"{base_url}?{query}",
        headers=headers,
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(request, timeout=120):
            return
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Failed to delete rows from {table_name}: HTTP {exc.code} {body[:500]}"
        ) from exc


def reconcile_image_rows(*, project_ref: str, api_key: str, note_rows: list[dict]) -> None:
    for note_row in note_rows:
        filters = {"note_id": f"eq.{note_row['note_id']}"}
        image_count = len(note_row["image_list"])
        if image_count > 0:
            filters["image_index"] = f"gt.{image_count}"
        delete_rows(
            project_ref=project_ref,
            api_key=api_key,
            table_name="weibo_images",
            filters=filters,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync local Weibo exports into Supabase")
    parser.add_argument("--project-ref", default=load_project_ref(), help="Supabase project ref")
    parser.add_argument(
        "--export-root",
        default=str(DEFAULT_EXPORT_ROOT),
        help="Export root containing csv/ and json/ subdirectories, e.g. output_files/2026-06-12/weibo",
    )
    args = parser.parse_args()

    project_ref = args.project_ref
    export_root = Path(args.export_root).expanduser().resolve()
    csv_dir = export_root / "csv"
    json_dir = export_root / "json"
    if not csv_dir.exists() and not json_dir.exists():
        raise RuntimeError(f"Export root does not contain csv/ or json/ directories: {export_root}")

    api_key = load_service_role_key(project_ref)
    creator_rows = build_creator_rows(csv_dir=csv_dir, json_dir=json_dir)
    note_rows = build_note_rows(csv_dir=csv_dir, json_dir=json_dir)
    image_rows = build_image_rows(note_rows)

    creator_ids = {row["user_id"] for row in creator_rows}
    missing_creator_ids = sorted({row["user_id"] for row in note_rows if row["user_id"] not in creator_ids})
    if missing_creator_ids:
        raise RuntimeError(f"Notes reference creators missing from local creator exports: {missing_creator_ids}")

    print(f"project_ref={project_ref}")
    print(f"export_root={export_root}")
    print(f"creators={len(creator_rows)} notes={len(note_rows)} images={len(image_rows)}")
    upsert_rows(
        project_ref=project_ref,
        api_key=api_key,
        table_name="weibo_creators",
        conflict_field="user_id",
        rows=creator_rows,
    )
    upsert_rows(
        project_ref=project_ref,
        api_key=api_key,
        table_name="weibo_notes",
        conflict_field="note_id",
        rows=note_rows,
    )
    reconcile_image_rows(
        project_ref=project_ref,
        api_key=api_key,
        note_rows=note_rows,
    )
    upsert_rows(
        project_ref=project_ref,
        api_key=api_key,
        table_name="weibo_images",
        conflict_field="note_id,image_index",
        rows=image_rows,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
