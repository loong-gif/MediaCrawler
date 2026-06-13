#!/usr/bin/env python3
"""
Classify weibo images: natural life photo vs commercial/advertising.
Uses mimo-v2-omni multimodal LLM via OpenAI-compatible API.
Downloads images -> base64 -> API (weibo CDN blocked from API server).
Updates weibo_images.is_commercial in Supabase.
"""

from __future__ import annotations
import os
import sys
import json
import re
import time
import base64
import asyncio
import aiohttp
import subprocess

# ── config ──────────────────────────────────────────────────────
API_BASE = "https://token-plan-sgp.xiaomimimo.com/v1"
API_KEY = os.environ.get("XIAOMI_API_KEY", "")
MODEL = "mimo-v2-omni"
BATCH_SIZE = 50           # rows per DB fetch
CONCURRENCY = 5           # parallel API calls
MAX_RETRIES = 5
RETRY_DELAY = 5
DB_WORKDIR = "/Users/wyl/MediaCrawler-main"
DL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://weibo.com/",
}
# ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a binary image classifier. Given an image, determine if it is a "
    "NATURAL LIFE PHOTO (casual selfie, candid moment, travel snapshot, food photo, "
    "personal life) or a COMMERCIAL/ADVERTISING IMAGE (product placement, brand logos, "
    "studio shoot, promotional poster, e-commerce listing, marketing campaign). "
    "Reply with ONLY a JSON object on a single line, no markdown, no explanation: "
    '{"is_commercial": true_or_false, "confidence": 0.0_to_1.0}'
)


def db_query(sql: str) -> str:
    cmd = ["supabase", "--workdir", DB_WORKDIR, "db", "query", "--linked", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"DB error: {r.stderr[:200]}", file=sys.stderr)
        return ""
    return r.stdout


def parse_table_rows(stdout: str) -> list:
    rows = []
    for line in stdout.strip().split("\n"):
        parts = line.split("│")
        if len(parts) >= 4:
            row_id = parts[1].strip()
            image_url = parts[2].strip()
            if row_id and image_url and row_id.isdigit():
                rows.append({"id": int(row_id), "image_url": image_url})
    return rows


def fetch_unclassified(limit: int = 50) -> list:
    out = db_query(f"SELECT id, image_url FROM weibo_images WHERE is_commercial IS NULL LIMIT {limit}")
    return parse_table_rows(out)


def count_unclassified() -> int:
    out = db_query("SELECT count(*) FROM weibo_images WHERE is_commercial IS NULL")
    for line in out.strip().split("\n"):
        parts = line.split("│")
        if len(parts) >= 3:
            val = parts[1].strip()
            if val.isdigit():
                return int(val)
    return 0


def update_batch(updates: list):
    if not updates:
        return
    case_parts = []
    all_ids = []
    for u in updates:
        all_ids.append(str(u["id"]))
        val = "true" if u["is_commercial"] else "false"
        case_parts.append(f"WHEN {u['id']} THEN {val}")

    case_expr = " ".join(case_parts)
    ids_str = ",".join(all_ids)
    sql = (
        f"UPDATE weibo_images "
        f"SET is_commercial = CASE id {case_expr} END "
        f"WHERE id IN ({ids_str});"
    )
    db_query(sql)


def extract_json(text: str) -> dict | None:
    """Extract JSON from model response (handles markdown, prose, etc.)."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown code block
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    match = re.search(r'\{[^{}]*"is_commercial"\s*:\s*(?:true|false)[^{}]*\}', text, re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Try to infer from keywords
    text_lower = text.lower()
    if '"is_commercial"' in text_lower:
        if "true" in text_lower.split('"is_commercial"')[1][:20]:
            return {"is_commercial": True, "confidence": 0.5}
        elif "false" in text_lower.split('"is_commercial"')[1][:20]:
            return {"is_commercial": False, "confidence": 0.5}

    return None


async def download_image(session: aiohttp.ClientSession, url: str) -> bytes | None:
    try:
        async with session.get(url, headers=DL_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception:
        pass
    return None


async def classify_image(session: aiohttp.ClientSession, image_bytes: bytes) -> dict | None:
    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:image/jpeg;base64,{b64}"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": "Classify this image. Reply ONLY with JSON."},
            ]},
        ],
        "max_tokens": 300,
        "temperature": 0.1,
    }

    for attempt in range(MAX_RETRIES):
        try:
            async with session.post(
                f"{API_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                if resp.status == 429:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                if resp.status != 200:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY)
                        continue
                    return None

                data = await resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                return extract_json(content)

        except Exception:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
                continue
            return None

    return None


async def process_one(semaphore: asyncio.Semaphore, row: dict) -> dict | None:
    async with semaphore:
        async with aiohttp.ClientSession() as session:
            img_bytes = await download_image(session, row["image_url"])
            if not img_bytes:
                return None
            result = await classify_image(session, img_bytes)
            if result and "is_commercial" in result:
                return {"id": row["id"], "is_commercial": result["is_commercial"]}
    return None


async def main():
    if not API_KEY:
        print("Error: XIAOMI_API_KEY not set")
        sys.exit(1)

    remaining = count_unclassified()
    print(f"Unclassified images: {remaining}", flush=True)

    total_classified = 0
    total_errors = 0
    t0 = time.time()

    while remaining > 0:
        rows = fetch_unclassified(BATCH_SIZE)
        if not rows:
            break

        print(f"\nBatch: {len(rows)} images (remaining: {remaining})", flush=True)

        semaphore = asyncio.Semaphore(CONCURRENCY)
        tasks = [process_one(semaphore, row) for row in rows]
        completed = await asyncio.gather(*tasks)

        updates = [r for r in completed if r is not None]
        errors = len(rows) - len(updates)
        total_errors += errors

        update_batch(updates)
        total_classified += len(updates)
        remaining -= len(rows)

        elapsed = time.time() - t0
        rate = total_classified / elapsed if elapsed > 0 else 0
        eta = remaining / rate if rate > 0 else 0
        print(
            f"  OK: {len(updates)} | Err: {errors} | Total: {total_classified} | "
            f"Rate: {rate:.1f}/s | ETA: {eta/60:.0f}min",
            flush=True,
        )
        await asyncio.sleep(1)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed/60:.1f}min", flush=True)
    print(f"  Classified: {total_classified}", flush=True)
    print(f"  Errors: {total_errors}", flush=True)

    out = db_query(
        "SELECT is_commercial, count(*) FROM weibo_images "
        "WHERE is_commercial IS NOT NULL GROUP BY is_commercial"
    )
    print(f"\nDistribution:\n{out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
