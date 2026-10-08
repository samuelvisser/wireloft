import assert from 'node:assert/strict'
import test from 'node:test'

import {
    ALL_DOWNLOAD_STATUSES,
    DEFAULT_DOWNLOAD_STATUS_FILTER,
    downloadStatusesForApi,
} from '../src/lib/downloadStatusFilters'

test('complete download status coverage is sent to the API as no filter', () => {
    assert.equal(downloadStatusesForApi(ALL_DOWNLOAD_STATUSES), undefined)
    assert.equal(
        downloadStatusesForApi([...ALL_DOWNLOAD_STATUSES].reverse()),
        undefined,
    )
})

test('proper download status subsets remain explicit API filters', () => {
    const normalized = downloadStatusesForApi(DEFAULT_DOWNLOAD_STATUS_FILTER)

    assert.ok(normalized)
    assert.deepEqual(normalized, [...DEFAULT_DOWNLOAD_STATUS_FILTER].sort())
})
