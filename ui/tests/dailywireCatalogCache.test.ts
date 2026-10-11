import {strict as assert} from 'node:assert'
import {beforeEach, test} from 'node:test'

import {
    loadDailywireMovieCatalogFromStorage,
    loadDailywireShowCatalogFromStorage,
    saveDailywireMovieCatalogToStorage,
    saveDailywireShowCatalogToStorage,
} from '../src/lib/dailywireCatalogCache'

const cache = new Map<string, string>()
const storage = {
    getItem: (key: string) => cache.get(key) ?? null,
    setItem: (key: string, value: string) => { cache.set(key, value) },
}

beforeEach(() => {
    cache.clear()
    Object.defineProperty(globalThis, 'localStorage', {configurable: true, value: storage})
})

const showPage = {
    items: [{dwId: 'show-1', slug: 'first-show', title: 'First Show'}],
    offset: 0,
    limit: 24,
    total: 1,
    hasMore: false,
}
const moviePage = {
    items: [{dwId: 'movie-1', slug: 'first-movie', title: 'First Movie'}],
    offset: 0,
    limit: 24,
    total: 1,
    hasMore: false,
}

test('unfiltered Browse pages survive a reload and stay separate by catalog and grouping', () => {
    saveDailywireShowCatalogToStorage('host', {pages: [showPage], pageParams: [0]})
    saveDailywireMovieCatalogToStorage({pages: [moviePage], pageParams: [0]})

    assert.deepEqual(loadDailywireShowCatalogFromStorage('host')?.pages[0].items, showPage.items)
    assert.equal(loadDailywireShowCatalogFromStorage('alphabetical'), undefined)
    assert.deepEqual(loadDailywireMovieCatalogFromStorage()?.pages[0].items, moviePage.items)
})

test('cached infinite-query pages and page parameters are restored together', () => {
    const nextPage = {
        ...showPage,
        offset: 24,
        total: 25,
        items: [{dwId: 'show-25', slug: 'later-show', title: 'Later Show'}],
    }
    saveDailywireShowCatalogToStorage('alphabetical', {
        pages: [{...showPage, total: 25, hasMore: true}, nextPage],
        pageParams: [0, 24],
    })

    const restored = loadDailywireShowCatalogFromStorage('alphabetical')
    assert.deepEqual(restored?.pageParams, [0, 24])
    assert.equal(restored?.pages[1].items[0].slug, 'later-show')
})

test('corrupt cache entries are ignored rather than disrupting Browse', () => {
    storage.setItem('wl_dailywire_browse_v1:movies', '{invalid json')
    assert.equal(loadDailywireMovieCatalogFromStorage(), undefined)

    storage.setItem('wl_dailywire_browse_v1:movies', JSON.stringify({
        version: 1,
        pages: [moviePage],
        pageParams: [24],
    }))
    assert.equal(loadDailywireMovieCatalogFromStorage(), undefined)
})

test('failed browser storage writes do not prevent the catalog from loading', () => {
    Object.defineProperty(globalThis, 'localStorage', {
        configurable: true,
        value: {getItem: () => null, setItem: () => {throw new Error('Quota exceeded')}},
    })

    assert.doesNotThrow(() => {
        saveDailywireMovieCatalogToStorage({pages: [moviePage], pageParams: [0]})
    })
    assert.equal(loadDailywireMovieCatalogFromStorage(), undefined)
})

test('a successful refresh replaces the previously stored catalog', () => {
    saveDailywireMovieCatalogToStorage({pages: [moviePage], pageParams: [0]})
    const refreshedPage = {
        ...moviePage,
        total: 2,
        items: [
            ...moviePage.items,
            {dwId: 'movie-2', slug: 'new-movie', title: 'New Movie'},
        ],
    }
    saveDailywireMovieCatalogToStorage({pages: [refreshedPage], pageParams: [0]})

    assert.equal(loadDailywireMovieCatalogFromStorage()?.pages[0].items.length, 2)
})

test('outdated cache formats are ignored', () => {
    storage.setItem('wl_dailywire_browse_v1:movies', JSON.stringify({
        version: 0,
        pages: [moviePage],
        pageParams: [0],
    }))
    assert.equal(loadDailywireMovieCatalogFromStorage(), undefined)
})
