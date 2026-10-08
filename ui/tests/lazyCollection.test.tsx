import assert from 'node:assert/strict'
import test from 'node:test'
import {QueryClient, type InfiniteData} from '@tanstack/react-query'

import {
    contiguousLazyCollectionItems,
    deriveSameLazyCollectionPlaceholder,
    type LazyCollectionPage,
    lazyCollectionQueryKey,
    nextLazyCollectionPageRequest,
    previousLazyCollectionPageRequest,
} from '../src/lib/lazyCollection'
import {
    applyMediaDownloadQueuePositions,
    compareMediaDownloadWorkflowOrder,
    deriveMediaDownloadCollectionPlaceholder,
} from '../src/lib/queries'
import {deriveTaskLedgerCollectionPlaceholder} from '../src/lib/taskLedger'
import type {TaskLedgerEntryRead} from '../src/types/schemas/task'
import type {
    MediaDownloadDomainViewRead,
    MediaDownloadViewRead,
} from '../src/types/schemas/media_download'

test('Home cache can seed Downloads display without satisfying its 50-row refresh', () => {
    const queryClient = new QueryClient()
    const semanticKey = ['mediaDownloads', 'list', ['pending'], 'workflow'] as const
    const homeKey = lazyCollectionQueryKey(
        ['mediaDownloads'],
        [['pending'], 'workflow'],
        3,
        50,
    )
    const downloadsKey = lazyCollectionQueryKey(
        ['mediaDownloads'],
        [['pending'], 'workflow'],
        50,
        50,
    )
    const homePage: LazyCollectionPage<{id: number}> = {
        items: Array.from({length: 3}, (_, index) => ({id: index + 1})),
        total: 100,
        limit: 3,
        nextCursor: 'next-page',
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<{id: number}>,
        {cursor: string | null; limit: number}
    >>(homeKey, {
        pages: [homePage],
        pageParams: [{cursor: null, limit: 3}],
    })

    const placeholder = deriveSameLazyCollectionPlaceholder<{id: number}>(
        queryClient,
        semanticKey,
        50,
    )

    assert.ok(placeholder)
    assert.deepEqual(placeholder.pages[0].items.map((item) => item.id), [1, 2, 3])
    assert.equal(placeholder.pages[0].limit, 50)
    assert.equal(queryClient.getQueryData(downloadsKey), undefined)
    assert.notDeepEqual(homeKey, downloadsKey)
})

test('Downloads cache can seed Home display without satisfying its three-row refresh', () => {
    const queryClient = new QueryClient()
    const semanticKey = ['mediaDownloads', 'list', ['pending'], 'workflow'] as const
    const downloadsKey = lazyCollectionQueryKey(
        ['mediaDownloads'],
        [['pending'], 'workflow'],
        50,
        50,
    )
    const homeKey = lazyCollectionQueryKey(
        ['mediaDownloads'],
        [['pending'], 'workflow'],
        3,
        50,
    )
    const downloadsPage: LazyCollectionPage<{id: number}> = {
        items: Array.from({length: 50}, (_, index) => ({id: index + 1})),
        total: 100,
        limit: 50,
        nextCursor: 'next-page',
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<{id: number}>,
        {cursor: string | null; limit: number}
    >>(downloadsKey, {
        pages: [downloadsPage],
        pageParams: [{cursor: null, limit: 50}],
    })

    const placeholder = deriveSameLazyCollectionPlaceholder<{id: number}>(
        queryClient,
        semanticKey,
        3,
    )

    assert.ok(placeholder)
    assert.deepEqual(placeholder.pages[0].items.map((item) => item.id), [1, 2, 3])
    assert.equal(placeholder.pages[0].limit, 3)
    assert.equal(queryClient.getQueryData(homeKey), undefined)
})

test('normal lazy collection scrolling uses the configured batch size', () => {
    const firstPage: LazyCollectionPage<{id: number}> = {
        items: Array.from({length: 50}, (_, index) => ({id: index + 1})),
        total: 120,
        limit: 50,
        nextCursor: 'next-page',
    }

    assert.deepEqual(
        nextLazyCollectionPageRequest(firstPage, 50),
        {cursor: 'next-page', limit: 50},
    )
})

test('queue-position updates reorder cached queued downloads immediately', () => {
    const queryClient = new QueryClient()
    const download = (id: number, queuePosition: number): MediaDownloadDomainViewRead => ({
        id,
        queuePosition,
    } as MediaDownloadDomainViewRead)

    const first = download(1, 1)
    const second = download(2, 2)
    const page: LazyCollectionPage<MediaDownloadDomainViewRead> = {
        items: [first, second],
        total: 2,
        limit: 50,
        nextCursor: null,
    }
    const queryKey = lazyCollectionQueryKey(
        ['mediaDownloads'],
        [['pending'], 'workflow'],
        50,
        50,
    )

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {cursor: string | null; limit: number}
    >>(queryKey, {
        pages: [page],
        pageParams: [{cursor: null, limit: 50}],
    })

    applyMediaDownloadQueuePositions(queryClient, {1: 2, 2: 1})

    const updated = queryClient.getQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {cursor: string | null; limit: number}
    >>(queryKey)
    assert.ok(updated)

    const presented = updated.pages[0].items.map((item) => ({
        ...item,
        downloadStatus: 'pending',
        presentation: {active: true},
    } as MediaDownloadViewRead))

    presented.sort(compareMediaDownloadWorkflowOrder)
    assert.deepEqual(presented.map((item) => item.id), [2, 1])
    assert.deepEqual(presented.map((item) => item.queuePosition), [1, 2])
})


function domainDownload(
    id: number,
    artifactStatus: MediaDownloadDomainViewRead['artifactStatus'],
): MediaDownloadDomainViewRead {
    const createdAt = new Date(`2026-10-08T00:00:0${id}Z`)
    return {
        id,
        type: 'episode',
        mediaItemId: id,
        localMediaProfileId: 1,
        filePath: `/downloads/${id}.m4a`,
        assets: [],
        artifactStatus,
        artifactError: null,
        artifactSizeBytes: null,
        automaticRetrySuppressed: false,
        downloadedBytes: null,
        formatDownloaded: null,
        downloadedAt: artifactStatus === 'available' ? createdAt : null,
        createdAt,
        updatedAt: createdAt,
        mediaSlug: null,
        mediaTitle: `Episode ${id}`,
        episodeSlug: `episode-${id}`,
        episodeTitle: `Episode ${id}`,
        episodeIdentifier: null,
        showSlug: 'show',
        showTitle: 'Show',
        movieSlug: null,
        movieTitle: null,
        movieExtraType: null,
        localMediaProfileName: 'Audio',
        preferredFormat: 'format_audio_only',
        downloadedPublishStatus: null,
        latestTaskStatus: null,
        latestTaskError: null,
        latestTaskIsRedownload: false,
        latestTaskStartedAt: null,
        latestTaskFinishedAt: null,
    } as MediaDownloadDomainViewRead
}

test('a narrower download filter renders from a broader cache without populating its cache key', () => {
    const queryClient = new QueryClient()
    const broadKey = lazyCollectionQueryKey(
        ['mediaDownloads'],
        [null, 'workflow'],
        50,
        50,
    )
    const narrowKey = lazyCollectionQueryKey(
        ['mediaDownloads'],
        [['downloaded'], 'workflow'],
        50,
        50,
    )
    const broadPage: LazyCollectionPage<MediaDownloadDomainViewRead> = {
        items: [
            domainDownload(3, 'available'),
            domainDownload(2, 'missing'),
            domainDownload(1, 'available'),
        ],
        total: 3,
        limit: 50,
        nextCursor: null,
        revision: 'revision-1',
        facets: {downloaded: 2, missing: 1},
        actions: {},
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {cursor: string | null; limit: number}
    >>(broadKey, {
        pages: [broadPage],
        pageParams: [{cursor: null, limit: 50}],
    })

    const placeholder = deriveMediaDownloadCollectionPlaceholder(queryClient, {
        statuses: ['downloaded'],
        order: 'workflow',
        initialCount: 50,
    })

    assert.ok(placeholder)
    assert.deepEqual(placeholder.pages[0].items.map((item) => item.id), [3, 1])
    assert.equal(placeholder.pages[0].total, 2)
    assert.equal(placeholder.pages[0].nextCursor, null)

    // Derived data is only observer placeholder data. The narrower query remains
    // uncached, so mounting it still performs its own authoritative backend fetch.
    assert.equal(queryClient.getQueryData(narrowKey), undefined)
})

test('a partial broader download prefix can seed the known filtered prefix when facets prove more exist', () => {
    const queryClient = new QueryClient()
    const broadKey = lazyCollectionQueryKey(
        ['mediaDownloads'],
        [null, 'workflow'],
        3,
        50,
    )
    const broadPage: LazyCollectionPage<MediaDownloadDomainViewRead> = {
        items: [
            domainDownload(5, 'missing'),
            domainDownload(4, 'available'),
            domainDownload(3, 'missing'),
        ],
        total: 20,
        limit: 3,
        nextCursor: 'next-page',
        revision: 'revision-2',
        facets: {downloaded: 5, missing: 15},
        actions: {},
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {cursor: string | null; limit: number}
    >>(broadKey, {
        pages: [broadPage],
        pageParams: [{cursor: null, limit: 3}],
    })

    const placeholder = deriveMediaDownloadCollectionPlaceholder(queryClient, {
        statuses: ['downloaded'],
        order: 'workflow',
        initialCount: 9,
    })

    assert.ok(placeholder)
    assert.deepEqual(placeholder.pages[0].items.map((item) => item.id), [4])
    assert.equal(placeholder.pages[0].total, 5)
    assert.equal(placeholder.pages[0].nextCursor, null)
})

test('filtered placeholder reuse never crosses collection ordering', () => {
    const queryClient = new QueryClient()
    const broadKey = lazyCollectionQueryKey(
        ['mediaDownloads'],
        [null, 'recent'],
        9,
        9,
    )
    const broadPage: LazyCollectionPage<MediaDownloadDomainViewRead> = {
        items: [domainDownload(1, 'available')],
        total: 1,
        limit: 9,
        nextCursor: null,
        revision: 'revision-3',
        facets: {downloaded: 1},
        actions: {},
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {cursor: string | null; limit: number}
    >>(broadKey, {
        pages: [broadPage],
        pageParams: [{cursor: null, limit: 9}],
    })

    assert.equal(
        deriveMediaDownloadCollectionPlaceholder(queryClient, {
            statuses: ['downloaded'],
            order: 'workflow',
            initialCount: 9,
        }),
        undefined,
    )
})


test('a narrower download filter can reuse a filtered superset with the same ordering', () => {
    const queryClient = new QueryClient()
    const broadKey = lazyCollectionQueryKey(
        ['mediaDownloads'],
        [['corrupted', 'error', 'missing'], 'workflow'],
        50,
        50,
    )
    const broadPage: LazyCollectionPage<MediaDownloadDomainViewRead> = {
        items: [
            domainDownload(3, 'corrupted'),
            domainDownload(2, 'missing'),
            domainDownload(1, 'missing'),
        ],
        total: 3,
        limit: 50,
        nextCursor: null,
        revision: 'revision-4',
        facets: {corrupted: 1, error: 0, missing: 2},
        actions: {},
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {cursor: string | null; limit: number}
    >>(broadKey, {
        pages: [broadPage],
        pageParams: [{cursor: null, limit: 50}],
    })

    const placeholder = deriveMediaDownloadCollectionPlaceholder(queryClient, {
        statuses: ['missing'],
        order: 'workflow',
        initialCount: 50,
    })

    assert.ok(placeholder)
    assert.deepEqual(placeholder.pages[0].items.map((item) => item.id), [2, 1])
    assert.equal(placeholder.pages[0].total, 2)
})


function taskLedgerEntry(
    id: number,
    {
        definitionKey = 'fetch_new_episodes',
        resourceType = 'show',
        resourceId = 0,
        status = 'SUCCEEDED',
        startedAt = `2026-10-08T0${id}:00:00Z`,
    }: Partial<Pick<
        TaskLedgerEntryRead,
        'definitionKey' | 'resourceType' | 'resourceId' | 'status' | 'startedAt'
    >> = {},
): TaskLedgerEntryRead {
    return {
        id,
        definitionKey,
        definitionTitle: definitionKey,
        resourceType,
        resourceId,
        status,
        inputs: {},
        result: null,
        attemptCount: 1,
        maxRetries: 0,
        createdAt: startedAt ?? `2026-10-08T0${id}:00:00Z`,
        updatedAt: startedAt ?? `2026-10-08T0${id}:00:00Z`,
        startedAt,
    } as TaskLedgerEntryRead
}

test('cron task ledger can render immediately from the broader Tasks cache without populating its own key', () => {
    const queryClient = new QueryClient()
    const tasksKey = lazyCollectionQueryKey(
        ['taskLedger'],
        [null, null, null, null, null, 'created_at', 'desc'],
        100,
        100,
    )
    const cronKey = lazyCollectionQueryKey(
        ['taskLedger'],
        ['fetch_new_episodes', 'show', [0], null, null, 'created_at', 'desc'],
        10,
        10,
    )
    const broadPage: LazyCollectionPage<TaskLedgerEntryRead> = {
        items: [
            taskLedgerEntry(3, {definitionKey: 'file_watcher'}),
            taskLedgerEntry(2),
            taskLedgerEntry(1, {resourceId: 9}),
        ],
        total: 3,
        limit: 100,
        nextCursor: null,
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<TaskLedgerEntryRead>,
        {cursor: string | null; limit: number}
    >>(tasksKey, {
        pages: [broadPage],
        pageParams: [{cursor: null, limit: 100}],
    })

    const placeholder = deriveTaskLedgerCollectionPlaceholder(queryClient, {
        definitionKey: 'fetch_new_episodes',
        resourceType: 'show',
        resourceIds: [0],
        statuses: undefined,
        startedAfter: undefined,
        orderBy: 'created_at',
        order: 'desc',
        initialCount: 10,
    })

    assert.ok(placeholder)
    assert.deepEqual(placeholder.pages[0].items.map((item) => item.id), [2])
    assert.equal(placeholder.pages[0].total, 1)

    // As with downloads, this is observer-only placeholder data. Opening the
    // cron ledger still performs its own filtered /tasks/ledger request.
    assert.equal(queryClient.getQueryData(cronKey), undefined)
})

test('task ledger placeholder reuse respects status and started-after filters', () => {
    const queryClient = new QueryClient()
    const tasksKey = lazyCollectionQueryKey(
        ['taskLedger'],
        [null, null, null, null, null, 'created_at', 'desc'],
        100,
        100,
    )
    const broadPage: LazyCollectionPage<TaskLedgerEntryRead> = {
        items: [
            taskLedgerEntry(3, {status: 'FAILED', startedAt: '2026-10-08T03:00:00Z'}),
            taskLedgerEntry(2, {status: 'SUCCEEDED', startedAt: '2026-10-08T02:00:00Z'}),
            taskLedgerEntry(1, {status: 'FAILED', startedAt: '2026-10-08T01:00:00Z'}),
        ],
        total: 3,
        limit: 100,
        nextCursor: null,
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<TaskLedgerEntryRead>,
        {cursor: string | null; limit: number}
    >>(tasksKey, {
        pages: [broadPage],
        pageParams: [{cursor: null, limit: 100}],
    })

    const placeholder = deriveTaskLedgerCollectionPlaceholder(queryClient, {
        definitionKey: 'fetch_new_episodes',
        resourceType: 'show',
        resourceIds: [0],
        statuses: ['FAILED'],
        startedAfter: '2026-10-08T02:00:00Z',
        orderBy: 'created_at',
        order: 'desc',
        initialCount: 10,
    })

    assert.ok(placeholder)
    assert.deepEqual(placeholder.pages[0].items.map((item) => item.id), [3])
})

test('task ledger placeholder reuse never crosses ordering', () => {
    const queryClient = new QueryClient()
    const tasksKey = lazyCollectionQueryKey(
        ['taskLedger'],
        [null, null, null, null, null, 'started_at', 'desc'],
        100,
        100,
    )
    const broadPage: LazyCollectionPage<TaskLedgerEntryRead> = {
        items: [taskLedgerEntry(1)],
        total: 1,
        limit: 100,
        nextCursor: null,
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<TaskLedgerEntryRead>,
        {cursor: string | null; limit: number}
    >>(tasksKey, {
        pages: [broadPage],
        pageParams: [{cursor: null, limit: 100}],
    })

    assert.equal(
        deriveTaskLedgerCollectionPlaceholder(queryClient, {
            definitionKey: 'fetch_new_episodes',
            resourceType: 'show',
            resourceIds: [0],
            statuses: undefined,
            startedAfter: undefined,
            orderBy: 'created_at',
            order: 'desc',
            initialCount: 10,
        }),
        undefined,
    )
})


test('Tasks and 10-row ledger modals use separate refresh executions over the same semantic cache', () => {
    const tasksKey = lazyCollectionQueryKey(
        ['taskLedger'],
        [null, null, null, null, null, 'created_at', 'desc'],
        100,
        100,
    )
    const modalKey = lazyCollectionQueryKey(
        ['taskLedger'],
        [null, null, null, null, null, 'created_at', 'desc'],
        10,
        10,
    )

    assert.notDeepEqual(tasksKey, modalKey)
})

test('pagination continues only after an authoritative initial prefix', () => {
    const authoritativeFirstPage: LazyCollectionPage<{id: number}> = {
        items: Array.from({length: 50}, (_, index) => ({id: index + 1})),
        total: 120,
        limit: 50,
        nextCursor: 'next-page',
    }

    assert.deepEqual(
        nextLazyCollectionPageRequest(authoritativeFirstPage, 50),
        {cursor: 'next-page', limit: 50},
    )
})


test('bidirectional lazy collections use the server previous cursor', () => {
    const page: LazyCollectionPage<{id: string}> = {
        items: [{id: 'middle'}],
        limit: 30,
        nextCursor: 'after-middle',
        previousCursor: 'before-middle',
    }

    assert.deepEqual(
        previousLazyCollectionPageRequest(page, 30),
        {cursor: 'before-middle', limit: 30},
    )
})


test('mixed cursor revisions are never reused as compatible placeholder cache', () => {
    const pages: LazyCollectionPage<{id: number}>[] = [
        {
            items: [{id: 1}],
            limit: 1,
            nextCursor: 'old-next',
            revision: 'old-revision',
        },
        {
            items: [{id: 2}],
            limit: 1,
            nextCursor: 'new-next',
            revision: 'new-revision',
        },
    ]

    assert.equal(contiguousLazyCollectionItems(pages), null)
})
