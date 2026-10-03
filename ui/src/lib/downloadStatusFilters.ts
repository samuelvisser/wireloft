export const DOWNLOAD_STATUS_FILTER_QUERY_PARAM = 'status'

export type DownloadStatusFilterValue =
    | 'not_downloaded'
    | 'pending'
    | 'downloading'
    | 'downloaded'
    | 'local_processing'
    | 'cancelled'
    | 'error'
    | 'missing'
    | 'corrupted'

export type DownloadStatusFilterOption = {
    value: DownloadStatusFilterValue
    label: string
    statuses: readonly string[]
}

export const DOWNLOAD_STATUS_FILTER_OPTIONS: readonly DownloadStatusFilterOption[] = [
    {value: 'not_downloaded', label: 'Not downloaded', statuses: ['not_downloaded']},
    {value: 'pending', label: 'Queued', statuses: ['pending']},
    {value: 'downloading', label: 'Downloading', statuses: ['downloading', 'preparing', 'waiting', 'canceling']},
    {value: 'downloaded', label: 'Downloaded', statuses: ['downloaded', 'redownloaded']},
    {value: 'local_processing', label: 'Processing', statuses: ['local_processing']},
    {value: 'cancelled', label: 'Cancelled', statuses: ['cancelled']},
    {value: 'error', label: 'Error', statuses: ['error']},
    {value: 'missing', label: 'Missing', statuses: ['missing']},
    {value: 'corrupted', label: 'Corrupted', statuses: ['corrupted']},
]

// Show everything by default except completed downloads.
export const DEFAULT_DOWNLOAD_STATUS_FILTER = new Set(
    DOWNLOAD_STATUS_FILTER_OPTIONS
        .filter((option) => option.value !== 'downloaded')
        .flatMap((option) => option.statuses),
)

const DOWNLOAD_STATUS_FILTER_OPTIONS_BY_VALUE = new Map(
    DOWNLOAD_STATUS_FILTER_OPTIONS.map((option) => [option.value, option]),
)

export function downloadStatusFilterFromSearchParams(searchParams: URLSearchParams): Set<string> {
    const requestedFilters = searchParams.getAll(DOWNLOAD_STATUS_FILTER_QUERY_PARAM)
    if (requestedFilters.length === 0) return new Set(DEFAULT_DOWNLOAD_STATUS_FILTER)

    const statuses = new Set<string>()
    for (const value of requestedFilters) {
        const option = DOWNLOAD_STATUS_FILTER_OPTIONS_BY_VALUE.get(value as DownloadStatusFilterValue)
        if (!option) continue

        for (const status of option.statuses) {
            statuses.add(status)
        }
    }
    return statuses
}

export function downloadsUrlForStatusFilters(...filters: DownloadStatusFilterValue[]): string {
    const searchParams = new URLSearchParams()
    for (const filter of filters) {
        searchParams.append(DOWNLOAD_STATUS_FILTER_QUERY_PARAM, filter)
    }

    const query = searchParams.toString()
    return query ? `/downloads?${query}` : '/downloads'
}

export function downloadStatusFiltersToSearchParams(statusFilter: Set<string>): URLSearchParams {
    const searchParams = new URLSearchParams()
    for (const option of DOWNLOAD_STATUS_FILTER_OPTIONS) {
        if (option.statuses.every((status) => statusFilter.has(status))) {
            searchParams.append(DOWNLOAD_STATUS_FILTER_QUERY_PARAM, option.value)
        }
    }
    return searchParams
}
