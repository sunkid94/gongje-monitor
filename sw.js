// 구형 SW 자리. 새 SW(OneSignalSDKWorker.js)로 대체 중.
// 이 SW는 자기 자신을 즉시 unregister하여 OneSignal SDK가 OneSignalSDKWorker.js를 새로 등록하도록 비켜줍니다.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    try {
      const reg = await self.registration.unregister();
      const clients = await self.clients.matchAll({ type: 'window' });
      clients.forEach((c) => c.navigate(c.url));
    } catch (_) {}
  })());
});
