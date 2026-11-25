// Pode Abrir service worker: installability and push notifications only.
// It deliberately has NO fetch handler and caches nothing, so documents (even encrypted) and
// API responses never persist on the device through it.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = { title: "Pode Abrir", body: "", url: "/compartilhamentos/" };
  try {
    data = { ...data, ...event.data.json() };
  } catch {
    // Malformed payload: show the generic notification.
  }
  event.waitUntil(self.registration.showNotification(data.title, {
    body: data.body, icon: "/icon-192.png", badge: "/icon-192.png", tag: "podeabrir", data: { url: data.url },
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
