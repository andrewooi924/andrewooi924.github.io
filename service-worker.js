/* Most Wanted service worker.
   - Precache the app shell + catalog so the app opens offline.
   - Runtime cache-first for Yuyutei card images so wishlist art survives offline.
   - Network-first for navigation so updates land when online, cache when not.
   Bump CACHE when you ship a new catalog.json or app version. */

const CACHE = 'most-wanted-v9';
const IMG_CACHE = 'mw-images-v9';
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
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE && k !== IMG_CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Card images (official Bandai CDN + Yuyutei) — cache-first, store opaque too.
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

  // Same-origin navigations — network-first, fall back to cached shell.
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('./index.html')));
    return;
  }

  // Same-origin assets (incl. catalog.json) — cache-first, refresh in background.
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
