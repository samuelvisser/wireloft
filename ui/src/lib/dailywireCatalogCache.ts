import type {InfiniteData} from '@tanstack/react-query'
import {z} from 'zod'

import {
    DailywireCatalogMoviePageReadSchema,
    DailywireCatalogShowPageReadSchema,
} from '../types/schemas/dailywire_catalog'

// Only the unfiltered Browse catalog is persisted. Search query results stay
// in the React Query memory cache without filling browser storage.
const CATALOG_STORAGE_PREFIX = 'wl_dailywire_browse_v1:'
const CACHE_VERSION = 1

const storedShowsSchema = z.object({
    version: z.literal(CACHE_VERSION),
    pages: z.array(DailywireCatalogShowPageReadSchema).min(1),
    pageParams: z.array(z.number().int().nonnegative()).min(1),
})
const storedMoviesSchema = z.object({
    version: z.literal(CACHE_VERSION),
    pages: z.array(DailywireCatalogMoviePageReadSchema).min(1),
    pageParams: z.array(z.number().int().nonnegative()).min(1),
})

type CatalogPage = {offset: number}
type StoredCatalog<T extends CatalogPage> = {
    version: number
    pages: T[]
    pageParams: number[]
}

function loadCatalog<T extends CatalogPage>(
    key: string,
    schema: {safeParse: (value: unknown) => {success: boolean; data?: StoredCatalog<T>}},
): InfiniteData<T, number> | undefined {
    try {
        const raw = localStorage.getItem(CATALOG_STORAGE_PREFIX + key)
        if (!raw) return undefined

        const parsed = schema.safeParse(JSON.parse(raw))
        if (!parsed.success || !parsed.data) return undefined

        const {pages, pageParams} = parsed.data
        if (
            pages.length !== pageParams.length
            || pageParams[0] !== 0
            || pages.some((page, index) => page.offset !== pageParams[index])
        ) return undefined

        return {pages, pageParams}
    } catch {
        // Browser storage is a best-effort optimization, never a prerequisite.
        return undefined
    }
}

function saveCatalog<T extends CatalogPage>(key: string, data: InfiniteData<T, number>): void {
    try {
        localStorage.setItem(CATALOG_STORAGE_PREFIX + key, JSON.stringify({
            version: CACHE_VERSION,
            pages: data.pages,
            pageParams: data.pageParams,
        }))
    } catch {
        // Storage may be unavailable or full; the in-memory query cache still works.
    }
}

export function loadDailywireShowCatalogFromStorage(grouping: 'host' | 'alphabetical') {
    return loadCatalog('shows:' + grouping, storedShowsSchema)
}

export function saveDailywireShowCatalogToStorage(
    grouping: 'host' | 'alphabetical',
    data: InfiniteData<z.infer<typeof DailywireCatalogShowPageReadSchema>, number>,
): void {
    saveCatalog('shows:' + grouping, data)
}

export function loadDailywireMovieCatalogFromStorage() {
    return loadCatalog('movies', storedMoviesSchema)
}

export function saveDailywireMovieCatalogToStorage(
    data: InfiniteData<z.infer<typeof DailywireCatalogMoviePageReadSchema>, number>,
): void {
    saveCatalog('movies', data)
}
