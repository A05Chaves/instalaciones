const CACHE = "sesur-tecnico-v1";
const SHELL = [
  "{% url 'portal_tecnico' %}",
  "/static/sesur/css/portal_tecnico.css",
  "/static/sesur/js/portal_tecnico.js",
  "/static/sesur/img/logosesur.png"
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET" || event.request.url.includes("/api/")) return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith(
    fetch(event.request).then(response => {
      const copia = response.clone();
      caches.open(CACHE).then(cache => cache.put(event.request, copia));
      return response;
    }).catch(() => caches.match(event.request).then(response => response || caches.match("{% url 'portal_tecnico' %}")))
  );
});
