const CACHE_NAME = "flight-monitor-v1";
const ASSET_LIST = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png"
];

self.addEventListener("install", function (event) {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(ASSET_LIST).catch(function () { /* jangan gagal install cuma gara2 1 aset */ });
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE_NAME; }).map(function (k) { return caches.delete(k); })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request).then(function (cached) {
      var jaringan = fetch(event.request)
        .then(function (resp) {
          if (resp && resp.ok) {
            var salinan = resp.clone();
            caches.open(CACHE_NAME).then(function (cache) { cache.put(event.request, salinan); });
          }
          return resp;
        })
        .catch(function () { return cached; });
      return cached || jaringan;
    })
  );
});

// ---------- notifikasi push (ini yang bikin muncul di status bar HP) ----------
self.addEventListener("push", function (event) {
  var data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = {}; }

  var judul = data.title || "Flight Monitor";
  var opsi = {
    body: data.body || "Ada update penerbangan.",
    icon: "/static/icon-192.png",
    badge: "/static/icon-192.png",
    tag: data.nomor || "flight-monitor",
    vibrate: [200, 100, 200]
  };

  event.waitUntil(self.registration.showNotification(judul, opsi));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: "window" }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        if ("focus" in list[i]) return list[i].focus();
      }
      if (clients.openWindow) return clients.openWindow("/");
    })
  );
});
