#!/usr/bin/env python3
"""Download Weibo images from Supabase when is_selfie = true."""

from __future__ import annotations

import argparse
import asyncio

from store.weibo import build_weibo_selfie_image_filename, download_weibo_image
from store.weibo._store_impl import SupabaseWeiboRestStore


DEFAULT_SAVE_PATH = "data/weibo/images"
DEFAULT_BATCH_SIZE = 200


async def fetch_selfie_rows(*, limit: int, offset: int) -> list[dict]:
    return await SupabaseWeiboRestStore.fetch_rows(
        table_name="weibo_images",
        select_fields="note_id,image_index,image_url",
        filters={
            "is_selfie": "eq.true",
            "limit": str(limit),
            "offset": str(offset),
        },
        order_by="note_id.asc,image_index.asc",
    )


async def download_rows(*, rows: list[dict], save_path: str) -> tuple[int, int]:
    success_count = 0
    total_count = len(rows)

    for row in rows:
        note_id = int(row["note_id"])
        image_index = int(row["image_index"])
        image_url = str(row["image_url"])
        filename = build_weibo_selfie_image_filename(
            note_id=note_id,
            image_index=image_index,
        )
        if await download_weibo_image(image_url, save_path, filename):
            success_count += 1

    return success_count, total_count


async def run(*, save_path: str, batch_size: int) -> tuple[int, int]:
    offset = 0
    total_success = 0
    total_seen = 0

    while True:
        rows = await fetch_selfie_rows(limit=batch_size, offset=offset)
        if not rows:
            break

        batch_success, batch_total = await download_rows(rows=rows, save_path=save_path)
        total_success += batch_success
        total_seen += batch_total
        offset += len(rows)
        print(
            f"batch_offset={offset} downloaded={batch_success}/{batch_total} total={total_success}/{total_seen}",
            flush=True,
        )

    return total_success, total_seen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Weibo selfie images from Supabase weibo_images"
    )
    parser.add_argument(
        "--save-path",
        default=DEFAULT_SAVE_PATH,
        help="Directory for downloaded images",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Number of Supabase rows to fetch per batch",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    total_success, total_seen = asyncio.run(
        run(save_path=args.save_path, batch_size=args.batch_size)
    )
    print(f"DONE downloaded={total_success}/{total_seen}", flush=True)


if __name__ == "__main__":
    main()
