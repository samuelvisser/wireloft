import {useEffect, useMemo} from 'react'
import {
    type InfiniteData,
    type QueryClient,
    useInfiniteQuery,
    useQueryClient,
} from '@tanstack/react-query'

export type LazyCollectionPage<T> = {
    items: T[]
    limit: number
    nextCursor?: string | null
    previousCursor?: string | null
    total?: number
    revision?: string
    facets?: Record<string, number>
    actions?: Record<string, number>
    provisional?: boolean
}

export type LazyCollectionPageRequest = {
    cursor: string | null
    limit: number
}


export function lazyCollectionQueryKey(
    collectionPrefix: readonly unknown[],
    queryKey: readonly unknown[],
    initialCount: number,
    batchSize: number,
) {
    return [
        ...collectionPrefix,
        'list',
        ...queryKey,
        'request',
        initialCount,
        batchSize,
    ] as const
}

export function deriveSameLazyCollectionPlaceholder<T extends {id: string | number}>(
    queryClient: QueryClient,
    semanticQueryKey: readonly unknown[],
    initialCount: number,
): InfiniteData<LazyCollectionPage<T>, LazyCollectionPageRequest> | undefined {
    const candidates = queryClient.getQueryCache().findAll({queryKey: semanticQueryKey})

    let best: {
        data: InfiniteData<LazyCollectionPage<T>, LazyCollectionPageRequest>
        itemCount: number
        updatedAt: number
    } | undefined

    for (const query of candidates) {
        const source = query.state.data as InfiniteData<
            LazyCollectionPage<T>,
            LazyCollectionPageRequest
        > | undefined
        if (!source?.pages.length) continue

        const contiguous = contiguousLazyCollectionItems(source.pages)
        if (!contiguous) continue

        const firstPage = source.pages[0]
        const items = contiguous.items.slice(0, initialCount)
        const placeholder: InfiniteData<
            LazyCollectionPage<T>,
            LazyCollectionPageRequest
        > = {
            pages: [{
                ...firstPage,
                items,
                limit: initialCount,
                // Placeholder rows are display-only. Never continue paging from a
                // cursor that belonged to another consumer's older snapshot.
                nextCursor: null,
                previousCursor: null,
            }],
            pageParams: [{cursor: null, limit: initialCount}],
        }

        if (
            best === undefined
            || items.length > best.itemCount
            || (
                items.length === best.itemCount
                && query.state.dataUpdatedAt > best.updatedAt
            )
        ) {
            best = {
                data: placeholder,
                itemCount: items.length,
                updatedAt: query.state.dataUpdatedAt,
            }
        }
    }

    return best?.data
}


export function nextLazyCollectionPageRequest<T>(
    lastPage: LazyCollectionPage<T>,
    batchSize: number,
): LazyCollectionPageRequest | undefined {
    if (!lastPage.nextCursor) return undefined
    return {
        cursor: lastPage.nextCursor,
        limit: batchSize,
    }
}

export function previousLazyCollectionPageRequest<T>(
    firstPage: LazyCollectionPage<T>,
    batchSize: number,
): LazyCollectionPageRequest | undefined {
    if (!firstPage.previousCursor) return undefined
    return {
        cursor: firstPage.previousCursor,
        limit: batchSize,
    }
}


export function contiguousLazyCollectionItems<T>(
    pages: readonly LazyCollectionPage<T>[],
): {items: T[]; complete: boolean} | null {
    if (pages.length === 0) return null

    const revisions = new Set(
        pages
            .map((page) => page.revision)
            .filter((revision): revision is string => revision !== undefined),
    )
    // A mixed-revision chain is being replaced by the authoritative new head.
    // It is never safe placeholder material for another consumer.
    if (revisions.size > 1) return null

    const items = pages.flatMap((page) => page.items)
    const complete = (
        !pages[0]?.previousCursor
        && !pages[pages.length - 1]?.nextCursor
    )
    return {items, complete}
}

type LazyCollectionOptions<T extends {id: string | number}> = {
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

function replaceEntitiesInCollection<T extends {id: string | number}>(
    data: InfiniteData<LazyCollectionPage<T>, LazyCollectionPageRequest> | undefined,
    replacements: Map<string | number, T>,
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

export function syncLazyCollectionEntities<T extends {id: string | number}>(
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

export function updateLazyCollectionEntities<T extends {id: string | number}>(
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

export function useLazyCollection<T extends {id: string | number}>({
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
    const semanticQueryKeySignature = JSON.stringify([
        ...collectionPrefix,
        'list',
        ...queryKey,
    ])
    const semanticQueryKey = useMemo(
        () => [...collectionPrefix, 'list', ...queryKey] as const,
        // Collection descriptors are normalized JSON-compatible values. Keep the
        // query-key reference stable when only the caller's array identity changes.
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [semanticQueryKeySignature],
    )
    const fullQueryKeySignature = JSON.stringify([
        ...semanticQueryKey,
        'request',
        initialCount,
        batchSize,
    ])
    const fullQueryKey = useMemo(
        () => lazyCollectionQueryKey(
            collectionPrefix,
            queryKey,
            initialCount,
            batchSize,
        ),
        // Execution identity also includes the requested initial prefix and page
        // size so another consumer's cache can never reduce this request.
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [fullQueryKeySignature],
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
        initialPageParam: {cursor: null, limit: initialCount},
        placeholderData: () => (
            deriveSameLazyCollectionPlaceholder<T>(
                queryClient,
                semanticQueryKey,
                initialCount,
            )
            ?? derivePlaceholderData?.(queryClient)
        ),
        queryFn: async ({pageParam, signal}) => {
            const page = await fetchPage(pageParam, signal)
            syncLazyCollectionEntities(queryClient, collectionPrefix, page.items)
            return page
        },
        getNextPageParam: (lastPage) => (
            nextLazyCollectionPageRequest(lastPage, batchSize)
        ),
        getPreviousPageParam: (firstPage) => (
            previousLazyCollectionPageRequest(firstPage, batchSize)
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

    const displayData = useMemo(() => {
        if (!query.data?.pages.length) return query.data

        const latestRevision = [...query.data.pages]
            .reverse()
            .find((page) => page.revision !== undefined)
            ?.revision
        if (latestRevision === undefined) return query.data

        const pageIndexes = query.data.pages
            .map((page, index) => page.revision === latestRevision ? index : -1)
            .filter((index) => index >= 0)
        if (pageIndexes.length === query.data.pages.length) return query.data

        return {
            ...query.data,
            pages: pageIndexes.map((index) => query.data!.pages[index]),
            pageParams: pageIndexes.map((index) => query.data!.pageParams[index]),
        }
    }, [query.data])

    const items = useMemo(() => {
        const seen = new Set<string | number>()
        const result: T[] = []
        for (const page of displayData?.pages ?? []) {
            for (const item of page.items) {
                if (seen.has(item.id)) continue
                seen.add(item.id)
                result.push(item)
            }
        }
        return result
    }, [displayData])
    const total = displayData?.pages[0]?.total ?? 0
    const revision = displayData?.pages[0]?.revision
    const facets = displayData?.pages[0]?.facets ?? {}
    const actions = displayData?.pages[0]?.actions ?? {}
    const isTotalProvisional = (
        query.isPlaceholderData
        && displayData?.pages[0]?.provisional === true
    )

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
        const pages = query.data?.pages ?? []
        const revisions = new Set(
            pages
                .map((page) => page.revision)
                .filter((value): value is string => value !== undefined),
        )
        if (revisions.size <= 1 || pages.length === 0) return

        const latestRevision = [...pages]
            .reverse()
            .find((page) => page.revision !== undefined)
            ?.revision
        const replacement = latestRevision === undefined
            ? undefined
            : [...pages].reverse().find((page) => page.revision === latestRevision)
        if (!replacement) return

        // A stale cursor may intentionally be answered with the new collection
        // head. Make that response the new authoritative first page and discard
        // every cursor/page parameter derived from the previous revision before
        // asking React Query to refresh it.
        const normalizedReplacement: LazyCollectionPage<T> = {
            ...replacement,
            items: replacement.items.slice(0, initialCount),
            limit: initialCount,
            // A reset page is the new head. Never preserve cursors calculated
            // for the stale continuation request that produced it.
            previousCursor: null,
            nextCursor: replacement.items.length > initialCount
                ? null
                : replacement.nextCursor,
        }
        queryClient.setQueryData<
            InfiniteData<LazyCollectionPage<T>, LazyCollectionPageRequest>
        >(fullQueryKey, {
            pages: [normalizedReplacement],
            pageParams: [{cursor: null, limit: initialCount}],
        })
        void queryClient.invalidateQueries({queryKey: fullQueryKey, exact: true})
    }, [fullQueryKey, initialCount, query.data?.pages, queryClient])

    return {
        ...query,
        data: displayData,
        items,
        total,
        revision,
        facets,
        actions,
        isTotalProvisional,
    }
}
