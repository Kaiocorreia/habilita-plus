const CACHE = "habilita-plus-v1";
const ESSENCIAIS = [
    "/static/css/style.css",
    "/static/icons/icone-192.png",
    "/static/icons/icone-512.png",
];

self.addEventListener("install", (evento) => {
    evento.waitUntil(
        caches.open(CACHE).then((cache) => cache.addAll(ESSENCIAIS))
    );
    self.skipWaiting();
});

self.addEventListener("activate", (evento) => {
    evento.waitUntil(
        caches.keys().then((chaves) =>
            Promise.all(chaves.filter((c) => c !== CACHE).map((c) => caches.delete(c)))
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", (evento) => {
    if (evento.request.method !== "GET") {
        return;
    }

    evento.respondWith(
        fetch(evento.request).catch(() => caches.match(evento.request))
    );
});
