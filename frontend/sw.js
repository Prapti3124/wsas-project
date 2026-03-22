/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Service Worker (sw.js)
   Basic offline caching for app-like behavior.
   ═══════════════════════════════════════════════════════════════════════════ */
const CACHE_NAME = 'wsas-v1';
const ASSETS = [
  '/',
  '/index.html',
  '/css/style.css',
  '/js/app.js',
  '/js/api.js',
  '/manifest.json'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
  );
});

self.addEventListener('fetch', (e) => {
  e.respondWith(
    caches.match(e.request).then(response => response || fetch(e.request))
  );
});
