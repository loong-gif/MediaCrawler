#!/usr/bin/env python3
"""Convert product JSON to CSV with one row per variant."""

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return " ".join(text.split())


def iter_rows(products: List[Dict[str, Any]]) -> Iterable[Dict[str, str]]:
    for idx, product in enumerate(products):
        additional = product.get("additionalProperties") or {}
        if not isinstance(additional, dict):
            additional = {}

        brand = product.get("brand") or {}
        if not isinstance(brand, dict):
            brand = {}

        variants = additional.get("hasVariant") or []
        if not isinstance(variants, list):
            variants = []

        base = {
            "product_index": str(idx),
            "product_name": to_text(product.get("name")),
            "product_url": to_text(product.get("url")),
            "product_image": to_text(product.get("image")),
            "product_price": to_text((product.get("offers") or {}).get("price") if isinstance(product.get("offers"), dict) else ""),
            "brand_name": to_text(brand.get("name")),
            "brand_url": to_text(brand.get("url")),
            "variants_count": str(len(variants)),
        }

        if variants:
            for v_idx, variant in enumerate(variants):
                if not isinstance(variant, dict):
                    variant = {"raw_variant": variant}
                offers = variant.get("offers") or {}
                if not isinstance(offers, dict):
                    offers = {}

                row = dict(base)
                row.update(
                    {
                        "variant_index": str(v_idx),
                        "variant_name": to_text(variant.get("name")),
                        "variant_price": to_text(offers.get("price")),
                        "variant_sku": to_text(variant.get("sku")),
                        "variant_mpn": to_text(variant.get("mpn")),
                        "variant_gtin13": to_text(variant.get("gtin13")),
                        "variant_image": to_text(variant.get("image")),
                    }
                )
                yield row
        else:
            row = dict(base)
            row.update(
                {
                    "variant_index": "",
                    "variant_name": "",
                    "variant_price": "",
                    "variant_sku": "",
                    "variant_mpn": "",
                    "variant_gtin13": "",
                    "variant_image": "",
                }
            )
            yield row


def convert(input_path: Path, output_path: Path, limit: Optional[int] = None) -> int:
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("JSON root must be a list of product objects")

    fieldnames = [
        "product_index",
        "product_name",
        "product_url",
        "product_image",
        "product_price",
        "brand_name",
        "brand_url",
        "variants_count",
        "variant_index",
        "variant_name",
        "variant_price",
        "variant_sku",
        "variant_mpn",
        "variant_gtin13",
        "variant_image",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in iter_rows(data):
            writer.writerow(row)
            count += 1
            if limit is not None and count >= limit:
                break

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert product JSON to variant-level CSV")
    parser.add_argument("input", type=Path, help="Path to input JSON")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Path to output CSV")
    parser.add_argument("--limit", type=int, default=None, help="Limit output row count")
    args = parser.parse_args()

    total = convert(args.input, args.output, args.limit)
    print(f"Wrote {total} rows to {args.output}")


if __name__ == "__main__":
    main()
