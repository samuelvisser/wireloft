import {useMemo, useRef, useState} from 'react'
import {useNavigate} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {library} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@awesome.me/kit-83fa1ac5a9/icons'
import {Column, DataTable, DataTableAction} from '../components/DataTable/DataTable'
import DownloadLogDialog from '../components/MediaDownload/DownloadLogDialog'
import {useActiveOperation} from '../components/OperationNotifier/OperationNotifier'
import PageSubtitle from '../components/common/PageSubtitle'
import ProgressBar from '../components/common/ProgressBar'
import ProgressButton from '../components/common/ProgressButton'
import {frontendOperationDefinitions} from '../lib/operationDefinitions'
import {useControlOperation, useStartOperation} from '../lib/operations'
import {useMediaDownloadsView} from '../lib/queries'
import {ACTIVE_DOWNLOAD_STATUSES, MediaDownloadStatusReg} from '../types/media_download'
import {MediaDownloadViewRead} from '../types/schemas/media_download'
import {TaskOperationRead} from '../types/schemas/operation'
import {getErrorMessageFromResponse} from '../utils/helpers'
import {movieExtraTypeLabel} from '../utils/movieExtras'
import './DownloadsPage.css'

type StatusFilterOption = {
    value: string
    label: string
    statuses: readonly string[]
}

type BulkAction = 'retry' | 'cancel'

const STATUS_FILTER_OPTIONS: StatusFilterOption[] = [
    {value: 'not_downloaded', label: 'Not downloaded', statuses: ['not_downloaded']},
    {value: 'pending', label: 'Queued', statuses: ['pending']},
    {value: 'downloading', label: 'Downloading', statuses: ['downloading']},
    {value: 'downloaded', label: 'Downloaded', statuses: ['downloaded', 'redownloaded']},
    {value: 'local_processing', label: 'Local processing', statuses: ['local_processing']},
    {value: 'cancelled', label: 'Cancelled', statuses: ['cancelled']},
    {value: 'error', label: 'Error', statuses: ['error']},
    {value: 'missing', label: 'Missing', statuses: ['missing']},
    {value: 'corrupted', label: 'Corrupted', statuses: ['corrupted']},
]

const FILTER_DOUBLE_PRESS_WINDOW_MS = 500

// Show everything by default except completed downloads.
const DEFAULT_STATUS_FILTER = new Set(
    STATUS_FILTER_OPTIONS
        .filter((option) => option.value !== 'downloaded')
        .flatMap((option) => option.statuses),
)

function formatDateTime(value: Date | null | undefined): string {
    if (!value) return '—'
    try {
        return value.toLocaleString()
    } catch {
        return String(value)
    }
}

/** The timestamp to show for a download row: when it finished, otherwise when its record was created. */
function rowTimestamp(row: MediaDownloadViewRead): Date | null {
    return row.finishedAt ?? row.createdAt ?? null
}

function rowTitle(row: MediaDownloadViewRead): string {
    return row.mediaTitle ?? row.movieTitle ?? row.episodeTitle ?? 'Unknown media'
}

function mediaTypeLabel(type: string, movieExtraType?: string | null): string {
    if (type === 'movie') return 'Movie'
    if (type === 'movie_extra') return movieExtraTypeLabel(movieExtraType)
    if (type === 'episode') return 'Episode'
    return type ? type.replace(/_/g, ' ').replace(/^./, (char) => char.toUpperCase()) : 'Media'
}

function rowContext(row: MediaDownloadViewRead): string {
    if (row.type === 'movie' || row.type === 'movie_extra') return mediaTypeLabel(row.type, row.movieExtraType)
    return row.showTitle ?? mediaTypeLabel(String(row.type))
}

function setsEqual(a: Set<string>, b: Set<string>): boolean {
    if (a.size !== b.size) return false
    for (const v of a) if (!b.has(v)) return false
    return true
}

function bulkOperationLabel(operation: TaskOperationRead | undefined, starting: boolean): string | undefined {
    if (starting && operation === undefined) return 'Starting…'
    if (!operation) return undefined
    if (operation.status === 'QUEUED') return 'Queued…'
    if (operation.status === 'WAITING') return operation.message || 'Waiting…'
    return `${operation.progress ?? 0}%`
}

// Ensure icons from the kit are registered (idempotent)
library.add(fas)

function formatBytes(n: number | null | undefined) {
    if (!n && n !== 0) return '—'
    if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GiB`
    if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MiB`
    return `${Math.round(n / 1024)} KiB`
}

function tableErrorMessage(errorMessage: string | null | undefined): string | null {
    if (!errorMessage) return null

    const match = errorMessage.match(/^HTTP error \d+:\s*([\s\S]+)$/)
    if (!match) return errorMessage

    try {
        const parsed = JSON.parse(match[1])
        if (parsed && typeof parsed === 'object' && typeof parsed.error === 'string' && parsed.error.trim()) {
            return parsed.error
        }
    } catch {
        // Keep the original error when the HTTP response body is not JSON.
    }

    return errorMessage
}

function StatusCell({row}: {row: MediaDownloadViewRead}) {
    const status = String(row.downloadStatus)
    if (status === 'downloading' || status === 'pending') {
        return (
            <div style={{display: 'flex', alignItems: 'center', gap: 8, minWidth: 140}} aria-live="polite">
                <div style={{flex: 1}}>
                    <ProgressBar value={row.progress} ariaLabel={`Progress for ${rowTitle(row)}`}/>
                </div>
                <span style={{minWidth: 52}}>{status === 'pending' ? 'Queued' : `${row.progress}%`}</span>
            </div>
        )
    }
    if (status === 'error' || status === 'missing' || status === 'corrupted') {
        const errorMessage = tableErrorMessage(row.errorMessage)
        return (
            <span className="download-status-message" title={row.errorMessage ?? undefined}>
                {MediaDownloadStatusReg.getLabelLoose(status)}{errorMessage ? `: ${errorMessage}` : ''}
            </span>
        )
    }
    return <span>{MediaDownloadStatusReg.getLabelLoose(status)}</span>
}

// Queued operations can be prioritized. Records with no active queue item can be retried instead.
const _RETRYABLE_STATUSES = new Set([
    'not_downloaded',
    'downloading',
    'local_processing',
    'cancelled',
    'error',
    'missing',
    'corrupted',
])

const _ACTIVE_SORT_STATUSES = new Set(['downloading', 'local_processing'])

function isRetryableDownload(row: MediaDownloadViewRead): boolean {
    return _RETRYABLE_STATUSES.has(String(row.downloadStatus))
}

function isCancellableDownload(row: MediaDownloadViewRead): boolean {
    return ACTIVE_DOWNLOAD_STATUSES.has(String(row.downloadStatus))
}

function defaultDownloadOrder(left: MediaDownloadViewRead, right: MediaDownloadViewRead): number {
    const leftStatus = String(left.downloadStatus)
    const rightStatus = String(right.downloadStatus)
    const leftActive = _ACTIVE_SORT_STATUSES.has(leftStatus)
    const rightActive = _ACTIVE_SORT_STATUSES.has(rightStatus)
    if (leftActive !== rightActive) return leftActive ? -1 : 1

    const leftQueued = leftStatus === 'pending'
    const rightQueued = rightStatus === 'pending'
    if (leftQueued !== rightQueued) return leftQueued ? -1 : 1

    if (leftQueued && rightQueued) {
        const leftPosition = left.queuePosition
        const rightPosition = right.queuePosition

        // A QUEUED operation with no queue position has already claimed a download
        // slot and is waiting for its worker, so it is ahead of the dispatcher queue.
        if (leftPosition == null && rightPosition != null) return -1
        if (leftPosition != null && rightPosition == null) return 1
        if (leftPosition != null && rightPosition != null) return leftPosition - rightPosition
    }

    // Preserve the existing newest-first order within all other groups.
    return 0
}

export default function DownloadsPage() {
    const navigate = useNavigate()
    const qc = useQueryClient()
    const startOperation = useStartOperation()
    const controlOperation = useControlOperation()
    const {data: downloads, isLoading, error} = useMediaDownloadsView()
    const lastFilterPressRef = useRef<{value: string; timestamp: number} | null>(null)
    const [logRow, setLogRow] = useState<MediaDownloadViewRead | null>(null)
    const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set(DEFAULT_STATUS_FILTER))
    const [bulkActionStarting, setBulkActionStarting] = useState<BulkAction | null>(null)
    const [bulkControlBusy, setBulkControlBusy] = useState<string | null>(null)

    const retryAllOperation = useActiveOperation('media_download.bulk_retry', 'media_download')
    const cancelAllOperation = useActiveOperation('media_download.bulk_cancel', 'media_download')

    const toggleStatusFilter = (option: StatusFilterOption) => {
        setStatusFilter((prev) => {
            const next = new Set(prev)
            const enabled = option.statuses.every((status) => next.has(status))
            for (const status of option.statuses) {
                if (enabled) next.delete(status)
                else next.add(status)
            }
            return next
        })
    }

    const pressStatusFilter = (option: StatusFilterOption) => {
        const now = Date.now()
        const previousPress = lastFilterPressRef.current

        // Detect consecutive clicks ourselves so the shortcut also works for touch-generated clicks.
        if (
            previousPress?.value === option.value
            && now - previousPress.timestamp <= FILTER_DOUBLE_PRESS_WINDOW_MS
        ) {
            lastFilterPressRef.current = null
            setStatusFilter(new Set(option.statuses))
            return
        }

        lastFilterPressRef.current = {value: option.value, timestamp: now}
        toggleStatusFilter(option)
    }

    const filteredDownloads = useMemo(
        () => (downloads ?? [])
            .filter((row) => statusFilter.has(String(row.downloadStatus)))
            .sort(defaultDownloadOrder),
        [downloads, statusFilter],
    )
    const retryableDownloads = useMemo(
        () => filteredDownloads.filter(isRetryableDownload),
        [filteredDownloads],
    )
    const cancellableDownloads = useMemo(
        () => filteredDownloads.filter(isCancellableDownload),
        [filteredDownloads],
    )

    const bulkOperationActive = Boolean(
        retryAllOperation
        || cancelAllOperation
        || bulkActionStarting,
    )
    const showActionRow = Boolean(
        retryableDownloads.length
        || cancellableDownloads.length
        || retryAllOperation
        || cancelAllOperation,
    )

    const prioritize = async (row: MediaDownloadViewRead) => {
        try {
            const base = (window as any).appConfig.API_URL
            const r = await fetch(`${base}/media-downloads/${row.id}/prioritize`, {
                method: 'POST',
                credentials: 'include',
            })
            if (!r.ok) {
                const {error: message} = await getErrorMessageFromResponse(r)
                toast.error(message || 'Could not prioritize the download')
            } else {
                toast.success('Download prioritized')
            }
        } catch {
            toast.error('Could not prioritize the download')
        }
        await qc.invalidateQueries({queryKey: ['mediaDownloadsView']})
        if (row.episodeSlug) await qc.invalidateQueries({queryKey: ['episodeDownloads', row.episodeSlug]})
        if (row.movieSlug) await qc.invalidateQueries({queryKey: ['movieDownloads', row.movieSlug]})
    }

    const retryRequest = async (row: MediaDownloadViewRead): Promise<string | null> => {
        try {
            const base = (window as any).appConfig.API_URL
            const r = await fetch(`${base}/media-downloads/${row.id}/retry`, {
                method: 'POST',
                credentials: 'include',
            })
            if (!r.ok) {
                const {error: message} = await getErrorMessageFromResponse(r)
                return message || 'Could not retry the download'
            }
            return null
        } catch {
            return 'Could not retry the download'
        }
    }

    const retry = async (row: MediaDownloadViewRead) => {
        const message = await retryRequest(row)
        if (message) toast.error(message)
        await qc.invalidateQueries({queryKey: ['mediaDownloadsView']})
        if (row.episodeSlug) await qc.invalidateQueries({queryKey: ['episodeDownloads', row.episodeSlug]})
        if (row.movieSlug) await qc.invalidateQueries({queryKey: ['movieDownloads', row.movieSlug]})
    }

    const cancel = async (row: MediaDownloadViewRead) => {
        try {
            const base = (window as any).appConfig.API_URL
            const r = await fetch(`${base}/media-downloads/${row.id}/cancel`, {method: 'POST', credentials: 'include'})
            if (!r.ok) {
                const {error: message} = await getErrorMessageFromResponse(r)
                toast.error(message || 'Could not cancel the download')
            }
        } catch {
            toast.error('Could not cancel the download')
        }
        await qc.invalidateQueries({queryKey: ['mediaDownloadsView']})
        if (row.episodeSlug) await qc.invalidateQueries({queryKey: ['episodeDownloads', row.episodeSlug]})
        if (row.movieSlug) await qc.invalidateQueries({queryKey: ['movieDownloads', row.movieSlug]})
    }

    const startBulkAction = async (action: BulkAction, rows: MediaDownloadViewRead[]) => {
        if (!rows.length || bulkOperationActive) return
        setBulkActionStarting(action)
        try {
            const base = (window as any).appConfig?.API_URL || '/api'
            await startOperation(`${base}/media-downloads/bulk/${action}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mediaDownloadIds: rows.map((row) => row.id)}),
            })
        } catch (actionError) {
            const fallback = action === 'retry'
                ? 'Could not retry the selected downloads'
                : 'Could not cancel the selected downloads'
            toast.error(actionError instanceof Error && actionError.message ? actionError.message : fallback)
        } finally {
            setBulkActionStarting(null)
        }
    }

    const cancelBulkOperation = async (operation: TaskOperationRead) => {
        if (bulkControlBusy) return
        setBulkControlBusy(operation.id)
        try {
            await controlOperation(operation.id, 'cancel')
        } catch (controlError) {
            toast.error(
                controlError instanceof Error && controlError.message
                    ? controlError.message
                    : 'Could not stop the bulk action',
            )
        } finally {
            setBulkControlBusy(null)
        }
    }

    const columns: Column<MediaDownloadViewRead>[] = [
        {
            header: 'Media',
            cell: (row) => (
                <div>
                    <div>{rowTitle(row)}</div>
                    <div style={{color: 'var(--muted, #777)', fontSize: '0.85rem'}}>{rowContext(row)}</div>
                </div>
            ),
            dataLabel: 'Media',
            mobileHidden: true,
            sortAccessor: (row) => rowTitle(row),
            width: '18%',
        },
        {
            header: 'Profile',
            accessor: (row) => row.localMediaProfileName ?? '—',
            dataLabel: 'Profile',
            sortAccessor: (row) => row.localMediaProfileName,
            width: '14%',
        },
        {
            header: 'Format',
            accessor: (row) => row.formatDownloaded ?? '—',
            align: 'center',
            dataLabel: 'Format',
            sortAccessor: (row) => row.formatDownloaded,
            width: '9%',
        },
        {
            header: 'Status',
            cell: (row) => <StatusCell row={row}/>,
            dataLabel: 'Status',
            sortAccessor: (row) => MediaDownloadStatusReg.getLabelLoose(String(row.downloadStatus)),
        },
        {
            header: 'Size',
            accessor: (row) => formatBytes(row.downloadedBytes),
            align: 'right',
            dataLabel: 'Size',
            sortAccessor: (row) => row.downloadedBytes,
            width: '10%',
        },
        {
            header: 'Updated',
            accessor: (row) => formatDateTime(rowTimestamp(row)),
            dataLabel: 'Updated',
            sortAccessor: (row) => rowTimestamp(row),
            width: '16%',
        },
    ]

    return (
        <section className="view" aria-labelledby="downloads-title">
            <div className="view-header">
                <h1 id="downloads-title">Downloads</h1>
                <PageSubtitle summary={<>All media downloads: queued, running, finished, failed and not downloaded.</>}>
                    <p>
                        Every episode and movie download shows up here, one row per Local Media Profile.
                        Running downloads report live progress; failed ones show the error and can be retried.
                        Records without a file or active queue item are marked Not downloaded and can also be retried.
                        Download records are persistent history and cannot be deleted individually.
                    </p>
                </PageSubtitle>
            </div>
            <div className="filter-chip-group" role="group" aria-label="Filter downloads by status">
                {STATUS_FILTER_OPTIONS.map((option) => (
                    <button
                        key={option.value}
                        type="button"
                        className="filter-chip"
                        aria-pressed={option.statuses.every((status) => statusFilter.has(status))}
                        onClick={() => pressStatusFilter(option)}
                    >
                        {option.label}
                    </button>
                ))}
                {!setsEqual(statusFilter, DEFAULT_STATUS_FILTER) && (
                    <button
                        type="button"
                        className="filter-chip-reset"
                        onClick={() => {
                            lastFilterPressRef.current = null
                            setStatusFilter(new Set(DEFAULT_STATUS_FILTER))
                        }}
                    >
                        Reset filters
                    </button>
                )}
            </div>
            {showActionRow && (
                <div className="downloads-action-row" role="group" aria-label="Actions for visible downloads">
                    {(retryableDownloads.length > 0 || retryAllOperation || bulkActionStarting === 'retry') && (
                        <ProgressButton
                            definition={frontendOperationDefinitions['media_download.bulk_retry']}
                            label="Retry all"
                            icon={['fas', 'rotate-right']}
                            onClick={() => void startBulkAction('retry', retryableDownloads)}
                            disabled={bulkOperationActive && !retryAllOperation && bulkActionStarting !== 'retry'}
                            primary={false}
                            starting={bulkActionStarting === 'retry'}
                            active={retryAllOperation !== undefined}
                            progress={retryAllOperation?.progress ?? 0}
                            activeLabel={bulkOperationLabel(retryAllOperation, bulkActionStarting === 'retry')}
                            ariaLabel={`Retry ${retryableDownloads.length} visible retryable downloads`}
                            onCancel={retryAllOperation ? () => void cancelBulkOperation(retryAllOperation) : undefined}
                            cancelDisabled={bulkControlBusy === retryAllOperation?.id}
                            cancelLabel="Cancel retry all"
                        />
                    )}
                    {(cancellableDownloads.length > 0 || cancelAllOperation || bulkActionStarting === 'cancel') && (
                        <ProgressButton
                            definition={frontendOperationDefinitions['media_download.bulk_cancel']}
                            label="Cancel all"
                            icon={['fas', 'ban']}
                            onClick={() => void startBulkAction('cancel', cancellableDownloads)}
                            disabled={bulkOperationActive && !cancelAllOperation && bulkActionStarting !== 'cancel'}
                            primary={false}
                            starting={bulkActionStarting === 'cancel'}
                            active={cancelAllOperation !== undefined}
                            progress={cancelAllOperation?.progress ?? 0}
                            activeLabel={bulkOperationLabel(cancelAllOperation, bulkActionStarting === 'cancel')}
                            ariaLabel={`Cancel ${cancellableDownloads.length} visible active downloads`}
                            onCancel={cancelAllOperation ? () => void cancelBulkOperation(cancelAllOperation) : undefined}
                            cancelDisabled={bulkControlBusy === cancelAllOperation?.id}
                            cancelLabel="Stop cancel all"
                        />
                    )}
                </div>
            )}
            <div className="form-row">
                <DataTable<MediaDownloadViewRead>
                    ariaLabel="Media downloads"
                    columns={columns}
                    data={filteredDownloads}
                    className="table downloads-table"
                    wrapperClassName="table-wrapper downloads-table-wrapper"
                    loading={isLoading}
                    error={error}
                    emptyMessage={
                        downloads && downloads.length > 0
                            ? 'No downloads match the selected filters.'
                            : "No downloads yet. Start one from an episode or movie page."
                    }
                    rowKey={(row) => row.id}
                    rowAriaLabel={(row) => `${rowTitle(row)} (${row.localMediaProfileName})`}
                    mobileSummary={(row) => {
                        const status = String(row.downloadStatus)
                        const statusClass = status === 'downloaded' || status === 'redownloaded'
                            ? 'is-success'
                            : status === 'pending' || status === 'downloading' || status === 'local_processing'
                                ? 'is-progress'
                                : status === 'error' || status === 'missing' || status === 'corrupted'
                                    ? 'is-error'
                                    : ''
                        return (
                            <>
                                <span className="mobile-summary-title">{rowTitle(row)}</span>
                                <span className="mobile-summary-subtitle">{rowContext(row)}</span>
                                <span className="mobile-summary-meta">
                                    <span>{status === 'not_downloaded' ? 'Not downloaded' : status === 'pending' ? 'Queued' : status === 'downloading' ? `${row.progress}%` : status === 'cancelled' ? 'Cancelled' : formatBytes(row.downloadedBytes)}</span>
                                    <span aria-hidden="true">•</span>
                                    <span>{row.formatDownloaded ?? 'Unknown format'}</span>
                                    <span className={`mobile-summary-status ${statusClass}`}>
                                        {MediaDownloadStatusReg.getLabelLoose(status)}
                                    </span>
                                </span>
                            </>
                        )
                    }}
                    mobileRowActionLabel="Open media"
                    onRowClick={(row) => {
                        if (row.movieSlug) navigate(`/movie/${row.movieSlug}`)
                        else if (row.showSlug && row.episodeSlug) navigate(`/show/${row.showSlug}/episode/${row.episodeSlug}`)
                    }}
                    actions={(row) => {
                        const status = String(row.downloadStatus)
                        const actions: DataTableAction<MediaDownloadViewRead>[] = [
                            {
                                onClick: (r) => setLogRow(r),
                                icon: ['fas', 'file-lines'],
                                text: 'View log',
                                classes: 'btn',
                            },
                        ]
                        if (status === 'pending') {
                            actions.push({
                                onClick: () => void prioritize(row),
                                icon: ['fas', 'arrow-up'],
                                text: 'Prioritize',
                                classes: 'btn',
                            })
                        } else if (isRetryableDownload(row)) {
                            actions.push({
                                onClick: () => void retry(row),
                                icon: ['fas', 'rotate-right'],
                                text: 'Retry',
                                classes: 'btn',
                            })
                        }
                        if (isCancellableDownload(row)) {
                            actions.push({
                                onClick: () => void cancel(row),
                                icon: ['fas', 'ban'],
                                text: 'Cancel',
                                classes: 'btn',
                            })
                        }
                        return actions
                    }}
                />
            </div>
            <DownloadLogDialog row={logRow} onClose={() => setLogRow(null)}/>
        </section>
    )
}