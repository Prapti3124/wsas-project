/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Service Worker (sw.js)
   Network-First strategy + Background Sync for offline SOS.
   ═══════════════════════════════════════════════════════════════════════════ */
const CACHE_NAME = 'sakhi-v5-cache-reset';
const ASSETS = [
  '/',
  '/index.html',
  '/css/sakhi-v2.css',
  '/js/app.js',
  '/js/api.js',
  '/js/map.js',
  '/js/voice.js',
  '/js/shake.js',
  '/js/charts.js',
  '/manifest.json',
  '/assets/sakhi-bare-logo.png'
];

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS).catch(err => {
      console.warn('[SW] Some assets failed to pre-cache:', err);
    }))
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)));
    }).then(() => self.clients.claim())
  );
});

// ── Network-First Strategy ───────────────────────────────────────────────────
self.addEventListener('fetch', (e) => {
  // Only cache GET requests; skip cross-origin API calls from Twilio/OSRM
  if (e.request.method !== 'GET') return;

  e.respondWith(
    fetch(e.request).then(response => {
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

// ── Background Sync – Replay Queued SOS Alerts ───────────────────────────────
self.addEventListener('sync', (e) => {
  if (e.tag === 'sos-pending') {
    e.waitUntil(replayPendingAlerts());
  }
});

async function replayPendingAlerts() {
  // We need to communicate with the active page to use its JWT token.
  // Broadcast a message to all open clients to trigger replayQueuedAlerts().
  const clients = await self.clients.matchAll({ includeUncontrolled: true, type: 'window' });
  clients.forEach(client => {
    client.postMessage({ type: 'REPLAY_SOS_QUEUE' });
  });
}

// Listen for messages from the page (e.g. force cache refresh requests)
self.addEventListener('message', (e) => {
  if (e.data && e.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
