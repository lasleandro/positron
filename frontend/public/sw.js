// pode abrir service worker: installability, push notifications and an offline page.
// It caches exactly one static file (/offline.html, which contains no data). API responses,
// documents (even encrypted) and app pages are never cached: every request goes to the network.
const CACHE = "podeabrir-offline-v1";
const OFFLINE_URL = "/offline.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.add(new Request(OFFLINE_URL, { cache: "reload" })))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

// Only page navigations are intercepted, and only to show the offline page when the network
// is unreachable. Everything else (API, documents, assets) passes through untouched.
self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.mode !== "navigate" || request.method !== "GET") return;
  event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
});

self.addEventListener("push", (event) => {
  let data = { title: "pode abrir", body: "", url: "/compartilhamentos/" };
  try {
    data = { ...data, ...event.data.json() };
  } catch {
    // Malformed payload: show the generic notification.
  }
  event.waitUntil(self.registration.showNotification(data.title, {
    body: data.body, icon: "/icon-192.png", badge: "/brand/badge-128.png", tag: "podeabrir", data: { url: data.url },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
    const open = windows.find((client) => client.url.startsWith(self.location.origin));
    if (open) return open.navigate(url).then((client) => client?.focus());
    return self.clients.openWindow(url);
  }));
});
