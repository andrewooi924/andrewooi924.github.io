/* Most Wanted service worker.
   - Precache the app shell so the app opens offline (fetched fresh, bypassing HTTP cache).
   - catalog.json + navigations: NETWORK-FIRST so a new deploy shows immediately when online,
     falling back to cache when offline. (Fixes stale catalog / English-name search after deploy.)
   - Card images: cache-first so wishlist art survives offline.
   Bump CACHE when you ship a new app version. */

const CACHE = 'most-wanted-v22';
const IMG_CACHE = 'mw-images-v22';
const SHELL = [
  './',
  './index.html',
  './manifest.webmanifest',
  './catalog.json',
  './icon-192.png',
  './icon-512.png',
  './apple-touch-icon.png'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c =>
      // {cache:'reload'} forces a fresh network copy, never the browser HTTP cache.
      Promise.all(SHELL.map(u => fetch(u, { cache: 'reload' })
        .then(res => c.put(u, res)).catch(() => {})))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE && k !== IMG_CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('message', e => { if (e.data === 'skip-waiting') self.skipWaiting(); });

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Card images (Bandai CDN + Yuyutei) — cache-first, keep opaque responses too.
  const isCardImg = (url.hostname.endsWith('onepiece-cardgame.com') || url.hostname.endsWith('yuyu-tei.jp'))
    && /\.(jpg|jpeg|png|webp)$/.test(url.pathname);
  if (isCardImg) {
    e.respondWith(
      caches.open(IMG_CACHE).then(async cache => {
        const hit = await cache.match(req);
        if (hit) return hit;
        try {
          const res = await fetch(req, { mode: 'no-cors' });
          cache.put(req, res.clone());
          return res;
        } catch (_) {
          return hit || Response.error();
        }
      })
    );
    return;
  }

  // The catalog + navigations — NETWORK-FIRST: newest data when online, cache when offline.
  const isCatalog = url.origin === self.location.origin && url.pathname.endsWith('/catalog.json');
  if (req.mode === 'navigate' || isCatalog) {
    e.respondWith(
      fetch(req).then(res => {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(isCatalog ? req : './index.html', copy));
        return res;
      }).catch(() => caches.match(isCatalog ? req : './index.html').then(h => h || caches.match('./index.html')))
    );
    return;
  }

  // Other same-origin assets (icons, manifest) — cache-first, refresh in background.
  if (url.origin === self.location.origin) {
    e.respondWith(
      caches.match(req).then(hit => {
        const net = fetch(req).then(res => {
          caches.open(CACHE).then(c => c.put(req, res.clone()));
          return res;
        }).catch(() => hit);
        return hit || net;
      })
    );
  }
});
