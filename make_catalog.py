"""Turn price_database.json into a compact, app-ready catalog.json.

Images: each Yuyutei listing's own image (the cid is per-variant, so it is always
the correct art). Uses the real image URL captured by the scraper when present,
otherwise reconstructs it from set + cid.

DON & promos: DON cards (Bandai card_type "-", or the 'don' set page) are typed
as "DON". Promo set pages get tidy labels (P-100, P-OP10, ...). These flow into
the Type and Set filters automatically.
"""
import json, re, os

db = json.load(open('price_database.json', encoding='utf-8'))

COLOR_JP = {'赤':'red','緑':'green','青':'blue','紫':'purple','黒':'black','黄':'yellow'}

# Tidy display label for each Yuyutei set slug.
SET_LABELS = {'don':'DON','promo-100':'P-100','promo-200':'P-200',
              'promo-op10':'P-OP10','promo-op20':'P-OP20',
              'promo-st10':'P-ST10','promo-eb10':'P-EB10'}

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

def card_type(r, name):
    ct = (r.get('card_type') or '').strip()
    # DON!! cards: Bandai type "-", the dedicated DON page, or named "ドン!!…".
    # The name check catches booster DON cards, which carry no Bandai metadata.
    if ct == '-' or r['set_code'] == 'don' or 'ドン!!' in (name or ''):
        return 'DON'
    return ct.title()

SIZE = "100_140"   # change to a larger Yuyutei size here if one exists
def yuyutei_img(set_code, cid):
    return f"https://card.yuyu-tei.jp/opc/{SIZE}/{set_code}/{cid}.jpg"
def bandai_remote(base_image):
    return f"https://www.onepiece-cardgame.com/images/cardlist/card/{base_image}" if base_image else None

out = []
for r in db:
    rarity = r.get('yuyutei_rarity') or r.get('bandai_rarity') or '—'
    base = r.get('base_image')
    img = r.get('yuyutei_image') or yuyutei_img(r['set_code'], r['yuyutei_cid'])
    name = r.get('name_jp') or r.get('yuyutei_name') or r['card_code']
    out.append({
        'id': f"{r['set_code']}_{r['yuyutei_cid']}",
        'set': SET_LABELS.get(r['set_code'], r['set_code'].upper()),
        'code': r['card_code'],
        'name': name,
        'colors': colors(r.get('color')),
        'rarity': rarity,
        'variant': variant_label(r.get('variant')),
        'tags': r.get('variant') or [],
        'type': card_type(r, name),
        'power': r.get('power'),
        'price': r.get('price'),
        'soldOut': bool(r.get('sold_out')),
        'img': img,                                # Yuyutei image = correct variant
        'imgAlt': bandai_remote(base),             # fallback: official base art
        'imgAlt2': '',
        'url': r.get('product_url'),
        'effect': r.get('effect') or '',
    })

json.dump(out, open('catalog.json','w'), ensure_ascii=False, separators=(',',':'))
print("catalog rows:", len(out), "| size:", round(os.path.getsize('catalog.json')/1024), "KB")
from collections import Counter
print("types:", Counter(c['type'] for c in out).most_common())
