#!/usr/bin/env python3
"""
Filter images: keep only those containing human faces.
Uses InsightFace (RetinaFace detector + ArcFace backbone).
Non-face images are moved to a 'no_face' subfolder (not deleted).
"""

import os
import sys
import shutil
import time
import cv2
import numpy as np
from pathlib import Path

# ── config ──────────────────────────────────────────────────────
IMG_DIR = Path("/Users/wyl/MediaCrawler-main/data/weibo/images_from_supabase")
NO_FACE_DIR = IMG_DIR / "no_face"
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
DET_SIZE = (640, 640)  # detection input size; larger = more accurate but slower
# ────────────────────────────────────────────────────────────────

def init_model():
    """Load InsightFace face analysis model (buffalo_l)."""
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(
        name="buffalo_l",
        providers=["CPUExecutionProvider"],  # macOS — no CUDA
        allowed_modules=["detection"],        # only need detector, skip recognition
    )
    app.prepare(ctx_id=-1, det_size=DET_SIZE)
    return app


def has_face(app, img_path: str) -> bool:
    """Return True if at least one face is detected in the image."""
    img = cv2.imread(img_path)
    if img is None:
        return False
    # Skip tiny images (likely thumbnails or corrupt)
    h, w = img.shape[:2]
    if h < 64 or w < 64:
        return False
    faces = app.get(img)
    return len(faces) > 0


def main():
    # Collect image files
    images = sorted(
        p for p in IMG_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in EXTS
    )
    total = len(images)
    print(f"Found {total} images in {IMG_DIR}")

    if total == 0:
        print("Nothing to do.")
        return

    NO_FACE_DIR.mkdir(exist_ok=True)

    print("Loading InsightFace model (buffalo_l)...")
    app = init_model()
    print("Model ready.\n")

    kept = 0
    removed = 0
    errors = 0
    t0 = time.time()

    for i, img_path in enumerate(images, 1):
        try:
            if has_face(app, str(img_path)):
                kept += 1
            else:
                shutil.move(str(img_path), str(NO_FACE_DIR / img_path.name))
                removed += 1
        except Exception as e:
            print(f"  [ERROR] {img_path.name}: {e}")
            errors += 1

        # Progress every 50 images
        if i % 50 == 0 or i == total:
            elapsed = time.time() - t0
            fps = i / elapsed if elapsed > 0 else 0
            print(f"  [{i}/{total}] kept={kept} removed={removed} errors={errors}  ({fps:.1f} img/s)")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Kept (has face):    {kept}")
    print(f"  Removed (no face):  {removed}  -> moved to {NO_FACE_DIR}")
    print(f"  Errors:             {errors}")


if __name__ == "__main__":
    main()
