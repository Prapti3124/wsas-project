/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Service Worker (sw.js)
   Network-First strategy for development/production.
   ═══════════════════════════════════════════════════════════════════════════ */
const CACHE_NAME = 'sakhi-v3-final';
const ASSETS = [
  '/',
  '/index.html?v=3',
  '/css/sakhi-v2.css',
  '/assets/sakhi-identity.png',
  '/js/app.js?v=3',
  '/js/api.js?v=3',
  '/manifest.json'
];

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)));
    }).then(() => self.clients.claim())
  );
});

// Network-First Strategy
self.addEventListener('fetch', (e) => {
  // Only cache GET requests
  if (e.request.method !== 'GET') return;
  
  e.respondWith(
    fetch(e.request).then(response => {
      // Clone response and update cache
      const resClone = response.clone();
      caches.open(CACHE_NAME).then(cache => {
        cache.put(e.request, resClone);
      });
      return response;
    }).catch(() => {
      return caches.match(e.request);
    })
  );
});
