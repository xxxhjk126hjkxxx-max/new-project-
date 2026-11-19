// Bump the version whenever the app shell or one of its bundled assets changes.
const PREFIX = 'iua-offline-shell-';
const CACHE = PREFIX + 'v3';
const SHELL = new Set([
  '/', '/student', '/student-offline.html',
  ...[
    'app.css', 'leader.js', 'db.js', 'qr-code.js', 'student.js', 'manifest.webmanifest', 'student.webmanifest',
    'icon.svg', 'icon-192.png', 'icon-512.png', 'vendor/qrcode.js', 'vendor/jsqr.js',
  ].map(name => '/offline-assets/' + name),
]);

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll(Array.from(SHELL, url => new Request(url, {cache: 'reload'})));
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key.startsWith(PREFIX) && key !== CACHE).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const {request} = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || !SHELL.has(url.pathname)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    return (await cache.match(url.pathname)) || fetch(request);
  })());
});
