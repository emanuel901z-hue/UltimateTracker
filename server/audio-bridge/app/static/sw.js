// Service Worker – PWA + Web-Push für die Eltern-UI.
//
// Aufgaben:
//  * Push-Nachrichten der Bridge anzeigen (neue Sprachnachricht, Suchmodus)
//  * Klick auf die Benachrichtigung öffnet/fokussiert die UI
//  * Minimaler Offline-Cache der Startseite

const CACHE = 'ut-shell-v1';
const SHELL = ['/', '/manifest.webmanifest'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // Nur die Startseite aus dem Cache bedienen; API-Aufrufe immer live.
  if (event.request.method !== 'GET' || new URL(event.request.url).pathname !== '/') return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put('/', copy));
        return response;
      })
      .catch(() => caches.match('/'))
  );
});

self.addEventListener('push', (event) => {
  let payload = { title: 'UltimateTracker', body: 'Neue Nachricht' };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch (err) {
    if (event.data) payload.body = event.data.text();
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      tag: 'ultimatetracker',
      renotify: true,
      data: { url: '/' },
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ('focus' in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    })
  );
});
