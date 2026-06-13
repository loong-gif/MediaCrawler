#!/usr/bin/env python3
"""
Classify weibo images: natural life photo vs commercial/advertising.
Synchronous with rate limiting, image resize, and file-based logging.
"""

from __future__ import annotations
import os, sys, json, re, time, base64, subprocess
import urllib.request, urllib.error

# ── config ──────────────────────────────────────────────────────
API_BASE = "https://token-plan-sgp.xiaomimimo.com/v1"
MODEL = "mimo-v2-omni"
BATCH_SIZE = 20
DB_WORKDIR = "/Users/wyl/MediaCrawler-main"
DELAY_BETWEEN = 8.0
MAX_RETRIES = 5
RETRY_DELAY = 15
LOG_FILE = "/tmp/classify_images.log"
MAX_DIM = 1024            # resize longest edge to this before base64
MAX_BYTES = 2_000_000     # skip images > 2MB raw (before resize)
# ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a binary image classifier. Given an image, determine if it is a "
    "NATURAL LIFE PHOTO (casual selfie, candid moment, travel snapshot, food photo, "
    "personal life) or a COMMERCIAL/ADVERTISING IMAGE (product placement, brand logos, "
    "studio shoot, promotional poster, e-commerce listing, marketing campaign). "
    'Reply with ONLY a JSON object on one line: {"is_commercial": true_or_false, "confidence": 0.0_to_1.0}. '
    "No markdown, no explanation, just the JSON."
)

log_fh = open(LOG_FILE, "a", buffering=1)


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    log_fh.write(f"[{ts}] {msg}\n")
    log_fh.flush()


def load_api_key():
    with open(os.path.expanduser("~/.hermes/.env")) as f:
        for line in f:
            if line.strip().startswith("XIAOMI_API_KEY="):
                return line.strip().split("=", 1)[1]
    return ""


def db_query(sql: str) -> str:
    r = subprocess.run(
        ["supabase", "--workdir", DB_WORKDIR, "db", "query", "--linked", sql],
        capture_output=True, text=True, timeout=60,
    )
    return r.stdout


def fetch_unclassified(limit: int = 20) -> list:
    out = db_query(
        f"SELECT id, image_url FROM weibo_images "
        f"WHERE is_commercial IS NULL ORDER BY id LIMIT {limit}"
    )
    rows = []
    for line in out.strip().split("\n"):
        parts = line.split("│")
        if len(parts) >= 4:
            rid = parts[1].strip()
            url = parts[2].strip()
            if rid.isdigit() and url:
                rows.append({"id": int(rid), "image_url": url})
    return rows


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
    case_parts, all_ids = [], []
    for u in updates:
        all_ids.append(str(u["id"]))
        case_parts.append(f"WHEN {u['id']} THEN {'true' if u['is_commercial'] else 'false'}")
    sql = (
        f"UPDATE weibo_images SET is_commercial = CASE id {' '.join(case_parts)} END "
        f"WHERE id IN ({','.join(all_ids)});"
    )
    db_query(sql)


def extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r'\{[^{}]*"is_commercial"\s*:\s*(?:true|false)[^{}]*\}', text, re.I)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


def download_image(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Referer": "https://weibo.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except Exception:
        return None


def resize_image(img_bytes: bytes) -> bytes:
    """Resize image so longest edge <= MAX_DIM, return JPEG bytes."""
    import cv2, numpy as np
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return img_bytes  # fallback: return original
    h, w = img.shape[:2]
    if max(h, w) <= MAX_DIM:
        # Already small enough, just re-encode as JPEG
        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buf.tobytes()
    scale = MAX_DIM / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes()


def classify_image(api_key: str, image_bytes: bytes) -> dict | None:
    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:image/jpeg;base64,{b64}"

    payload = json.dumps({
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
    }).encode()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(
            f"{API_BASE}/chat/completions", data=payload, headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
                content = data["choices"][0]["message"]["content"].strip()
                return extract_json(content)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                log(f"    [429] waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            log(f"    [HTTP {e.code}]")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            return None
        except Exception as e:
            log(f"    [err] {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            return None
    return None


def main():
    api_key = load_api_key()
    if not api_key:
        log("Error: XIAOMI_API_KEY not found")
        sys.exit(1)
    log(f"API key loaded ({len(api_key)} chars)")

    remaining = count_unclassified()
    log(f"Unclassified images: {remaining}")

    total_ok = total_err = 0
    t0 = time.time()

    while remaining > 0:
        rows = fetch_unclassified(BATCH_SIZE)
        if not rows:
            break

        log(f"--- Batch: {len(rows)} (remaining: {remaining}) ---")
        batch_ok = batch_err = 0

        for i, row in enumerate(rows):
            log(f"  [{i+1}/{len(rows)}] id={row['id']} downloading...")
            img = download_image(row["image_url"])
            if not img:
                log(f"    FAIL (download)")
                batch_err += 1
                continue

            log(f"    raw={len(img)//1024}KB resizing...")
            img = resize_image(img)
            log(f"    resized={len(img)//1024}KB classifying...")

            result = classify_image(api_key, img)
            if result and "is_commercial" in result:
                ic = result["is_commercial"]
                conf = result.get("confidence", "?")
                label = "COMMERCIAL" if ic else "natural"
                log(f"    -> {label} (conf={conf})")
                update_batch([{"id": row["id"], "is_commercial": ic}])
                batch_ok += 1
            else:
                log(f"    FAIL (parse): {result}")
                batch_err += 1

            time.sleep(DELAY_BETWEEN)

        total_ok += batch_ok
        total_err += batch_err
        remaining -= len(rows)

        elapsed = time.time() - t0
        rate = total_ok / elapsed if elapsed > 0 else 0
        eta = remaining / rate if rate > 0 else 0
        log(f"  Batch done: OK={batch_ok} Err={batch_err} | Total={total_ok} | {rate:.2f}/s | ETA={eta/60:.0f}min")

    elapsed = time.time() - t0
    log(f"DONE in {elapsed/60:.1f}min | Classified={total_ok} | Errors={total_err}")
    out = db_query(
        "SELECT is_commercial, count(*) FROM weibo_images "
        "WHERE is_commercial IS NOT NULL GROUP BY is_commercial"
    )
    log(f"Distribution:\n{out}")
    log_fh.close()


if __name__ == "__main__":
    main()
