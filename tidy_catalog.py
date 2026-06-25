"""One-shot tidy for an existing catalog.json (no re-scrape / rebuild needed).

Applies:
  #2  All promo sets -> "PROMO" (set label + card label).
  #3  Rarity outliers:  "—" / "-" / blank -> "P";
                        "SP P" -> "SP" only for the OP15 card, otherwise "P";
                        stray "SPカード" -> "SP".
  #4  Variant "Errata" -> "Normal".

Run next to your catalog.json:   python tidy_catalog.py
It rewrites catalog.json in place (a .bak copy is saved first).
"""
import json, os, shutil, collections

F = 'catalog.json'
shutil.copyfile(F, F + '.bak')
cat = json.load(open(F, encoding='utf-8'))

def set_label(s):
    s = s or ''
    if s == 'DON': return 'DON'
    # promos look like "P", "P-100", "P-OP10", "PROMO-100"… but NOT "PRB01".
    if s == 'P' or s.startswith('P-') or s.startswith('PROMO'): return 'PROMO'
    return s

def rarity_label(r, setlbl):
    r = (r or '').strip()
    if r in ('—', '-', '−', '–', ''): return 'P'
    if r in ('SP P', 'SP-P', 'SP/P'): return 'SP' if setlbl == 'OP15' else 'P'
    if r in ('SPカード',): return 'SP'
    return r

changed = collections.Counter()
for c in cat:
    orig_set = c.get('set', '')
    ns = set_label(orig_set)
    if ns != orig_set: c['set'] = ns; changed['set']+=1
    nr = rarity_label(c.get('rarity', ''), orig_set)   # OP15 check uses the ORIGINAL set
    if nr != c.get('rarity'): c['rarity'] = nr; changed['rarity']+=1
    if c.get('variant') == 'Errata': c['variant'] = 'Normal'; changed['variant']+=1

json.dump(cat, open(F, 'w'), ensure_ascii=False, separators=(',', ':'))
print('rows:', len(cat), '| changes:', dict(changed))
print('sets now:', sorted({c['set'] for c in cat}))
print('rarities now:', sorted({c['rarity'] for c in cat}))
print('variants now:', sorted({c['variant'] for c in cat}))
