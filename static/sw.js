// Nexora AI service worker: network-first (bypassing the HTTP cache) for the app shell, never caches /api.
const CACHE = "nexora-v22";
const SHELL = [
  "/", "/index.html", "/style.css?v=22", "/app.js?v=22", "/config.js",
  "/vendor/marked.min.js", "/vendor/purify.min.js", "/manifest.webmanifest",
  "/icons/icon.svg", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/maskable-512.png",
];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE)
    .then((c) => Promise.all(SHELL.map((u) => fetch(u, { cache: "no-store" }).then((r) => r.ok && c.put(u, r)).catch(() => {}))))
    .then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    const old = (await caches.keys()).filter((k) => k !== CACHE && k !== CACHE + "-media");
    await Promise.all(old.map((k) => caches.delete(k)));
    await self.clients.claim();
    if (old.length) { // upgrading from an older Nexora: reload pages still running the old code
      const wins = await self.clients.matchAll({ type: "window" });
      await Promise.all(wins.map((w) => w.navigate(w.url).catch(() => {})));
    }
  })());
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return;
  if (url.pathname.startsWith("/media/")) {
    e.respondWith(caches.open(CACHE + "-media").then(async (c) => {
      const hit = await c.match(e.request);
      if (hit) return hit;
      const res = await fetch(e.request);
      if (res.ok) await c.put(e.request, res.clone());
      return res;
    }));
    return;
  }
  const fresh = e.request.mode === "navigate"
    ? fetch(e.request.url, { cache: "no-store", credentials: "same-origin" })
    : fetch(new Request(e.request, { cache: "no-store" }));
  e.respondWith(
    fresh.then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
      return res;
    }).catch(() => caches.match(e.request, { ignoreSearch: e.request.mode === "navigate" }).then((r) => r || caches.match("/")))
  );
});
