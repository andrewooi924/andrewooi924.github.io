# Most Wanted — OPTCG hunt list (PWA)

A local-first wishlist + price app for One Piece Card Game cards on the Japanese
market. Installs to an iPhone/Android home screen, works fully offline, no server.

## Files
- `index.html`           the app (UI + logic)
- `manifest.webmanifest` home-screen install metadata
- `service-worker.js`    offline engine (caches app, catalog, and card images)
- `catalog.json`         the card data — built from your scraper + price database
- `icon-*.png`, `apple-touch-icon.png`  app icons

## Rebuilding the catalog
When you re-scrape prices, regenerate the catalog from your pipeline output:

    python yyt_scrapper.py          # -> yuyutei_listings.json (rarity + variants)
    python build_price_database.py  # -> price_database.json
    python make_catalog.py          # -> catalog.json  (drop next to index.html)

Then bump the `CACHE` name in `service-worker.js` (e.g. v1 -> v2) so phones pull
the new data on next open.

## Run / install
A service worker needs https (or localhost). Two easy paths:

Local test:
    python3 -m http.server 8099
    # open http://localhost:8099 on your computer

On your phone:
1. Host the folder anywhere static + https (GitHub Pages, Netlify, Cloudflare
   Pages, Vercel — all free and drag-and-drop).
2. Open the URL in Safari (iOS) or Chrome (Android).
3. Share -> "Add to Home Screen". It now launches full-screen and runs offline.

## How the four requirements map
1. Wishlists      — tap + on any card; set High/Medium/Low priority + a note.
2. Offline        — the app caches itself + the catalog; "Save offline" pre-caches
                    your wishlist's card images so the list works with no signal.
3. Sort/filter    — color, rarity, set, type, price range, search; wishlist sorts
                    by priority/price/name/set and filters by priority.
4. Sync/backup    — "Backup" exports a JSON file (also CSV); "Restore" merges or
                    replaces from a file. Stash the backup in iCloud/Drive to move
                    between devices.

## Want live multi-device sync later?
File backup covers transfer today. Real-time sync (edit on phone, see on laptop
instantly) needs a small backend — Supabase or Firebase both drop in cleanly with
the existing data model (each wishlist item already has a stable `id`). That's the
one piece that can't be purely local.
