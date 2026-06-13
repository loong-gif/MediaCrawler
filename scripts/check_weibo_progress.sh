#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/wyl/MediaCrawler-main"
LOG_PATH="${1:-$ROOT_DIR/run_logs/weibo_creator_retry_5_uids_new_token.log}"
UIDS="${WEIBO_PROGRESS_UIDS:-6146539952,5589792153,6741964788,5211643249,5479678683}"
PROCESS_PATTERN='uv run main.py --platform wb --lt cookie --type creator --save_data_option supabase'

cd "$ROOT_DIR"

echo "== Process =="
PIDS="$(pgrep -af "$PROCESS_PATTERN" || true)"
if [[ -n "$PIDS" ]]; then
  echo "$PIDS"
  MAIN_PID="$(printf '%s\n' "$PIDS" | awk 'NR==1{print $1}')"
  echo
  echo "== Process Stats =="
  ps -p "$MAIN_PID" -o pid,etime,state,pcpu,pmem,command
else
  echo "No matching creator process found."
fi

echo
echo "== Supabase Counts =="
WEIBO_PROGRESS_UIDS="$UIDS" uv run python - <<'PY'
import asyncio
import os
from store.weibo._store_impl import SupabaseWeiboRestStore

uids = [uid.strip() for uid in os.environ["WEIBO_PROGRESS_UIDS"].split(",") if uid.strip()]

async def main():
    counts = {}
    total = 0
    for uid in uids:
        rows = await SupabaseWeiboRestStore.fetch_rows(
            table_name="weibo_notes",
            select_fields="note_id",
            filters={"user_id": f"eq.{uid}"},
        )
        count = len(rows)
        counts[uid] = count
        total += count

    print({"total": total, "counts": counts})

asyncio.run(main())
PY

echo
echo "== Log Tail =="
if [[ -f "$LOG_PATH" ]]; then
  tail -n 40 "$LOG_PATH"
else
  echo "Log file not found: $LOG_PATH"
fi
