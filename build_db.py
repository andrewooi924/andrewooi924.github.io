"""
Build the price database.

This REPLACES matcher.py and merger.py. It abandons the goal of pairing each
Bandai image asset (ST01-006_p10.png) to a marketplace listing, because that
correspondence does not exist in the data (see PROJECT_NOTES). Instead:

  - The Yuyutei LISTING is the unit of pricing (that's what the market sells).
  - Each listing gets a deterministic key:
        (set_code, card_code, rarity, variant_signature)
  - Bandai METADATA (name, color, type, power, effect, base image) is joined
    on card_code, which is stable across art variants.

Inputs:
    cards.json            Bandai metadata (one record per image asset)
    yuyutei_listings.json Output of yuyutei_parse.py (one record per listing)

Output:
    price_database.json   One row per purchasable variant, with prices + metadata
"""

import json
import re
from collections import defaultdict


BANDAI_FILE = "onepiece_data/metadata/cards.json"
YUYUTEI_FILE = "yuyutei_listings.json"
OUTPUT_FILE = "price_database.json"

# Metadata fields that are identical across a card_code's art assets.
META_FIELDS = (
    "name_jp", "color", "card_type", "power", "life",
    "counter", "attribute", "feature", "rarity", "effect",
)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def variant_signature(name):
    tags = re.findall(r"[(（]([^()（）]+)[)）]", name or "")
    return tuple(sorted(t.strip() for t in tags))


def build_bandai_index(bandai):
    """card_code -> (metadata dict, base_image filename or None)."""
    meta = {}
    base_img = {}
    for c in bandai:
        code = c["card_code"]
        if code not in meta:
            meta[code] = {k: c.get(k) for k in META_FIELDS}
        img = c.get("image_filename") or ""
        # Base art = filename with no _pN / _rN suffix.
        if re.fullmatch(r"[A-Z0-9\-]+\.png", img):
            base_img[code] = img
    return meta, base_img


def main():
    bandai = load(BANDAI_FILE)
    listings = load(YUYUTEI_FILE)
    meta, base_img = build_bandai_index(bandai)

    rows = []
    key_index = defaultdict(list)

    for lst in listings:
        # Prefer the variant tags already parsed; fall back to the name.
        variant = tuple(lst.get("variant") or variant_signature(lst.get("name")))
        key = (
            lst["set_code"],
            lst["card_code"],
            lst.get("rarity", ""),
            variant,
        )
        key_index[key].append(lst)

        m = meta.get(lst["card_code"], {})
        rows.append({
            # --- deterministic identity ---
            "set_code": lst["set_code"],
            "card_code": lst["card_code"],
            "yuyutei_rarity": lst.get("rarity", ""),
            "variant": list(variant),
            "yuyutei_cid": lst.get("yuyutei_cid"),
            # --- marketplace pricing ---
            "price": lst.get("price"),
            "sold_out": lst.get("sold_out"),
            "product_url": lst.get("product_url"),
            "yuyutei_name": lst.get("name"),
            # --- Bandai metadata (joined on card_code) ---
            "name_jp": m.get("name_jp"),
            "color": m.get("color"),
            "card_type": m.get("card_type"),
            "power": m.get("power"),
            "life": m.get("life"),
            "counter": m.get("counter"),
            "attribute": m.get("attribute"),
            "feature": m.get("feature"),
            "bandai_rarity": m.get("rarity"),
            "effect": m.get("effect"),
            "base_image": base_img.get(lst["card_code"]),
            "has_metadata": lst["card_code"] in meta,
        })

    collisions = {k: v for k, v in key_index.items() if len(v) > 1}

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    with_meta = sum(1 for r in rows if r["has_metadata"])
    with_price = sum(1 for r in rows if r["price"] is not None)

    print(f"Listings in:            {len(listings)}")
    print(f"Rows out:               {len(rows)}")
    print(f"Distinct keys:          {len(key_index)}")
    print(f"Ambiguous keys left:    {len(collisions)}  "
          f"({sum(len(v) for v in collisions.values())} rows)")
    print(f"Rows with Bandai meta:  {with_meta}/{len(rows)}")
    print(f"Rows with a price:      {with_price}/{len(rows)}")
    print(f"Saved -> {OUTPUT_FILE}")

    if collisions:
        print("\nRemaining collisions (inspect manually or add a tiebreaker):")
        for k, v in list(collisions.items())[:20]:
            print(f"  {k}  x{len(v)}  cids={[x.get('yuyutei_cid') for x in v]}")


if __name__ == "__main__":
    main()