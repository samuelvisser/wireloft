// Only immutable, content-hashed build assets are cached. Never cache the
// authenticated API, feeds, runtime config, or the HTML app shell.
const STATIC_CACHE = 'wireloft-static-v1'
const OFFLINE_CACHE = 'wireloft-offline-v1'
const OFFLINE_PAGE = '/offline.html'
const MAX_STATIC_ENTRIES = 160

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(OFFLINE_CACHE)
    await cache.add(new Request(OFFLINE_PAGE, {cache: 'reload'}))
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith('wireloft-') && key !== STATIC_CACHE && key !== OFFLINE_CACHE) {
        await caches.delete(key)
      }
    }
    await self.clients.claim()
  })())
})

function isAppNavigation(request, url) {
  if (request.mode !== 'navigate') return false
  // Never replace a feed/API request with HTML, even when opened in a browser tab.
  if (['/api', '/feeds', '/assets'].some((path) => url.pathname === path || url.pathname.startsWith(path + '/'))) {
    return false
  }
  // Static resources are not React routes.
  return !/\.(?:html|json|webmanifest|js|css|png|jpg|jpeg|svg|ico|woff2?)$/i.test(url.pathname)
}

async function cacheStaticAsset(request) {
  const cache = await caches.open(STATIC_CACHE)
  const cached = await cache.match(request)
  if (cached) return cached

  const response = await fetch(request)
  if (response.ok && response.type === 'basic') {
    await cache.put(request, response.clone())
    const entries = await cache.keys()
    for (const oldEntry of entries.slice(0, -MAX_STATIC_ENTRIES)) {
      await cache.delete(oldEntry)
    }
  }
  return response
}

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  if (isAppNavigation(request, url)) {
    // The current HTML must always come from the server when online. Serving
    // cached index.html would cause version-reload loops after a deployment.
    event.respondWith(
      fetch(request).catch(async () =>
        (await caches.open(OFFLINE_CACHE)).match(OFFLINE_PAGE) || Response.error(),
      ),
    )
  } else if (request.mode !== 'navigate' && url.pathname.startsWith('/assets/')) {
    event.respondWith(cacheStaticAsset(request))
  }
})
