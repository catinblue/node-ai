/* Node PWA — Stale-While-Revalidate cache for same-origin GETs only.
   Third-party resources (esm.sh, Google Fonts, favicon API, Vercel Analytics)
   bypass the cache and go straight to network. */

const CACHE = 'node-v1';
const PRECACHE = ['/', '/digest.html', '/manifest.json', '/icon.svg'];

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(PRECACHE).catch(() => {}))
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;  // third-party: untouched

  e.respondWith(
    caches.open(CACHE).then((cache) =>
      cache.match(e.request).then((cached) => {
        const fetchP = fetch(e.request)
          .then((resp) => {
            if (resp && resp.ok && resp.type === 'basic') {
              cache.put(e.request, resp.clone());
            }
            return resp;
          })
          .catch(() => cached);
        return cached || fetchP;
      })
    )
  );
});
