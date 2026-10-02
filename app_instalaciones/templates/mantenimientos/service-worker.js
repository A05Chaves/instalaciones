const CACHE = "sesur-tecnico-v18";
const SHELL = [
  "{% url 'portal_tecnico' %}",
  "/static/sesur/css/portal_tecnico.css?v=18",
  "/static/sesur/js/session_activity.js?v=18",
  "/static/sesur/js/portal_tecnico.js?v=18",
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

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const destino = (event.notification.data && event.notification.data.url) || "{% url 'portal_tecnico' %}";
  event.waitUntil(
    clients.matchAll({type: "window", includeUncontrolled: true}).then(ventanas => {
      const abierta = ventanas.find(ventana => "focus" in ventana);
      if (abierta) {
        abierta.navigate(destino);
        return abierta.focus();
      }
      return clients.openWindow(destino);
    })
  );
});
