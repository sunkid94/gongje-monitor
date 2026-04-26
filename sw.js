// OneSignal Web Push SDK — 푸시 알림 수신 처리
importScripts('https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js');

// CACHE 이름을 바꾸면 기존 PWA 사용자의 캐시가 다음 SW activate 단계에서 폐기됨.
// 배포 후 사용자에게 즉시 새 버전을 보이려면 이 버전을 올리세요.
const CACHE = 'cig-monitor-v2';
const CORE = ['./logo.png', './manifest.webmanifest', './icons/icon-192.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  const isDocument = req.mode === 'navigate' || req.destination === 'document';
  const isFreshAlways = isDocument
    || url.pathname.endsWith('articles.json')
    || url.pathname.endsWith('index.html')
    || url.pathname.endsWith('.html')
    || url.pathname.endsWith('.js')
    || url.pathname.endsWith('.css')
    || url.pathname.endsWith('.webmanifest');

  if (isFreshAlways) {
    // network-first — 배포 변경분이 즉시 보이도록, 오프라인 시 캐시 폴백
    e.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((cached) => cached || caches.match('./')))
    );
    return;
  }

  // 그 외 (이미지·아이콘 등)는 cache-first
  e.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      });
    })
  );
});
