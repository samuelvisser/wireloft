import assert from 'node:assert/strict'
import test from 'node:test'
import {QueryClient, type InfiniteData} from '@tanstack/react-query'

import {
    type LazyCollectionPage,
    nextLazyCollectionPageRequest,
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

test('a larger consumer fills only the missing prefix from a shared lazy collection', () => {
    const firstPage: LazyCollectionPage<{id: number}> = {
        items: Array.from({length: 9}, (_, index) => ({id: index + 1})),
        total: 100,
        offset: 0,
        limit: 9,
        hasMore: true,
    }

    assert.deepEqual(
        nextLazyCollectionPageRequest(firstPage, [firstPage], 50, 50),
        {offset: 9, limit: 41},
    )
})

test('normal lazy collection scrolling uses the configured batch size', () => {
    const firstPage: LazyCollectionPage<{id: number}> = {
        items: Array.from({length: 50}, (_, index) => ({id: index + 1})),
        total: 120,
        offset: 0,
        limit: 50,
        hasMore: true,
    }

    assert.deepEqual(
        nextLazyCollectionPageRequest(firstPage, [firstPage], 50, 50),
        {offset: 50, limit: 50},
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
        offset: 0,
        limit: 50,
        hasMore: false,
    }
    const queryKey = ['mediaDownloads', 'list', ['pending'], 'workflow'] as const

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {offset: number; limit: number}
    >>(queryKey, {
        pages: [page],
        pageParams: [{offset: 0, limit: 50}],
    })

    applyMediaDownloadQueuePositions(queryClient, {1: 2, 2: 1})

    const updated = queryClient.getQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {offset: number; limit: number}
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
    const broadKey = ['mediaDownloads', 'list', null, 'workflow'] as const
    const narrowKey = ['mediaDownloads', 'list', ['downloaded'], 'workflow'] as const
    const broadPage: LazyCollectionPage<MediaDownloadDomainViewRead> = {
        items: [
            domainDownload(3, 'available'),
            domainDownload(2, 'missing'),
            domainDownload(1, 'available'),
        ],
        total: 3,
        offset: 0,
        limit: 50,
        hasMore: false,
        revision: 'revision-1',
        facets: {downloaded: 2, missing: 1},
        actions: {},
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {offset: number; limit: number}
    >>(broadKey, {
        pages: [broadPage],
        pageParams: [{offset: 0, limit: 50}],
    })

    const placeholder = deriveMediaDownloadCollectionPlaceholder(queryClient, {
        statuses: ['downloaded'],
        order: 'workflow',
        initialCount: 50,
    })

    assert.ok(placeholder)
    assert.deepEqual(placeholder.pages[0].items.map((item) => item.id), [3, 1])
    assert.equal(placeholder.pages[0].total, 2)
    assert.equal(placeholder.pages[0].hasMore, false)

    // Derived data is only observer placeholder data. The narrower query remains
    // uncached, so mounting it still performs its own authoritative backend fetch.
    assert.equal(queryClient.getQueryData(narrowKey), undefined)
})

test('a partial broader download prefix can seed the known filtered prefix when facets prove more exist', () => {
    const queryClient = new QueryClient()
    const broadKey = ['mediaDownloads', 'list', null, 'workflow'] as const
    const broadPage: LazyCollectionPage<MediaDownloadDomainViewRead> = {
        items: [
            domainDownload(5, 'missing'),
            domainDownload(4, 'available'),
            domainDownload(3, 'missing'),
        ],
        total: 20,
        offset: 0,
        limit: 3,
        hasMore: true,
        revision: 'revision-2',
        facets: {downloaded: 5, missing: 15},
        actions: {},
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {offset: number; limit: number}
    >>(broadKey, {
        pages: [broadPage],
        pageParams: [{offset: 0, limit: 3}],
    })

    const placeholder = deriveMediaDownloadCollectionPlaceholder(queryClient, {
        statuses: ['downloaded'],
        order: 'workflow',
        initialCount: 9,
    })

    assert.ok(placeholder)
    assert.deepEqual(placeholder.pages[0].items.map((item) => item.id), [4])
    assert.equal(placeholder.pages[0].total, 5)
    assert.equal(placeholder.pages[0].hasMore, true)
})

test('filtered placeholder reuse never crosses collection ordering', () => {
    const queryClient = new QueryClient()
    const broadKey = ['mediaDownloads', 'list', null, 'recent'] as const
    const broadPage: LazyCollectionPage<MediaDownloadDomainViewRead> = {
        items: [domainDownload(1, 'available')],
        total: 1,
        offset: 0,
        limit: 9,
        hasMore: false,
        revision: 'revision-3',
        facets: {downloaded: 1},
        actions: {},
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {offset: number; limit: number}
    >>(broadKey, {
        pages: [broadPage],
        pageParams: [{offset: 0, limit: 9}],
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
    const broadKey = [
        'mediaDownloads',
        'list',
        ['corrupted', 'error', 'missing'],
        'workflow',
    ] as const
    const broadPage: LazyCollectionPage<MediaDownloadDomainViewRead> = {
        items: [
            domainDownload(3, 'corrupted'),
            domainDownload(2, 'missing'),
            domainDownload(1, 'missing'),
        ],
        total: 3,
        offset: 0,
        limit: 50,
        hasMore: false,
        revision: 'revision-4',
        facets: {corrupted: 1, error: 0, missing: 2},
        actions: {},
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<MediaDownloadDomainViewRead>,
        {offset: number; limit: number}
    >>(broadKey, {
        pages: [broadPage],
        pageParams: [{offset: 0, limit: 50}],
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
    const tasksKey = [
        'taskLedger',
        'list',
        null,
        null,
        null,
        null,
        null,
        'created_at',
        'desc',
    ] as const
    const cronKey = [
        'taskLedger',
        'list',
        'fetch_new_episodes',
        'show',
        [0],
        null,
        null,
        'created_at',
        'desc',
    ] as const
    const broadPage: LazyCollectionPage<TaskLedgerEntryRead> = {
        items: [
            taskLedgerEntry(3, {definitionKey: 'file_watcher'}),
            taskLedgerEntry(2),
            taskLedgerEntry(1, {resourceId: 9}),
        ],
        total: 3,
        offset: 0,
        limit: 100,
        hasMore: false,
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<TaskLedgerEntryRead>,
        {offset: number; limit: number}
    >>(tasksKey, {
        pages: [broadPage],
        pageParams: [{offset: 0, limit: 100}],
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
    const tasksKey = [
        'taskLedger',
        'list',
        null,
        null,
        null,
        null,
        null,
        'created_at',
        'desc',
    ] as const
    const broadPage: LazyCollectionPage<TaskLedgerEntryRead> = {
        items: [
            taskLedgerEntry(3, {status: 'FAILED', startedAt: '2026-10-08T03:00:00Z'}),
            taskLedgerEntry(2, {status: 'SUCCEEDED', startedAt: '2026-10-08T02:00:00Z'}),
            taskLedgerEntry(1, {status: 'FAILED', startedAt: '2026-10-08T01:00:00Z'}),
        ],
        total: 3,
        offset: 0,
        limit: 100,
        hasMore: false,
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<TaskLedgerEntryRead>,
        {offset: number; limit: number}
    >>(tasksKey, {
        pages: [broadPage],
        pageParams: [{offset: 0, limit: 100}],
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
    const tasksKey = [
        'taskLedger',
        'list',
        null,
        null,
        null,
        null,
        null,
        'started_at',
        'desc',
    ] as const
    const broadPage: LazyCollectionPage<TaskLedgerEntryRead> = {
        items: [taskLedgerEntry(1)],
        total: 1,
        offset: 0,
        limit: 100,
        hasMore: false,
    }

    queryClient.setQueryData<InfiniteData<
        LazyCollectionPage<TaskLedgerEntryRead>,
        {offset: number; limit: number}
    >>(tasksKey, {
        pages: [broadPage],
        pageParams: [{offset: 0, limit: 100}],
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


test('a 10-row ledger modal reuses a 100-row Tasks page before requesting the next backend page', () => {
    const cachedTasksPage: LazyCollectionPage<{id: number}> = {
        items: Array.from({length: 100}, (_, index) => ({id: index + 1})),
        total: 150,
        offset: 0,
        limit: 100,
        hasMore: true,
    }

    assert.deepEqual(
        nextLazyCollectionPageRequest(cachedTasksPage, [cachedTasksPage], 10, 10),
        {offset: 100, limit: 10},
    )
})

test('Tasks expands a 10-row ledger cache by requesting only the missing 90 rows', () => {
    const cachedLedgerPage: LazyCollectionPage<{id: number}> = {
        items: Array.from({length: 10}, (_, index) => ({id: index + 1})),
        total: 150,
        offset: 0,
        limit: 10,
        hasMore: true,
    }

    assert.deepEqual(
        nextLazyCollectionPageRequest(cachedLedgerPage, [cachedLedgerPage], 100, 100),
        {offset: 10, limit: 90},
    )
})
