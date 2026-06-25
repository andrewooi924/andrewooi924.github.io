"""Turn price_database.json into a compact, app-ready catalog.json.

Images: use the OFFICIAL Bandai high-res card art
(https://www.onepiece-cardgame.com/images/cardlist/card/<CODE>.png),
keyed by card_code base image. Falls back to the Yuyutei thumbnail only if a
card has no Bandai base image.

NOTE on variants: Bandai's per-art image files (_p1, _p2, ...) can't be reliably
mapped to a specific Yuyutei variant listing, so every variant of a card shows
that card's BASE art. It's sharp and clearly identifies the card; it just won't
render the alternate-art version of a parallel.
"""
import json, re

db = json.load(open('price_database.json', encoding='utf-8'))

COLOR_JP = {'赤':'red','緑':'green','青':'blue','紫':'purple','黒':'black','黄':'yellow'}

def colors(c):
    if not c: return []
    return [COLOR_JP.get(p.strip(), p.strip()) for p in c.split('/')]

def variant_label(tags):
    t = set(tags or [])
    if 'スーパーパラレル' in t: return 'Super Parallel'
    if any(x in t for x in ('ラメフォイル','海賊旗フォイル','箔押し','パラレル/箔押し')): return 'Foil / Stamped'
    if 'パラレル' in t: return 'Parallel'
    if any('修正' in x for x in t): return 'Errata'
    return 'Normal'

# Yuyutei serves one image per listing (cid), so it is ALWAYS the correct variant
# for that listing -- no matching needed. SIZE is the CDN size folder. 100_140 is
# the only size we have confirmed works; if you find Yuyutei serves a larger size
# (open e.g. https://card.yuyu-tei.jp/opc/300_420/op01/10151.jpg in a browser),
# change SIZE here and rebuild for sharper images.
SIZE = "100_140"

def yuyutei_img(set_code, cid):
    return f"https://card.yuyu-tei.jp/opc/{SIZE}/{set_code}/{cid}.jpg"

def bandai_remote(base_image):  # last-resort fallback only (base art)
    return f"https://www.onepiece-cardgame.com/images/cardlist/card/{base_image}" if base_image else None

out = []
for r in db:
    rarity = r.get('yuyutei_rarity') or r.get('bandai_rarity') or '—'
    base = r.get('base_image')
    yt = yuyutei_img(r['set_code'], r['yuyutei_cid'])
    out.append({
        'id': f"{r['set_code']}_{r['yuyutei_cid']}",
        'set': r['set_code'].upper(),
        'code': r['card_code'],
        'name': r.get('name_jp') or r.get('yuyutei_name') or r['card_code'],
        'colors': colors(r.get('color')),
        'rarity': rarity,
        'variant': variant_label(r.get('variant')),
        'tags': r.get('variant') or [],
        'type': (r.get('card_type') or '').title(),
        'power': r.get('power'),
        'price': r.get('price'),
        'soldOut': bool(r.get('sold_out')),
        'img': yt,                                 # Yuyutei image = correct variant
        'imgAlt': bandai_remote(base),             # last resort (base art) if thumb missing
        'imgAlt2': '',
        'url': r.get('product_url'),
        'effect': r.get('effect') or '',
    })

json.dump(out, open('catalog.json','w'), ensure_ascii=False, separators=(',',':'))
import os
print("catalog rows:", len(out), "| size:", round(os.path.getsize('catalog.json')/1024), "KB")
print("sample img:", out[0]['img'])
