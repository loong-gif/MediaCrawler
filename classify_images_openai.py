#!/usr/bin/env python3
"""
Classify weibo images: natural life photo vs commercial/advertising.
Uses OpenAI gpt-4o-mini via proxy with concurrent processing.
"""

from __future__ import annotations
import os, sys, json, re, time, base64, subprocess
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── config ──────────────────────────────────────────────────────
MODEL = "gpt-4o-mini"
BATCH_SIZE = 200
DB_WORKDIR = "/Users/wyl/MediaCrawler-main"
CONCURRENCY = 10
MAX_RETRIES = 3
RETRY_DELAY = 5
LOG_FILE = "/tmp/classify_images.log"
MAX_DIM = 512
PROXY = "http://192.168.1.189:7890"
# ────────────────────────────────────────────────────────────────

PROMPT = 'Natural life photo or commercial/advertising image? Reply ONLY JSON: {"is_commercial":true/false,"confidence":0.0-1.0}'

log_fh = open(LOG_FILE, "a", buffering=1)


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    log_fh.write(f"[{ts}] {msg}\n")
    log_fh.flush()


def load_env():
    env = {}
    with open(os.path.expanduser("~/.hermes/.env")) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
    return env


def db_query(sql: str) -> str:
    r = subprocess.run(
        ["supabase", "--workdir", DB_WORKDIR, "db", "query", "--linked", sql],
        capture_output=True, text=True, timeout=120,
    )
    return r.stdout


def fetch_unclassified(limit: int) -> list:
    out = db_query(
        f"SELECT id, image_url FROM weibo_images "
        f"WHERE is_commercial IS NULL ORDER BY id LIMIT {limit}"
    )
    rows = []
    for line in out.strip().split("\n"):
        parts = line.split("│")
        if len(parts) >= 4:
            rid, url = parts[1].strip(), parts[2].strip()
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


def download_and_resize(url: str) -> bytes | None:
    """Download image directly, then resize."""
    import cv2, numpy as np
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://weibo.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            img_bytes = resp.read()
    except Exception:
        return None

    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = MAX_DIM / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes()


def classify_one(api_key: str, row: dict) -> dict | None:
    """Download, resize, classify one image. Returns {id, is_commercial} or None."""
    img = download_and_resize(row["image_url"])
    if not img:
        return None

    b64 = base64.b64encode(img).decode()
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
        "max_tokens": 100,
        "temperature": 0.1,
    }).encode()

    proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    opener = urllib.request.build_opener(proxy_handler)

    for attempt in range(MAX_RETRIES):
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload, headers=headers, method="POST",
        )
        try:
            with opener.open(req, timeout=30) as resp:
                data = json.loads(resp.read())
                content = data["choices"][0]["message"]["content"].strip()
                result = extract_json(content)
                if result and "is_commercial" in result:
                    return {"id": row["id"], "is_commercial": result["is_commercial"]}
                return None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            return None
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            return None
    return None


def main():
    env = load_env()
    api_key = env.get("OPENAI_API_KEY", "")
    if not api_key:
        log("Error: OPENAI_API_KEY not found")
        sys.exit(1)
    log(f"OpenAI key loaded, model={MODEL}, concurrency={CONCURRENCY}")

    remaining = count_unclassified()
    log(f"Unclassified images: {remaining}")

    total_ok = total_err = 0
    t0 = time.time()

    while remaining > 0:
        rows = fetch_unclassified(BATCH_SIZE)
        if not rows:
            # Retry once - supabase CLI may transiently return empty
            time.sleep(3)
            rows = fetch_unclassified(BATCH_SIZE)
            if not rows:
                log("No rows fetched twice, checking count...")
                remaining = count_unclassified()
                if remaining > 0:
                    log(f"Still {remaining} unclassified, retrying in 10s...")
                    time.sleep(10)
                    continue
                break

        log(f"--- Batch: {len(rows)} (remaining: {remaining}) ---")
        updates = []

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = {pool.submit(classify_one, api_key, row): row for row in rows}
            for future in as_completed(futures):
                row = futures[future]
                try:
                    result = future.result()
                    if result:
                        updates.append(result)
                        ic = result["is_commercial"]
                        label = "COMMERCIAL" if ic else "natural"
                        log(f"  id={row['id']} -> {label}")
                        total_ok += 1
                    else:
                        total_err += 1
                        log(f"  id={row['id']} FAIL")
                except Exception as e:
                    total_err += 1
                    log(f"  id={row['id']} EXCEPTION: {e}")

        update_batch(updates)
        remaining -= len(rows)

        elapsed = time.time() - t0
        rate = total_ok / elapsed if elapsed > 0 else 0
        eta = remaining / rate if rate > 0 else 0
        log(f"  Batch done: OK={len(updates)} | Total={total_ok} Err={total_err} | {rate:.1f}/s | ETA={eta/60:.0f}min")

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
