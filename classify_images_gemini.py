#!/usr/bin/env python3
"""
Classify Weibo images with Gemini.
Reads image URLs from Supabase and updates weibo_images.is_commercial/is_selfie.
"""

from __future__ import annotations

import asyncio
import argparse
import base64
import csv
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - exercised in runtime environments without the SDK
    genai = None
    genai_types = None

from config import base_config
from pydantic import BaseModel
from store.weibo import (
    WEIBO_MEDIA_DOWNLOAD_FILTER_SELFIE_TRUE,
    build_weibo_selfie_image_filename,
    download_weibo_image,
    get_weibo_media_download_filter,
)


MODEL = "gemini-2.5-flash-lite"
DB_WORKDIR = "/Users/wyl/MediaCrawler-main"
DEFAULT_BATCH_SIZE = 200
DEFAULT_CONCURRENCY = 10
MAX_RETRIES = 3
RETRY_DELAY = 5
MAX_DIM = 512
HTTP_TIMEOUT_SEC = 60
DB_QUERY_TIMEOUT_SEC = 120
UPDATE_CHUNK_SIZE = 20
DB_QUERY_RETRIES = 3
DB_QUERY_RETRY_DELAY_SEC = 3
PROMPT = 'JSON only: {"is_commercial":bool,"is_selfie":bool}. commercial=ad/promo image; selfie=non-commercial selfie.'
ENV_FILE = Path.home() / ".hermes" / ".env"
DEFAULT_FAIL_COUNT_STATE_FILE = Path("/tmp/classify_images_gemini_fail_counts.json")
API_KEY_RUNTIME = ""
REST_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DL_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://weibo.com/",
}


class GeminiClassification(BaseModel):
    is_commercial: bool
    is_selfie: bool


def load_api_key() -> str:
    direct = os.environ.get("GEMINI_API_KEY", "").strip()
    if direct:
        return direct

    if not ENV_FILE.exists():
        return ""

    with ENV_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key == "GEMINI_API_KEY":
                return value.strip()
    return ""


def create_client(api_key: str):
    if genai is None:
        raise RuntimeError("google-genai is not installed. Please install dependencies first.")
    return genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(timeout=HTTP_TIMEOUT_SEC),
    )


def classify_image_rest(image_bytes: bytes) -> dict[str, bool] | None:
    if not API_KEY_RUNTIME:
        raise RuntimeError("GEMINI_API_KEY not available for REST fallback")

    url = (
        f"{REST_API_BASE}/models/{MODEL}:generateContent?"
        f"{urllib.parse.urlencode({'key': API_KEY_RUNTIME})}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": PROMPT},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64.b64encode(image_bytes).decode(),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"REST classify failed: HTTP {exc.code} {body[:400]}") from exc

    text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    fallback = extract_json(text)
    if fallback is None:
        return None
    if "is_commercial" not in fallback or "is_selfie" not in fallback:
        return None
    return normalize_result(fallback)


def db_query(sql: str) -> str:
    last_error: Exception | None = None
    for attempt in range(DB_QUERY_RETRIES):
        try:
            result = subprocess.run(
                ["supabase", "--workdir", DB_WORKDIR, "db", "query", "--linked", sql],
                capture_output=True,
                text=True,
                timeout=DB_QUERY_TIMEOUT_SEC,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or f"Supabase query failed: {sql}")
            return result.stdout
        except Exception as exc:
            last_error = exc
            if attempt == DB_QUERY_RETRIES - 1:
                break
            time.sleep(DB_QUERY_RETRY_DELAY_SEC * (attempt + 1))
    raise RuntimeError(f"Supabase query failed after retries: {last_error}")


def build_where_clause(force: bool) -> str:
    if force:
        return "TRUE"
    return "(is_commercial IS NULL OR is_selfie IS NULL)"


def parse_table_rows(stdout: str) -> list[dict[str, Any]]:
    rows_from_json = parse_supabase_rows(stdout)
    if rows_from_json is not None:
        rows: list[dict[str, Any]] = []
        for row in rows_from_json:
            row_id = row.get("id")
            image_url = row.get("image_url")
            if isinstance(row_id, int) and image_url:
                normalized_row = {"id": row_id, "image_url": str(image_url)}
                if row.get("note_id") is not None:
                    normalized_row["note_id"] = int(row["note_id"])
                if row.get("image_index") is not None:
                    normalized_row["image_index"] = int(row["image_index"])
                rows.append(normalized_row)
            elif isinstance(row_id, str) and row_id.isdigit() and image_url:
                normalized_row = {"id": int(row_id), "image_url": str(image_url)}
                if row.get("note_id") is not None and str(row["note_id"]).isdigit():
                    normalized_row["note_id"] = int(row["note_id"])
                if row.get("image_index") is not None and str(row["image_index"]).isdigit():
                    normalized_row["image_index"] = int(row["image_index"])
                rows.append(normalized_row)
        return rows

    rows: list[dict[str, Any]] = []
    for line in stdout.strip().split("\n"):
        parts = line.split("│")
        if len(parts) < 4:
            continue
        row_id = parts[1].strip()
        if len(parts) >= 5:
            note_id = parts[2].strip()
            image_index = parts[3].strip()
            image_url = parts[4].strip()
        else:
            note_id = ""
            image_index = ""
            image_url = parts[2].strip()
        if row_id.isdigit() and image_url:
            row: dict[str, Any] = {"id": int(row_id), "image_url": image_url}
            if note_id.isdigit():
                row["note_id"] = int(note_id)
            if image_index.isdigit():
                row["image_index"] = int(image_index)
            rows.append(row)
    return rows


def parse_supabase_rows(stdout: str) -> list[dict[str, Any]] | None:
    text = stdout.strip()
    if not text or not text.startswith("{"):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    rows = payload.get("rows")
    if isinstance(rows, list):
        return rows
    return None


def fetch_rows(*, limit: int, force: bool) -> list[dict[str, Any]]:
    where_clause = build_where_clause(force)
    sql = (
        "SELECT id, note_id, image_index, image_url FROM weibo_images "
        f"WHERE {where_clause} ORDER BY id LIMIT {limit}"
    )
    return parse_table_rows(db_query(sql))


def count_rows(*, force: bool) -> int:
    where_clause = build_where_clause(force)
    out = db_query(f"SELECT count(*) FROM weibo_images WHERE {where_clause}")
    rows_from_json = parse_supabase_rows(out)
    if rows_from_json:
        first = rows_from_json[0]
        for key in ("count", "count(*)", "pending"):
            value = first.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)

    for line in out.strip().split("\n"):
        parts = line.split("│")
        if len(parts) >= 3:
            value = parts[1].strip()
            if value.isdigit():
                return int(value)
    return 0


def build_update_sql(updates: list[dict[str, Any]]) -> str:
    commercial_cases: list[str] = []
    selfie_cases: list[str] = []
    ids: list[str] = []

    for update in updates:
        row_id = int(update["id"])
        ids.append(str(row_id))
        commercial_cases.append(f"WHEN {row_id} THEN {'true' if update['is_commercial'] else 'false'}")
        selfie_cases.append(f"WHEN {row_id} THEN {'true' if update['is_selfie'] else 'false'}")

    return (
        "UPDATE weibo_images "
        f"SET is_commercial = CASE id {' '.join(commercial_cases)} END, "
        f"is_selfie = CASE id {' '.join(selfie_cases)} END "
        f"WHERE id IN ({','.join(ids)});"
    )


def update_batch(updates: list[dict[str, Any]]) -> None:
    if not updates:
        return
    for index in range(0, len(updates), UPDATE_CHUNK_SIZE):
        chunk = updates[index : index + UPDATE_CHUNK_SIZE]
        _update_chunk_with_retry(chunk)


def _update_chunk_with_retry(chunk: list[dict[str, Any]]) -> None:
    if not chunk:
        return
    try:
        db_query(build_update_sql(chunk))
        return
    except Exception:
        if len(chunk) == 1:
            return

    mid = len(chunk) // 2
    _update_chunk_with_retry(chunk[:mid])
    _update_chunk_with_retry(chunk[mid:])


def extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    raise ValueError(f"Unsupported boolean value: {value!r}")


def normalize_result(result: dict[str, Any]) -> dict[str, bool]:
    normalized = {
        "is_commercial": coerce_bool(result["is_commercial"]),
        "is_selfie": coerce_bool(result["is_selfie"]),
    }
    if normalized["is_commercial"]:
        normalized["is_selfie"] = False
    return normalized


def parse_response(response: Any) -> dict[str, bool] | None:
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        if isinstance(parsed, dict):
            return normalize_result(parsed)
        return normalize_result(
            {
                "is_commercial": getattr(parsed, "is_commercial"),
                "is_selfie": getattr(parsed, "is_selfie"),
            }
        )

    text = getattr(response, "text", "")
    fallback = extract_json(text)
    if fallback is None:
        return None
    if "is_commercial" not in fallback or "is_selfie" not in fallback:
        return None
    return normalize_result(fallback)


def download_and_resize(url: str) -> bytes | None:
    import cv2
    import numpy as np

    request = urllib.request.Request(url, headers=DL_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            original_bytes = response.read()
    except Exception:
        return None

    image_array = np.frombuffer(original_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        return None

    height, width = image.shape[:2]
    scale = MAX_DIM / max(height, width)
    if scale < 1:
        image = cv2.resize(
            image,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_AREA,
        )

    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return None
    return buffer.tobytes()


def classify_image(client: Any, image_bytes: bytes) -> dict[str, bool] | None:
    if genai_types is None:
        raise RuntimeError("google-genai is not installed. Please install dependencies first.")
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                PROMPT,
                genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            ],
            config=genai_types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=GeminiClassification,
            ),
        )
        return parse_response(response)
    except Exception:
        # Some environments intermittently fail TLS handshakes in SDK transport.
        # Fall back to direct Gemini REST call to keep batch jobs progressing.
        return classify_image_rest(image_bytes)


def classify_one(client: Any, row: dict[str, Any]) -> dict[str, Any] | None:
    image_bytes = download_and_resize(row["image_url"])
    if not image_bytes:
        return None

    for attempt in range(MAX_RETRIES):
        try:
            result = classify_image(client, image_bytes)
            if result is None:
                return None
            return {"id": row["id"], **result}
        except Exception:
            if attempt == MAX_RETRIES - 1:
                return None
            time.sleep(RETRY_DELAY * (attempt + 1))
    return None


def classify_url(client: Any, image_url: str) -> dict[str, bool] | None:
    image_bytes = download_and_resize(image_url)
    if not image_bytes:
        return None
    return classify_image(client, image_bytes)


def emit_single_result(result: dict[str, bool], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return

    writer = csv.writer(sys.stdout)
    writer.writerow(["is_commercial", "is_selfie"])
    writer.writerow([str(result["is_commercial"]).lower(), str(result["is_selfie"]).lower()])


def print_distribution() -> None:
    print(
        "is_commercial distribution:\n"
        + db_query(
            "SELECT is_commercial, count(*) FROM weibo_images "
            "WHERE is_commercial IS NOT NULL GROUP BY is_commercial ORDER BY is_commercial"
        ),
        flush=True,
    )
    print(
        "is_selfie distribution:\n"
        + db_query(
            "SELECT is_selfie, count(*) FROM weibo_images "
            "WHERE is_selfie IS NOT NULL GROUP BY is_selfie ORDER BY is_selfie"
        ),
        flush=True,
    )
    print(
        "cross distribution:\n"
        + db_query(
            "SELECT is_commercial, is_selfie, count(*) FROM weibo_images "
            "WHERE is_commercial IS NOT NULL AND is_selfie IS NOT NULL "
            "GROUP BY is_commercial, is_selfie ORDER BY is_commercial, is_selfie"
        ),
        flush=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify Weibo images with Gemini")
    parser.add_argument("--image-url", help="Classify a single image URL directly")
    parser.add_argument(
        "--output-format",
        choices=("csv", "json"),
        default="csv",
        help="Output format for --image-url mode",
    )
    parser.add_argument("--force", action="store_true", help="Reclassify all rows")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Rows per batch")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Parallel worker count")
    parser.add_argument(
        "--hard-fail-default-after",
        type=int,
        default=0,
        help=(
            "If > 0, rows that fail this many times in one run are backfilled as "
            "commercial=false,selfie=false to avoid infinite retries."
        ),
    )
    parser.add_argument(
        "--skip-initial-count",
        action="store_true",
        help="Start processing immediately without querying initial pending count.",
    )
    parser.add_argument(
        "--fail-count-state-file",
        default=str(DEFAULT_FAIL_COUNT_STATE_FILE),
        help="JSON file path used to persist row fail counts across restarts.",
    )
    return parser.parse_args()


def load_fail_counts(path: Path) -> dict[int, int]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[int, int] = {}
    for key, value in payload.items():
        if str(key).isdigit() and isinstance(value, int) and value > 0:
            result[int(key)] = value
    return result


def save_fail_counts(path: Path, fail_counts: dict[int, int]) -> None:
    compact = {str(key): value for key, value in fail_counts.items() if value > 0}
    path.write_text(json.dumps(compact, ensure_ascii=False), encoding="utf-8")


def should_download_classified_selfies() -> bool:
    if not base_config.ENABLE_GET_MEIDAS:
        return False
    return get_weibo_media_download_filter() == WEIBO_MEDIA_DOWNLOAD_FILTER_SELFIE_TRUE


def build_selfie_download_rows(updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    download_rows: list[dict[str, Any]] = []
    for update in updates:
        if not update.get("is_selfie"):
            continue
        note_id = update.get("note_id")
        image_index = update.get("image_index")
        image_url = update.get("image_url")
        if note_id is None or image_index is None or not image_url:
            continue
        download_rows.append(
            {
                "note_id": int(note_id),
                "image_index": int(image_index),
                "image_url": str(image_url),
            }
        )
    return download_rows


async def _download_selfie_media_rows(download_rows: list[dict[str, Any]]) -> tuple[int, int]:
    success_count = 0
    total_count = len(download_rows)
    save_path = "data/weibo/images"

    for row in download_rows:
        filename = build_weibo_selfie_image_filename(
            note_id=row["note_id"],
            image_index=row["image_index"],
        )
        ok = await download_weibo_image(row["image_url"], save_path, filename)
        if ok:
            success_count += 1
    return success_count, total_count


def download_selfie_media_rows(download_rows: list[dict[str, Any]]) -> tuple[int, int]:
    if not download_rows:
        return 0, 0
    return asyncio.run(_download_selfie_media_rows(download_rows))


def main() -> None:
    global API_KEY_RUNTIME
    args = parse_args()
    api_key = load_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in env or ~/.hermes/.env")
    API_KEY_RUNTIME = api_key

    client = create_client(api_key)
    if args.image_url:
        result = classify_url(client, args.image_url)
        if result is None:
            raise RuntimeError("Failed to classify image URL")
        emit_single_result(result, args.output_format)
        return

    if args.skip_initial_count:
        remaining: int | None = None
        print("Pending images: unknown (skip initial count)", flush=True)
    else:
        remaining = count_rows(force=args.force)
        print(f"Pending images: {remaining}", flush=True)

    fail_count_state_path = Path(args.fail_count_state_file)
    row_failures = load_fail_counts(fail_count_state_path)
    total_ok = 0
    total_err = 0
    total_fallback = 0
    started_at = time.time()

    while True:
        rows = fetch_rows(limit=args.batch_size, force=args.force)
        if not rows:
            break

        remaining_text = "unknown" if remaining is None else str(remaining)
        print(f"--- Batch: {len(rows)} (remaining: {remaining_text}) ---", flush=True)
        updates: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {pool.submit(classify_one, client, row): row for row in rows}
            for future in as_completed(futures):
                row = futures[future]
                result = future.result()
                if result is None:
                    total_err += 1
                    row_failures[row["id"]] = row_failures.get(row["id"], 0) + 1
                    if (
                        args.hard_fail_default_after > 0
                        and row_failures[row["id"]] >= args.hard_fail_default_after
                    ):
                        fallback_update = {
                            "id": row["id"],
                            "is_commercial": False,
                            "is_selfie": False,
                        }
                        updates.append(fallback_update)
                        total_fallback += 1
                        print(
                            (
                                f"  id={row['id']} HARD_FAIL("
                                f"{row_failures[row['id']]}) -> fallback commercial=False selfie=False"
                            ),
                            flush=True,
                        )
                        row_failures.pop(row["id"], None)
                        continue
                    print(f"  id={row['id']} FAIL", flush=True)
                    continue

                updates.append({**row, **result})
                total_ok += 1
                row_failures.pop(row["id"], None)
                print(
                    f"  id={row['id']} -> commercial={result['is_commercial']} selfie={result['is_selfie']}",
                    flush=True,
                )

        update_batch(updates)
        if should_download_classified_selfies():
            download_rows = build_selfie_download_rows(updates)
            downloaded_ok, download_total = download_selfie_media_rows(download_rows)
            if download_total > 0:
                print(
                    f"Selfie downloads: ok={downloaded_ok} total={download_total}",
                    flush=True,
                )
        save_fail_counts(fail_count_state_path, row_failures)
        if remaining is not None:
            remaining = max(0, remaining - len(rows))

        elapsed = time.time() - started_at
        rate = total_ok / elapsed if elapsed > 0 else 0
        eta = ((remaining or 0) / rate) if (rate > 0 and remaining is not None) else 0
        eta_text = f"{eta/60:.0f}min" if remaining is not None else "n/a"
        print(
            f"Batch done: ok={len(updates)} total_ok={total_ok} total_err={total_err} "
            f"total_fallback={total_fallback} "
            f"rate={rate:.1f}/s eta={eta_text}",
            flush=True,
        )

    elapsed = time.time() - started_at
    print(
        f"DONE in {elapsed/60:.1f}min | ok={total_ok} | err={total_err} | fallback={total_fallback}",
        flush=True,
    )
    print_distribution()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
