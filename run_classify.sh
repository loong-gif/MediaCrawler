#!/bin/bash
cd /Users/wyl/MediaCrawler-main
export PYTHONUNBUFFERED=1
export XIAOMI_API_KEY="$(grep XIAOMI_API_KEY ~/.hermes/.env | cut -d= -f2-)"
exec .venv/bin/python3 classify_images.py
