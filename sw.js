// Service worker do Estoque — faz o app abrir mesmo sem internet.
// Estratégia: cacheia a "casca" (o próprio index.html e ícones).
// Os DADOS não passam por aqui: quem cuida deles é o Firebase, que tem
// a própria fila offline e sobe as alterações sozinho quando a conexão volta.
const CACHE="estoque-shell-v1";
const SHELL=[
  "./",
  "./index.html",
  "./manifest.json",
  "./icon-180.png",
  "./icon-192.png",
  "./icon-512.png"
];

self.addEventListener("install",e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).catch(()=>{}));
  self.skipWaiting();
});

self.addEventListener("activate",e=>{
  e.waitUntil(
    caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch",e=>{
  const url=new URL(e.request.url);
  // Nunca interceptar Firebase, Google, CDNs ou APIs — só a casca local.
  if(url.origin!==self.location.origin) return;
  if(e.request.method!=="GET") return;
  // Network-first para o index (pega atualizações), com cache de reserva offline.
  e.respondWith(
    fetch(e.request)
      .then(resp=>{
        const copy=resp.clone();
        caches.open(CACHE).then(c=>c.put(e.request,copy)).catch(()=>{});
        return resp;
      })
      .catch(()=>caches.match(e.request).then(r=>r||caches.match("./index.html")))
  );
});
