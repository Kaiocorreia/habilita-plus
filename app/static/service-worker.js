// Versão do cache: mude a cada deploy que altere estes arquivos.
const CACHE = "habilita-plus-v2";
const PAGINA_OFFLINE = "/offline";
const ESSENCIAIS = [
    PAGINA_OFFLINE,
    "/static/css/style.css",
    "/static/js/app.js",
    "/static/icons/icone-192.png",
    "/static/icons/icone-512.png",
];

self.addEventListener("install", (evento) => {
    evento.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ESSENCIAIS)));
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
    const pedido = evento.request;
    if (pedido.method !== "GET" || new URL(pedido.url).origin !== self.location.origin) {
        return;
    }

    // Páginas: sempre da rede (horários e agendamentos mudam a todo momento).
    // Sem conexão, mostra a página offline em vez do erro do navegador.
    if (pedido.mode === "navigate") {
        evento.respondWith(fetch(pedido).catch(() => caches.match(PAGINA_OFFLINE)));
        return;
    }

    // Arquivos estáticos: rede primeiro, cache como reserva.
    evento.respondWith(fetch(pedido).catch(() => caches.match(pedido, { ignoreSearch: true })));
});
