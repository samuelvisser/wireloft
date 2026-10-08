import {useEffect, useMemo} from 'react'
import {
    type InfiniteData,
    type QueryClient,
    useInfiniteQuery,
    useQueryClient,
} from '@tanstack/react-query'

export type LazyCollectionPage<T> = {
    items: T[]
    total: number
    offset: number
    limit: number
    hasMore: boolean
    revision?: string
    facets?: Record<string, number>
    actions?: Record<string, number>
}

export type LazyCollectionPageRequest = {
    offset: number
    limit: number
}


export function nextLazyCollectionPageRequest<T>(
    lastPage: LazyCollectionPage<T>,
    pages: readonly LazyCollectionPage<T>[],
    initialCount: number,
    batchSize: number,
): LazyCollectionPageRequest | undefined {
    if (!lastPage.hasMore) return undefined
    const loaded = pages.reduce((total, page) => total + page.items.length, 0)
    const missingInitial = Math.max(0, initialCount - loaded)
    return {
        offset: lastPage.offset + lastPage.items.length,
        limit: missingInitial > 0 ? missingInitial : batchSize,
    }
}

type LazyCollectionOptions<T extends {id: number}> = {
    queryKey: readonly unknown[]
    collectionPrefix: readonly unknown[]
    initialCount: number
    batchSize: number
    enabled?: boolean
    pollIntervalMs?: number
    pollWhilePageCountAtMost?: number
    /**
     * Derive observer-only initial rows from compatible cached collections.
     * React Query still treats the target collection as unfetched and runs its
     * own query immediately; the authoritative response replaces this data.
     */
    derivePlaceholderData?: (
        queryClient: QueryClient,
    ) => InfiniteData<LazyCollectionPage<T>, LazyCollectionPageRequest> | undefined
    fetchPage: (request: LazyCollectionPageRequest, signal?: AbortSignal) => Promise<LazyCollectionPage<T>>
}

function replaceEntitiesInCollection<T extends {id: number}>(
    data: InfiniteData<LazyCollectionPage<T>, LazyCollectionPageRequest> | undefined,
    replacements: Map<number, T>,
) {
    if (!data || replacements.size === 0) return data
    let changed = false
    const pages = data.pages.map((page) => {
        let pageChanged = false
        const items = page.items.map((item) => {
            const replacement = replacements.get(item.id)
            if (!replacement || replacement === item) return item
            pageChanged = true
            return replacement
        })
        if (!pageChanged) return page
        changed = true
        return {...page, items}
    })
    return changed ? {...data, pages} : data
}

export function syncLazyCollectionEntities<T extends {id: number}>(
    queryClient: QueryClient,
    collectionPrefix: readonly unknown[],
    items: readonly T[],
) {
    const replacements = new Map(items.map((item) => [item.id, item]))
    for (const item of items) {
        queryClient.setQueryData([...collectionPrefix, 'entity', item.id], item)
    }
    queryClient.setQueriesData<InfiniteData<LazyCollectionPage<T>, LazyCollectionPageRequest>>(
        {queryKey: [...collectionPrefix, 'list']},
        (data) => replaceEntitiesInCollection(data, replacements),
    )
}

export function updateLazyCollectionEntities<T extends {id: number}>(
    queryClient: QueryClient,
    collectionPrefix: readonly unknown[],
    update: (item: T) => T,
) {
    queryClient.setQueriesData<InfiniteData<LazyCollectionPage<T>, LazyCollectionPageRequest>>(
        {queryKey: [...collectionPrefix, 'list']},
        (data) => {
            if (!data) return data
            let changed = false
            const pages = data.pages.map((page) => {
                let pageChanged = false
                const items = page.items.map((item) => {
                    const next = update(item)
                    if (next === item) return item
                    pageChanged = true
                    return next
                })
                if (!pageChanged) return page
                changed = true
                return {...page, items}
            })
            return changed ? {...data, pages} : data
        },
    )
}

export function useLazyCollection<T extends {id: number}>({
    queryKey,
    collectionPrefix,
    initialCount,
    batchSize,
    enabled = true,
    pollIntervalMs,
    pollWhilePageCountAtMost,
    derivePlaceholderData,
    fetchPage,
}: LazyCollectionOptions<T>) {
    const queryClient = useQueryClient()
    const queryKeySignature = JSON.stringify([...collectionPrefix, 'list', ...queryKey])
    const fullQueryKey = useMemo(
        () => [...collectionPrefix, 'list', ...queryKey] as const,
        // Collection descriptors are normalized JSON-compatible values. Keep the
        // query-key reference stable when only the caller's array identity changes.
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [queryKeySignature],
    )

    const query = useInfiniteQuery<
        LazyCollectionPage<T>,
        Error,
        InfiniteData<LazyCollectionPage<T>, LazyCollectionPageRequest>,
        readonly unknown[],
        LazyCollectionPageRequest
    >({
        queryKey: fullQueryKey,
        enabled,
        initialPageParam: {offset: 0, limit: initialCount},
        placeholderData: derivePlaceholderData
            ? () => derivePlaceholderData(queryClient)
            : undefined,
        queryFn: async ({pageParam, signal}) => {
            const page = await fetchPage(pageParam, signal)
            syncLazyCollectionEntities(queryClient, collectionPrefix, page.items)
            return page
        },
        getNextPageParam: (lastPage, pages) => (
            nextLazyCollectionPageRequest(lastPage, pages, initialCount, batchSize)
        ),
        refetchOnMount: 'always',
        refetchOnWindowFocus: false,
        refetchIntervalInBackground: false,
        refetchInterval: pollIntervalMs === undefined
            ? false
            : (currentQuery) => {
                const currentData = currentQuery.state.data as
                    | InfiniteData<LazyCollectionPage<T>, LazyCollectionPageRequest>
                    | undefined
                const pageCount = currentData?.pages.length ?? 0
                if (
                    pollWhilePageCountAtMost !== undefined
                    && pageCount > pollWhilePageCountAtMost
                ) {
                    return false
                }
                return pollIntervalMs
            },
    })

    const items = useMemo(() => {
        const seen = new Set<number>()
        const result: T[] = []
        for (const page of query.data?.pages ?? []) {
            for (const item of page.items) {
                if (seen.has(item.id)) continue
                seen.add(item.id)
                result.push(item)
            }
        }
        return result
    }, [query.data])
    const total = query.data?.pages[0]?.total ?? 0
    const revision = query.data?.pages[0]?.revision
    const facets = query.data?.pages[0]?.facets ?? {}
    const actions = query.data?.pages[0]?.actions ?? {}

    useEffect(() => {
        if (
            !enabled
            || items.length >= initialCount
            || !query.hasNextPage
            || query.isFetching
        ) return
        void query.fetchNextPage()
    }, [
        enabled,
        initialCount,
        items.length,
        query.fetchNextPage,
        query.hasNextPage,
        query.isFetching,
    ])

    useEffect(() => {
        const revisions = new Set(
            (query.data?.pages ?? [])
                .map((page) => page.revision)
                .filter((value): value is string => Boolean(value)),
        )
        if (revisions.size <= 1) return
        void queryClient.invalidateQueries({queryKey: fullQueryKey, exact: true})
    }, [fullQueryKey, query.data?.pages, queryClient])

    return {
        ...query,
        items,
        total,
        revision,
        facets,
        actions,
    }
}
