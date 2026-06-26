import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

import requests
from playwright.async_api import async_playwright

OP_NUM = 16
EB_NUM = 4
PRB_NUM = 2
ST_NUM = 30
FAMILY_NUM = 1

BASE_URL = "https://www.onepiece-cardgame.com/cardlist/?series={}"

OUTPUT_DIR = Path("")
IMAGE_DIR = OUTPUT_DIR / "images"
METADATA_DIR = OUTPUT_DIR / "metadata"

IMAGE_DIR.mkdir(parents=True, exist_ok=True)
METADATA_DIR.mkdir(parents=True, exist_ok=True)


def clean(value: str, prefix: str = ""):
    if value is None:
        return ""

    value = value.strip()

    if prefix:
        value = value.replace(prefix, "")

    return value.strip()


def download_image(url, save_path):

    if save_path.exists():
        return

    try:

        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        response.raise_for_status()

        with open(save_path, "wb") as f:
            f.write(response.content)

    except Exception as e:
        print(f"Failed image {url}: {e}")


async def get_text(parent, selector):

    try:

        el = await parent.query_selector(selector)

        if not el:
            return ""

        return (await el.inner_text()).strip()

    except:
        return ""

def get_collection_name(series_id):

    series_id = str(series_id)

    if series_id == "550701":
        return "FAMILY"

    if series_id == "550801":
        return "LIMITED"

    if series_id == "550901":
        return "PROMO"

    if series_id.startswith("5501"):
        return f"OP{int(series_id[-2:]):02d}"

    if series_id.startswith("5502"):
        return f"EB{int(series_id[-2:]):02d}"

    if series_id.startswith("5503"):
        return f"PRB{int(series_id[-2:]):02d}"

    if series_id.startswith("5500"):
        return f"ST{int(series_id[-2:]):02d}"

    return "UNKNOWN"

def get_bandai_variant(image_filename):

    filename = image_filename.lower()

    if "_p" in filename:
        return "AA"

    return "NORMAL"

async def scrape_card(card, series_id):

    try:

        info = await card.query_selector(".infoCol")

        spans = await info.query_selector_all("span")

        card_code = (
            await spans[0].inner_text()
            if len(spans) > 0 else ""
        )

        rarity = (
            await spans[1].inner_text()
            if len(spans) > 1 else ""
        )

        card_type = (
            await spans[2].inner_text()
            if len(spans) > 2 else ""
        )

        name = await get_text(
            card,
            ".cardName"
        )

        img = await card.query_selector(
            ".frontCol img"
        )

        image_url = ""

        if img:

            image_url = await img.get_attribute(
                "data-src"
            )

            if image_url:

                image_url = (
                    "https://www.onepiece-cardgame.com/"
                    + image_url.replace("../", "")
                )

        attribute = ""

        attr_img = await card.query_selector(
            ".attribute img"
        )

        if attr_img:

            attribute = (
                await attr_img.get_attribute("alt")
            ) or ""

        life = clean(
            await get_text(card, ".cost"),
            "ライフ"
        )

        power = clean(
            await get_text(card, ".power"),
            "パワー"
        )

        counter = clean(
            await get_text(card, ".counter"),
            "カウンター"
        )

        color = clean(
            await get_text(card, ".color"),
            "色"
        )

        block = clean(
            await get_text(card, ".block"),
            "ブロックアイコン"
        )

        feature = clean(
            await get_text(card, ".feature"),
            "特徴"
        )

        effect = clean(
            await get_text(card, ".text"),
            "テキスト"
        )

        source_set = clean(
            await get_text(card, ".getInfo"),
            "入手情報"
        )

        filename = ""

        if image_url:

            filename = Path(
                urlparse(image_url).path
            ).name

            printing_id = Path(filename).stem

            collection = get_collection_name(series_id)

        collection_folder = IMAGE_DIR / collection

        collection_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        save_path = collection_folder / filename

        download_image(
            image_url,
            save_path
        )

        return {
            "card_code": card_code,

            "collection": collection,

            "series_id": series_id,

            "name_jp": name,
            "rarity": rarity,
            "card_type": card_type,

            "life": life,
            "power": power,
            "counter": counter,

            "color": color,
            "block": block,
            "attribute": attribute,

            "feature": feature,
            "effect": effect,

            "source_set": source_set,

            "image_url": image_url,
            "image_filename": filename,

            "scraped_at": datetime.utcnow().isoformat(),

            "printing_id": printing_id
        }

    except Exception as e:

        print(
            f"Failed card scrape: {e}"
        )

        return None


async def scrape_series(page, series_id):

    url = BASE_URL.format(series_id)

    print(
        f"Scraping series {series_id}"
    )

    await page.goto(
        url,
        wait_until="networkidle"
    )

    cards = await page.query_selector_all(
        ".modalCol"
    )

    if len(cards) == 0:

        return []

    print(
        f"Found {len(cards)} cards"
    )

    results = []

    for card in cards:

        card_data = await scrape_card(
            card,
            series_id
        )

        if card_data:

            results.append(card_data)

    return results


def generate_series():

    series = []

    for i in range(1, ST_NUM + 1):
        series.append(f"5500{i:02d}")

    for i in range(1, OP_NUM + 1):
        series.append(f"5501{i:02d}")

    for i in range(1, EB_NUM + 1):
        series.append(f"5502{i:02d}")

    for i in range(1, PRB_NUM + 1):
        series.append(f"5503{i:02d}")
        
    series.append("550701")
    series.append("550801")
    series.append("550901")

    return series


async def main():

    all_cards = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        for series_id in generate_series():

            cards = await scrape_series(
                page,
                series_id
            )

            all_cards.extend(cards)

        await browser.close()

    output_file = (
        METADATA_DIR / "cards.json"
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            all_cards,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print(
        f"Saved {len(all_cards)} card versions"
    )

def generate_yuyutei_sets():

    sets = []

    for i in range(1, 17):
        sets.append(f"op{i:02d}")

    for i in range(1, 5):
        sets.append(f"eb{i:02d}")

    for i in range(1, 3):
        sets.append(f"prb{i:02d}")

    for i in range(1, 31):
        sets.append(f"st{i:02d}")

    return sets

if __name__ == "__main__":
    asyncio.run(main())