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
