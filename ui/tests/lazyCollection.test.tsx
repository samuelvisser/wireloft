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
