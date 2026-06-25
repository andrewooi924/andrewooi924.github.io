"""
Yuyutei scraper (corrected).

Replaces the old yyt_scrapper.py. The old one fetched the pages fine but threw
away rarity, variant tags, and the Yuyutei product id. This one fetches every
set page live and extracts the full record per listing:

    set_code, card_code, rarity, name, variant[], price, sold_out,
    yuyutei_cid, product_url

Run:
    python yyt_scrapper.py
Output:
    yuyutei_listings.json   <- feed straight into build_price_database.py
"""

import asyncio
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


BASE_URL = "https://yuyu-tei.jp/sell/opc/s/{}"

CODE_RE = r"(?:OP|ST|EB|PRB)\d{2}-\d{3}"
ALT_RE = re.compile(rf"^({CODE_RE})\s+([A-Z0-9\-]+)\s+(.*)$")
# Yuyutei rarity tokens (incl. promo/DON-area ones): P-SEC, SEC, ... SP, TR, P-P, P, -
RARITIES = {"P-SEC","SEC","P-SR","SR","P-R","R","P-UC","UC","P-C","C","P-L","L","SP","TR","P-P","P","-"}


def generate_sets():
    sets = []
    sets += [f"op{i:02d}" for i in range(1, 17)]
    sets += [f"eb{i:02d}" for i in range(1, 5)]
    sets += [f"prb{i:02d}" for i in range(1, 3)]
    sets += [f"st{i:02d}" for i in range(1, 31)]
    # DON!! cards + promotional sets
    sets += ["don", "promo-100", "promo-200", "promo-op10",
             "promo-op20", "promo-st10", "promo-eb10"]
    return sets


def parse_price(text):
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def variant_signature(name):
    """Order-independent list of parenthetical variant tags. Base art -> []."""
    tags = re.findall(r"[(（]([^()（）]+)[)）]", name or "")
    return sorted(t.strip() for t in tags)


def parse_listing_html(html, set_code):
    soup = BeautifulSoup(html, "lxml")
    out = []

    for prod in soup.select("div.card-product"):
        img = prod.select_one("div.product-img img")
        alt = img["alt"].strip() if img and img.has_attr("alt") else ""
        src = img["src"] if img and img.has_attr("src") else ""   # real Yuyutei image URL

        code = rarity = alt_name = ""
        m = ALT_RE.match(alt)
        if m:
            code, rarity, alt_name = m.group(1), m.group(2), m.group(3).strip()
        else:
            # DON!! / token / promo without a standard code: pull a code if any,
            # then a leading rarity token, then treat the rest as the name.
            cm = re.search(CODE_RE, alt)
            code = cm.group(0) if cm else ""
            rest = alt.replace(code, "", 1).strip() if code else alt
            toks = rest.split()
            if toks and toks[0] in RARITIES:
                rarity, rest = toks[0], rest[len(toks[0]):].strip()
            alt_name = rest

        if not code:
            span = prod.select_one("span.border")
            if span:
                code = span.get_text(strip=True)

        h4 = prod.select_one("h4")
        name = h4.get_text(strip=True) if h4 else alt_name

        strong = prod.select_one("strong")
        price = parse_price(strong.get_text(strip=True) if strong else "")

        cid_el = prod.select_one("input.cart_cid")
        cid = cid_el["value"] if cid_el else ""
        ver_el = prod.select_one("input.cart_ver")
        ver = ver_el["value"] if ver_el else set_code

        link = prod.select_one("a[href*='/card/']")
        url = link["href"] if link else (
            f"https://yuyu-tei.jp/sell/opc/card/{ver}/{cid}" if cid else None
        )

        # No standard code (DON / token / some promos): synthesise a stable one
        # from the page + cid so the listing is still uniquely keyed.
        if not code and cid:
            code = f"{(ver or set_code).upper()}-{cid}"
        if not code:
            continue

        out.append({
            "set_code": ver,
            "card_code": code,
            "rarity": rarity,
            "name": name,
            "variant": variant_signature(name),
            "price": price,
            "sold_out": "sold-out" in prod.get("class", []),
            "yuyutei_cid": cid,
            "image": src,                 # store the real image URL (robust for DON/promo)
            "product_url": url,
        })

    return out


async def scrape_set(page, set_code):
    url = BASE_URL.format(set_code)
    print(f"Scraping {set_code} ...", end=" ", flush=True)
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(2000)
    html = await page.content()
    rows = parse_listing_html(html, set_code)
    print(f"{len(rows)} listings")
    return rows


async def main():
    all_rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        for set_code in generate_sets():
            try:
                all_rows.extend(await scrape_set(page, set_code))
            except Exception as e:
                print(f"{set_code} failed: {e}")
        await browser.close()

    Path("yuyutei_listings.json").write_text(
        json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nSaved {len(all_rows)} listings -> yuyutei_listings.json")


if __name__ == "__main__":
    asyncio.run(main())
