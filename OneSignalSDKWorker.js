// 폐기됨. OneSignal에서 표준 Web Push(VAPID)로 전환.
// 이 SW는 자기 자신을 unregister하여 새로 등록되는 sw.js로 자리를 양보합니다.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    try {
      await self.registration.unregister();
      const clients = await self.clients.matchAll({ type: 'window' });
      clients.forEach((c) => { try { c.navigate(c.url); } catch (_) {} });
    } catch (_) {}
  })());
});
