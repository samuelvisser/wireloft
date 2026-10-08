import {readFileSync} from 'node:fs'
import {test} from 'node:test'
import assert from 'node:assert/strict'
import {runInNewContext} from 'node:vm'

const publicFile = (name) => new URL(`../public/${name}`, import.meta.url)
const manifest = JSON.parse(readFileSync(publicFile('manifest.webmanifest'), 'utf8'))

function response(body) {
  return {body, ok: true, type: 'basic', clone() { return response(body) }}
}

function workerHarness() {
  const events = new Map()
  const stores = new Map()
  const calls = []
  let offline = false

  const cacheKey = (request) =>
    new URL(typeof request === 'string' ? request : request.url, 'https://wireloft.example').pathname

  function cache(name) {
    if (!stores.has(name)) stores.set(name, new Map())
    const store = stores.get(name)
    return {
      async match(request) { return store.get(cacheKey(request)) },
      async add(request) { store.set(cacheKey(request), response('offline-shell')) },
      async put(request, value) { store.set(cacheKey(request), value) },
      async keys() { return [...store.keys()].map((url) => ({url})) },
      async delete(request) { return store.delete(cacheKey(request)) },
    }
  }
  const caches = {
    open: async (name) => cache(name),
    keys: async () => [...stores.keys()],
    delete: async (name) => stores.delete(name),
  }
  const self = {
    location: {origin: 'https://wireloft.example'},
    addEventListener: (name, callback) => events.set(name, callback),
    skipWaiting: async () => {},
    clients: {claim: async () => {}},
  }
  const fetch = async (request) => {
    const url = request.url
    calls.push(url)
    if (offline) throw new Error('Network unavailable')
    return response('network-' + url)
  }
  runInNewContext(readFileSync(publicFile('sw.js'), 'utf8'), {
    self, caches, fetch, URL,
    Request: class { constructor(url) { this.url = url } },
    Response: {error: () => ({ok: false})},
  })

  async function dispatch(name, request) {
    let pending
    let intercepted
    events.get(name)({
      request,
      waitUntil(promise) { pending = promise },
      respondWith(promise) { intercepted = promise },
    })
    if (pending) await pending
    return intercepted ? intercepted : null
  }

  const request = (path, mode = 'cors', method = 'GET') => ({
    url: 'https://wireloft.example' + path,
    method,
    mode,
  })

  return {dispatch, request, calls, caches, setOffline(value) { offline = value }}
}

test('PWA has correct install metadata and real raster icon dimensions', () => {
  assert.equal(manifest.id, '/')
  assert.equal(manifest.start_url, '/')
  assert.equal(manifest.scope, '/')
  assert.equal(manifest.display, 'standalone')
  for (const [name, size] of [
    ['pwa-icon-180.png', 180],
    ['pwa-icon-192.png', 192],
    ['pwa-icon-512.png', 512],
    ['pwa-maskable-512.png', 512],
  ]) {
    const icon = readFileSync(publicFile(name))
    assert.equal(icon.subarray(0, 8).toString('hex'), '89504e470d0a1a0a')
    assert.equal(icon.readUInt32BE(16), size)
    assert.equal(icon.readUInt32BE(20), size)
  }
  assert.deepEqual(manifest.icons.map((item) => item.sizes), ['192x192', '512x512', '512x512'])
  const html = readFileSync(publicFile('../index.html'), 'utf8')
  assert.match(html, /rel="manifest"/)
  assert.match(html, /rel="apple-touch-icon"/)
})

test('install precaches only the offline document', async () => {
  const worker = workerHarness()
  await worker.dispatch('install')
  assert.deepEqual(await worker.caches.keys(), ['wireloft-offline-v1'])
})

test('API, feeds, config, manifests and cross-origin resources bypass the worker', async () => {
  const worker = workerHarness()
  const bypass = [
    worker.request('/api/pull'),
    worker.request('/api/downloads', 'cors', 'POST'),
    worker.request('/feeds/profile.xml', 'navigate'),
    worker.request('/config.json'),
    worker.request('/manifest.webmanifest'),
    worker.request('/logo-wide-wireloft.png'),
    worker.request('/assets/123.js', 'navigate'),
    {...worker.request('/assets/123.js'), url: 'https://other.example/assets/123.js'},
  ]
  for (const request of bypass) {
    assert.equal(await worker.dispatch('fetch', request), null, request.url)
  }
})

test('hashed assets are cache-first and failed responses are not cached', async () => {
  const worker = workerHarness()
  const request = worker.request('/assets/index-deadbeef.js')
  assert.equal((await worker.dispatch('fetch', request)).body, 'network-' + request.url)
  worker.setOffline(true)
  assert.equal((await worker.dispatch('fetch', request)).body, 'network-' + request.url)
  assert.equal(worker.calls.length, 1)
  await assert.rejects(worker.dispatch('fetch', worker.request('/assets/not-cached.js')), /Network unavailable/)
})

test('online navigations always refetch, offline navigations use the fallback', async () => {
  const worker = workerHarness()
  await worker.dispatch('install')
  const route = worker.request('/show/123/episode/456', 'navigate')
  await worker.dispatch('fetch', route)
  await worker.dispatch('fetch', route)
  assert.equal(worker.calls.length, 2)
  worker.setOffline(true)
  assert.equal((await worker.dispatch('fetch', route)).body, 'offline-shell')
  assert.equal(worker.calls.length, 3)
})

test('service worker does not replace API navigation with offline HTML', async () => {
  const worker = workerHarness()
  await worker.dispatch('install')
  worker.setOffline(true)
  assert.equal(await worker.dispatch('fetch', worker.request('/api/pull', 'navigate')), null)
  assert.equal(await worker.dispatch('fetch', worker.request('/feeds/token.xml', 'navigate')), null)
})

test('activation deletes obsolete WireLoft caches without touching unrelated caches', async () => {
  const worker = workerHarness()
  await worker.caches.open('wireloft-static-v0')
  await worker.caches.open('other-site-cache')
  await worker.dispatch('install')
  await worker.dispatch('activate')
  assert.deepEqual(await worker.caches.keys(), ['other-site-cache', 'wireloft-offline-v1'])
})
