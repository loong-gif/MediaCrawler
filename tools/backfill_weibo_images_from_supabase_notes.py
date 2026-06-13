#!/usr/bin/env python3
"""Backfill weibo_images directly from remote Supabase weibo_notes.image_list."""

from __future__ import annotations

import argparse
import http.client
import json
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

try:
    from tools.weibo_supabase_import_utils import build_weibo_image_rows
except ImportError:
    from weibo_supabase_import_utils import build_weibo_image_rows


REST_CHUNK_SIZE = 500
NOTE_BATCH_SIZE = 200


def load_service_role_key(project_ref: str) -> str:
    payload = json.loads(
        subprocess.check_output(
            ["supabase", "projects", "api-keys", "--project-ref", project_ref, "-o", "json"],
            text=True,
        )
    )
    for item in payload:
        if item.get("name") == "service_role" and item.get("api_key"):
            return item["api_key"]
    raise RuntimeError("No usable service_role API key found for the Supabase project")


def request_json(*, project_ref: str, api_key: str, table_name: str, method: str, params: dict[str, str] | None = None, body=None):
    url = f"https://{project_ref}.supabase.co/rest/v1/{table_name}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if method in {"POST", "DELETE"}:
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    request = urllib.request.Request(url, headers=headers, data=data, method=method)
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            if exc.code >= 500 and attempt < 5:
                last_error = RuntimeError(
                    f"{method} {table_name} failed: HTTP {exc.code} {error_body[:1000]}"
                )
                time.sleep(attempt)
                continue
            raise RuntimeError(
                f"{method} {table_name} failed: HTTP {exc.code} {error_body[:1000]}"
            ) from exc
        except (urllib.error.URLError, http.client.IncompleteRead, ssl.SSLError, ConnectionResetError) as exc:
            last_error = exc
            if attempt == 5:
                break
            time.sleep(attempt)
    if last_error is not None:
        raise last_error
    return None


def iter_note_batches(*, project_ref: str, api_key: str, batch_size: int, start_offset: int):
    offset = start_offset
    while True:
        rows = request_json(
            project_ref=project_ref,
            api_key=api_key,
            table_name="weibo_notes",
            method="GET",
            params={
                "select": "note_id,image_list",
                "image_list": "not.eq.[]",
                "order": "note_id.asc",
                "limit": str(batch_size),
                "offset": str(offset),
            },
        ) or []
        if not rows:
            return
        yield rows
        offset += len(rows)


def fetch_existing_images(*, project_ref: str, api_key: str, note_ids: list[int]) -> list[dict]:
    if not note_ids:
        return []
    ids_sql = ",".join(str(note_id) for note_id in note_ids)
    return request_json(
        project_ref=project_ref,
        api_key=api_key,
        table_name="weibo_images",
        method="GET",
        params={
            "select": "id,note_id,image_index,image_url,is_commercial,is_selfie,created_at",
            "note_id": f"in.({ids_sql})",
            "order": "note_id.asc,image_index.asc,id.asc",
        },
    ) or []


def choose_existing_template(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    prioritized = sorted(
        rows,
        key=lambda row: (
            row.get("is_commercial") is None,
            row.get("is_selfie") is None,
            row.get("created_at") is None,
            row.get("id", 0),
        ),
    )
    return prioritized[0]


def chunked(items: list[dict], size: int):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def backfill(project_ref: str, note_batch_size: int, start_offset: int) -> tuple[int, int]:
    api_key = load_service_role_key(project_ref)
    processed_notes = start_offset
    processed_images = 0

    for batch_number, note_rows in enumerate(
        iter_note_batches(
            project_ref=project_ref,
            api_key=api_key,
            batch_size=note_batch_size,
            start_offset=start_offset,
        ),
        start=(start_offset // note_batch_size) + 1,
    ):
        note_ids = [int(row["note_id"]) for row in note_rows]
        existing_images = fetch_existing_images(project_ref=project_ref, api_key=api_key, note_ids=note_ids)
        existing_by_note_index: dict[tuple[int, int], list[dict]] = {}
        for row in existing_images:
            key = (int(row["note_id"]), int(row["image_index"]))
            existing_by_note_index.setdefault(key, []).append(row)

        insert_rows: list[dict] = []
        for note_row in note_rows:
            note_id = int(note_row["note_id"])
            desired_rows = build_weibo_image_rows(note_id=note_id, image_urls=note_row.get("image_list") or [])
            for desired_row in desired_rows:
                template = choose_existing_template(
                    existing_by_note_index.get((note_id, int(desired_row["image_index"])), [])
                )
                insert_row = {
                    "note_id": desired_row["note_id"],
                    "image_url": desired_row["image_url"],
                    "image_index": desired_row["image_index"],
                    "is_commercial": None,
                    "is_selfie": None,
                    "created_at": None,
                }
                if template is not None:
                    insert_row["is_commercial"] = template.get("is_commercial")
                    insert_row["is_selfie"] = template.get("is_selfie")
                    insert_row["created_at"] = template.get("created_at")
                insert_rows.append(insert_row)

        ids_sql = ",".join(str(note_id) for note_id in note_ids)
        request_json(
            project_ref=project_ref,
            api_key=api_key,
            table_name="weibo_images",
            method="DELETE",
            params={"note_id": f"in.({ids_sql})"},
        )

        for row_chunk in chunked(insert_rows, REST_CHUNK_SIZE):
            request_json(
                project_ref=project_ref,
                api_key=api_key,
                table_name="weibo_images",
                method="POST",
                body=row_chunk,
            )

        processed_notes += len(note_rows)
        processed_images += len(insert_rows)
        print(
            f"batch={batch_number} notes={processed_notes} images={processed_images}",
            flush=True,
        )

    return processed_notes, processed_images


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill weibo_images from remote weibo_notes.image_list")
    parser.add_argument("--project-ref", required=True, help="Supabase project ref")
    parser.add_argument(
        "--note-batch-size",
        type=int,
        default=NOTE_BATCH_SIZE,
        help="Number of notes to reconcile per batch",
    )
    parser.add_argument(
        "--start-offset",
        type=int,
        default=0,
        help="Starting note offset for resume runs",
    )
    args = parser.parse_args()

    note_count, image_count = backfill(args.project_ref, args.note_batch_size, args.start_offset)
    print(f"Backfilled {image_count} images across {note_count} notes")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
