"""Map each catalog card to your own HD image and write image_map.json.

Expected layout (each set in its own folder):
    images/OP01/OP01-120.png        <- Normal (base id)
    images/OP01/OP01-120_p1.png     <- Parallel  (a "_pN" suffix)
    images/OP01/OP01-120_p2.png     <- Super Parallel (the LARGER N)
    images/ST01/...  images/PROMO/...  images/EB01/...  etc.

Rules used (your described convention):
    Normal          -> the base file  CODE.<ext>
    Parallel/other  -> the smaller "_pN" files, in ascending N
    Super Parallel  -> the largest "_pN" file(s)

Anything it can't place confidently is written to unmapped.csv for you to fix by
hand in manual_map.json (which is merged on top, so manual always wins).

Run it next to catalog.json with your images/ folder beside it:
    python map_images.py            # writes image_map.json + unmapped.csv
    python map_images.py --dry-run  # report only, write nothing
"""
import json, os, re, csv, sys, collections

CATALOG   = 'catalog.json'
IMAGES    = 'images'
EXTS      = ('.png', '.jpg', '.jpeg', '.webp')
DRY       = '--dry-run' in sys.argv

# A set label can map to several folders (the card's code picks the right one).
# Your PROMO cards live in either images/PROMO or images/LIMITED, so search both.
SET_FOLDERS = {'PROMO': ['PROMO', 'LIMITED']}

cat = json.load(open(CATALOG, encoding='utf-8'))

def folders_for(setlabel):
    # A set can map to several folders; the card's code decides which one actually holds it.
    return SET_FOLDERS.get(setlabel, [setlabel])

def scan(folder):
    """folder -> { code: {'base': filename|None, 'p': [(N, filename), ...] } } (p sorted by N)."""
    idx = collections.defaultdict(lambda: {'base': None, 'p': []})
    d = os.path.join(IMAGES, folder)
    if not os.path.isdir(d):
        return None
    for fn in sorted(os.listdir(d)):
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in EXTS:
            continue
        m = re.match(r'^(?P<code>.+?)_p(?P<n>\d+)$', stem)   # CODE_pN
        if m:
            idx[m.group('code')]['p'].append((int(m.group('n')), fn))
        else:
            idx[stem]['base'] = fn
    for k in idx:
        idx[k]['p'].sort()
    return idx

# group catalog rows by (set, code)
groups = collections.defaultdict(list)
for c in cat:
    groups[(c['set'], c['code'])].append(c)

folder_cache = {}
missing_folders = set()
mapping, unmapped = {}, []

def get_idx(folder):
    if folder not in folder_cache:
        folder_cache[folder] = scan(folder)
    return folder_cache[folder]

def rel(folder, fn):
    return f"{IMAGES}/{folder}/{fn}"

for (setlabel, code), rows in groups.items():
    cands = folders_for(setlabel)
    # find the first candidate folder that actually contains this code
    folder, files = None, None
    all_missing = True
    for cand in cands:
        idx = get_idx(cand)
        if idx is None:
            continue
        all_missing = False
        if code in idx and (idx[code]['base'] or idx[code]['p']):
            folder, files = cand, idx[code]
            break
    if files is None:
        if all_missing:
            for c in cands: missing_folders.add(c)
        for r in rows:
            unmapped.append((r, 'no file in ' + '/'.join('images/' + c for c in cands), '', ''))
        continue

    base = files['base']
    ps   = [fn for _, fn in files['p']]            # ascending N

    normals = [r for r in rows if r['variant'] == 'Normal']
    supers  = [r for r in rows if r['variant'] == 'Super Parallel']
    others  = [r for r in rows if r['variant'] in ('Parallel', 'Foil / Stamped', 'Errata')]

    # Normal -> base
    for r in normals:
        if base: mapping[r['id']] = rel(folder, base)
        else:    unmapped.append((r, 'no base file', base or '', ' '.join(ps)))

    # Super Parallel -> largest N(s); the rest of the _pN go to parallels (ascending)
    n_sp = len(supers)
    sp_files  = list(reversed(ps[len(ps) - n_sp:])) if 0 < n_sp <= len(ps) else []
    par_files = ps[:len(ps) - n_sp] if n_sp <= len(ps) else []

    for i, r in enumerate(supers):
        if i < len(sp_files): mapping[r['id']] = rel(folder, sp_files[i])
        else:                 unmapped.append((r, 'no super-parallel file', base or '', ' '.join(ps)))
    for i, r in enumerate(others):
        if i < len(par_files): mapping[r['id']] = rel(folder, par_files[i])
        else:                  unmapped.append((r, 'no parallel file', base or '', ' '.join(ps)))

# merge manual overrides (manual wins) so re-running never clobbers your fixes
if os.path.exists('manual_map.json'):
    manual = json.load(open('manual_map.json', encoding='utf-8'))
    for k, v in manual.items():
        mapping[k] = v
        unmapped = [u for u in unmapped if u[0]['id'] != k]

# ---- report ----
by_variant = collections.Counter(r['variant'] for r, *_ in unmapped)
print(f"cards: {len(cat)} | mapped: {len(mapping)} | unmapped: {len(unmapped)}")
if missing_folders:
    print("missing folders:", ', '.join(sorted(missing_folders)))
print("unmapped by variant:", dict(by_variant))

# show a few worked examples so you can sanity-check the heuristic
shown = 0
for (setlabel, code), rows in groups.items():
    idx = None
    for cand in folders_for(setlabel):
        ix = folder_cache.get(cand)
        if ix and code in ix: idx = ix; break
    if not idx or code not in idx: continue
    f = idx[code]
    if not f['p']: continue
    print(f"  e.g. {setlabel}/{code}: base={f['base']} parallels={[fn for _,fn in f['p']]}")
    for r in rows:
        print(f"        {r['variant']:14} -> {mapping.get(r['id'],'(unmapped)')}")
    shown += 1
    if shown >= 4: break

if not DRY:
    json.dump(mapping, open('image_map.json', 'w'), ensure_ascii=False, separators=(',', ':'))
    with open('unmapped.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['id', 'set', 'code', 'variant', 'reason', 'base_file', 'parallel_files'])
        for r, reason, base, ps in unmapped:
            w.writerow([r['id'], r['set'], r['code'], r['variant'], reason, base, ps])
    print("wrote image_map.json and unmapped.csv")
else:
    print("(dry run — nothing written)")
