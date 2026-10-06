import type {TaskOperationRead} from '../types/schemas/operation'
import {useEffect, useMemo, useRef, useState} from 'react'
import {useNavigate, useSearchParams} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Column, DataTable, DataTableAction} from '../components/DataTable/DataTable'
import DownloadLogDialog from '../components/MediaDownload/DownloadLogDialog'
import ConfirmDialog from '../components/ConfirmDialog/ConfirmDialog'
import {useActiveOperation} from '../components/OperationNotifier/OperationNotifier'
import PageSubtitle from '../components/common/PageSubtitle'
import DownloadProgressStatus from '../components/DownloadProgress/DownloadProgressStatus'
import ProgressButton from '../components/common/ProgressButton'
import {frontendOperationDefinitions} from '../lib/operationDefinitions'
import {useControlOperation, useStartOperation} from '../lib/operations'
import {useMediaDownloadsView} from '../lib/queries'
import {useFilterChipPress} from '../lib/useFilterChipPress'
import {faIcon} from '../icons/faIcon'
import {
    DEFAULT_DOWNLOAD_STATUS_FILTER,
    DOWNLOAD_STATUS_FILTER_OPTIONS,
    DownloadStatusFilterOption,
    downloadStatusFilterFromSearchParams,
    downloadStatusFiltersToSearchParams,
} from '../lib/downloadStatusFilters'
import {MediaDownloadStatusReg} from '../types/media_download'
import {MediaDownloadViewRead} from '../types/schemas/media_download'
import {formatBytes} from '../utils/formatting'
import {getErrorMessageFromResponse} from '../utils/helpers'
import {movieExtraTypeLabel} from '../utils/movieExtras'
import './DownloadsPage.css'

type BulkAction = 'retry' | 'cancel' | 'delete-unavailable'

const DOWNLOAD_PAGE_SIZE = 50

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


function StatusCell({row}: {row: MediaDownloadViewRead}) {
    return <DownloadProgressStatus download={row} compact/>
}

function isRetryableDownload(row: MediaDownloadViewRead): boolean {
    return row.presentation.canRetry
}

function isRedownloadableDownload(row: MediaDownloadViewRead): boolean {
    const status = String(row.downloadStatus)
    return status === 'downloaded' || status === 'redownloaded'
}

function isCancellableDownload(row: MediaDownloadViewRead): boolean {
    return row.presentation.canCancel
}

function isDeletableDownload(row: MediaDownloadViewRead): boolean {
    const status = String(row.downloadStatus)
    return status === 'not_downloaded' || status === 'missing' || status === 'cancelled'
}

function defaultDownloadOrder(left: MediaDownloadViewRead, right: MediaDownloadViewRead): number {
    const leftStatus = String(left.downloadStatus)
    const rightStatus = String(right.downloadStatus)
    const leftActive = left.presentation.active && leftStatus !== 'pending'
    const rightActive = right.presentation.active && rightStatus !== 'pending'
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
    const [searchParams, setSearchParams] = useSearchParams()
    const qc = useQueryClient()
    const startOperation = useStartOperation()
    const controlOperation = useControlOperation()
    const {data: downloads, error} = useMediaDownloadsView()
    const loadingDownloads = downloads === undefined && !error
    const filterPress = useFilterChipPress()
    const loadMoreRef = useRef<HTMLDivElement | null>(null)
    const [logRow, setLogRow] = useState<MediaDownloadViewRead | null>(null)
    const [deleteRow, setDeleteRow] = useState<MediaDownloadViewRead | null>(null)
    const [deleteBusy, setDeleteBusy] = useState(false)
    const [bulkDeleteConfirmOpen, setBulkDeleteConfirmOpen] = useState(false)
    const [statusFilter, setStatusFilter] = useState<Set<string>>(
        () => downloadStatusFilterFromSearchParams(searchParams),
    )
    const [bulkActionStarting, setBulkActionStarting] = useState<BulkAction | null>(null)
    const [bulkControlBusy, setBulkControlBusy] = useState<string | null>(null)
    const [visibleLimit, setVisibleLimit] = useState(DOWNLOAD_PAGE_SIZE)

    const retryAllOperation = useActiveOperation('media_download.bulk_retry', 'media_download')
    const cancelAllOperation = useActiveOperation('media_download.bulk_cancel', 'media_download')
    const deleteUnavailableOperation = useActiveOperation('media_download.bulk_delete_unavailable', 'media_download')

    const applyStatusFilter = (next: Set<string>, replace = false) => {
        setStatusFilter(next)
        setSearchParams(downloadStatusFiltersToSearchParams(next), {replace})
    }

    const toggleStatusFilter = (option: DownloadStatusFilterOption) => {
        const next = new Set(statusFilter)
        const enabled = option.statuses.every((status) => next.has(status))
        for (const status of option.statuses) {
            if (enabled) next.delete(status)
            else next.add(status)
        }
        applyStatusFilter(next)
    }

    const pressStatusFilter = (option: DownloadStatusFilterOption) => {
        filterPress.press(
            option.value,
            () => toggleStatusFilter(option),
            () => applyStatusFilter(new Set(option.statuses)),
        )
    }

    const filteredDownloads = useMemo(
        () => (downloads ?? [])
            .filter((row) => statusFilter.has(String(row.downloadStatus)))
            .sort(defaultDownloadOrder),
        [downloads, statusFilter],
    )
    const visibleDownloads = useMemo(
        () => filteredDownloads.slice(0, visibleLimit),
        [filteredDownloads, visibleLimit],
    )

    useEffect(() => {
        const next = downloadStatusFilterFromSearchParams(searchParams)
        setStatusFilter((current) => setsEqual(current, next) ? current : next)
    }, [searchParams])

    useEffect(() => {
        setVisibleLimit(DOWNLOAD_PAGE_SIZE)
    }, [statusFilter])

    useEffect(() => {
        const element = loadMoreRef.current
        if (!element || visibleLimit >= filteredDownloads.length) return

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    setVisibleLimit((current) => Math.min(current + DOWNLOAD_PAGE_SIZE, filteredDownloads.length))
                }
            },
            {rootMargin: '400px 0px'},
        )
        observer.observe(element)
        return () => observer.disconnect()
    }, [filteredDownloads.length, visibleLimit])

    const retryableDownloads = useMemo(
        () => filteredDownloads.filter((row) => isRetryableDownload(row) || isRedownloadableDownload(row)),
        [filteredDownloads],
    )
    const cancellableDownloads = useMemo(
        () => filteredDownloads.filter(isCancellableDownload),
        [filteredDownloads],
    )
    const deletableDownloads = useMemo(
        () => filteredDownloads.filter(isDeletableDownload),
        [filteredDownloads],
    )

    const bulkOperationActive = Boolean(
        retryAllOperation
        || cancelAllOperation
        || deleteUnavailableOperation
        || bulkActionStarting,
    )
    const showActionRow = Boolean(
        retryableDownloads.length
        || cancellableDownloads.length
        || deletableDownloads.length
        || retryAllOperation
        || cancelAllOperation
        || deleteUnavailableOperation,
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
        if (row.showSlug) await qc.invalidateQueries({queryKey: ['showDownloads', row.showSlug]})
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
        if (row.showSlug) await qc.invalidateQueries({queryKey: ['showDownloads', row.showSlug]})
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
        if (row.showSlug) await qc.invalidateQueries({queryKey: ['showDownloads', row.showSlug]})
    }

    const deleteUnavailable = async () => {
        if (!deleteRow || deleteBusy) return
        setDeleteBusy(true)
        try {
            const base = (window as any).appConfig.API_URL
            const r = await fetch(`${base}/media-downloads/${deleteRow.id}`, {
                method: 'DELETE',
                credentials: 'include',
            })
            if (!r.ok) {
                const {error: message} = await getErrorMessageFromResponse(r)
                toast.error(message || 'Could not delete the download item')
                return
            }

            const row = deleteRow
            setDeleteRow(null)
            await qc.invalidateQueries({queryKey: ['mediaDownloadsView']})
            if (row.episodeSlug) await qc.invalidateQueries({queryKey: ['episodeDownloads', row.episodeSlug]})
            if (row.movieSlug) await qc.invalidateQueries({queryKey: ['movieDownloads', row.movieSlug]})
        } catch {
            toast.error('Could not delete the download item')
        } finally {
            setDeleteBusy(false)
        }
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
                : action === 'cancel'
                    ? 'Could not cancel the selected downloads'
                    : 'Could not delete the selected download items'
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
            cell: (row) => <span className="downloads-format-value">{row.formatDownloaded ?? '—'}</span>,
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
            accessor: (row) => formatBytes(row.artifactSizeBytes) || '—',
            align: 'right',
            dataLabel: 'Size',
            sortAccessor: (row) => row.artifactSizeBytes,
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
                        Download records are persistent history; Not downloaded, Missing, and Cancelled records can be deleted individually or in bulk when no artifact is available.
                    </p>
                </PageSubtitle>
            </div>
            <div className="downloads-filter-row">
                <div className="filter-chip-group" role="group" aria-label="Filter downloads by status">
                    {DOWNLOAD_STATUS_FILTER_OPTIONS.map((option) => (
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
                    {!setsEqual(statusFilter, DEFAULT_DOWNLOAD_STATUS_FILTER) && (
                    <button
                        type="button"
                        className="filter-chip-reset"
                        onClick={() => {
                            filterPress.reset()
                            applyStatusFilter(new Set(DEFAULT_DOWNLOAD_STATUS_FILTER), true)
                        }}
                    >
                        Reset filters
                    </button>
                    )}
                </div>
                <strong className="downloads-view-count">
                    {filteredDownloads.length.toLocaleString()} {filteredDownloads.length === 1 ? 'download' : 'downloads'}
                </strong>
            </div>
            {showActionRow && (
                <div className="downloads-action-row" role="group" aria-label="Actions for visible downloads">
                    {(retryableDownloads.length > 0 || retryAllOperation || bulkActionStarting === 'retry') && (
                        <ProgressButton
                            definition={frontendOperationDefinitions['media_download.bulk_retry']}
                            label="Retry all"
                            icon={faIcon('fas', 'rotate-right')}
                            onClick={() => void startBulkAction('retry', retryableDownloads)}
                            disabled={bulkOperationActive && !retryAllOperation && bulkActionStarting !== 'retry'}
                            primary={false}
                            starting={bulkActionStarting === 'retry'}
                            active={retryAllOperation !== undefined}
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
                            icon={faIcon('fas', 'ban')}
                            onClick={() => void startBulkAction('cancel', cancellableDownloads)}
                            disabled={bulkOperationActive && !cancelAllOperation && bulkActionStarting !== 'cancel'}
                            primary={false}
                            starting={bulkActionStarting === 'cancel'}
                            active={cancelAllOperation !== undefined}
                            ariaLabel={`Cancel ${cancellableDownloads.length} visible active downloads`}
                            onCancel={cancelAllOperation ? () => void cancelBulkOperation(cancelAllOperation) : undefined}
                            cancelDisabled={bulkControlBusy === cancelAllOperation?.id}
                            cancelLabel="Stop cancel all"
                        />
                    )}
                    {(deletableDownloads.length > 0 || deleteUnavailableOperation || bulkActionStarting === 'delete-unavailable') && (
                        <ProgressButton
                            definition={frontendOperationDefinitions['media_download.bulk_delete_unavailable']}
                            label="Delete unavailable"
                            icon={faIcon('fas', 'trash')}
                            onClick={() => setBulkDeleteConfirmOpen(true)}
                            disabled={bulkOperationActive && !deleteUnavailableOperation && bulkActionStarting !== 'delete-unavailable'}
                            primary={false}
                            starting={bulkActionStarting === 'delete-unavailable'}
                            active={deleteUnavailableOperation !== undefined}
                            ariaLabel={`Delete ${deletableDownloads.length} visible unavailable download records`}
                            onCancel={deleteUnavailableOperation ? () => void cancelBulkOperation(deleteUnavailableOperation) : undefined}
                            cancelDisabled={bulkControlBusy === deleteUnavailableOperation?.id}
                            cancelLabel="Stop deleting unavailable download records"
                        />
                    )}
                </div>
            )}
            <div className="form-row">
                <DataTable<MediaDownloadViewRead>
                    ariaLabel="Media downloads"
                    columns={columns}
                    data={visibleDownloads}
                    className="table downloads-table"
                    wrapperClassName="table-wrapper downloads-table-wrapper"
                    loading={loadingDownloads}
                    loadingMessage={
                        <span className="downloads-table-loading" role="status" aria-label="Loading downloads">
                            <FontAwesomeIcon icon={faIcon('fas', 'spinner')} spin aria-hidden="true"/>
                        </span>
                    }
                    error={error}
                    emptyMessage={
                        downloads && downloads.length > 0
                            ? 'No downloads match the selected filters.'
                            : "No downloads yet. Start one from an episode or movie page."
                    }
                    rowKey={(row) => row.id}
                    rowAriaLabel={(row) => `${rowTitle(row)} (${row.localMediaProfileName})`}
                    mobileSummary={(row) => (
                        <>
                            <span className="mobile-summary-title">{rowTitle(row)}</span>
                            <span className="mobile-summary-subtitle">{rowContext(row)}</span>
                            <DownloadProgressStatus download={row} compact details={false}/>
                            <span className="mobile-summary-meta">
                                <span>{formatBytes(row.artifactSizeBytes)}</span>
                                <span>{row.formatDownloaded ?? 'Unknown format'}</span>
                            </span>
                        </>
                    )}
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
                                icon: faIcon('fas', 'file-lines'),
                                text: 'View log',
                                classes: 'btn',
                            },
                        ]
                        if (status === 'not_downloaded') {
                            actions.push({
                                onClick: () => void retry(row),
                                icon: faIcon('fas', 'download'),
                                text: 'Download',
                                classes: 'btn',
                            })
                        } else if (status === 'pending') {
                            actions.push({
                                onClick: () => void prioritize(row),
                                icon: faIcon('fas', 'arrow-up'),
                                text: 'Prioritize',
                                classes: 'btn',
                            })
                        } else if (isRetryableDownload(row) || isRedownloadableDownload(row)) {
                            actions.push({
                                onClick: () => void retry(row),
                                icon: faIcon('fas', 'rotate-right'),
                                text: isRedownloadableDownload(row) ? 'Re-download' : 'Retry',
                                classes: 'btn',
                            })
                        }
                        if (isCancellableDownload(row)) {
                            actions.push({
                                onClick: () => void cancel(row),
                                icon: faIcon('fas', 'ban'),
                                text: 'Cancel',
                                classes: 'btn',
                            })
                        }
                        if (isDeletableDownload(row)) {
                            actions.push({
                                onClick: () => setDeleteRow(row),
                                icon: faIcon('fas', 'trash'),
                                text: 'Delete',
                                classes: 'btn btn-danger',
                            })
                        }
                        return actions
                    }}
                />
                <div ref={loadMoreRef} className="infinite-scroll-sentinel" aria-hidden="true"/>
                {visibleDownloads.length < filteredDownloads.length && (
                    <div className="downloads-table-loading" role="status">
                        <FontAwesomeIcon className="wl-progress-icon" icon={faIcon('fas', 'spinner')}/>
                        Loading more downloads...
                    </div>
                )}
            </div>
            <DownloadLogDialog row={logRow} onClose={() => setLogRow(null)}/>
            <ConfirmDialog
                open={bulkDeleteConfirmOpen}
                title="Delete download records"
                onDismiss={() => setBulkDeleteConfirmOpen(false)}
                icon={faIcon('fas', 'trash')}
                iconTone="danger"
                confirmButton={{
                    label: 'Delete',
                    onClick: async () => {
                        setBulkDeleteConfirmOpen(false)
                        await startBulkAction('delete-unavailable', deletableDownloads)
                    },
                    className: 'btn btn-danger',
                }}
            >
                <p>
                    Delete {deletableDownloads.length} visible Missing, Not downloaded, or Cancelled {deletableDownloads.length === 1 ? 'record' : 'records'}?
                    WireLoft will verify that no artifact is available before deleting each download record.
                    Records with an available artifact will be kept.
                </p>
            </ConfirmDialog>
            <ConfirmDialog
                open={deleteRow !== null}
                title="Delete download record"
                onDismiss={() => {
                    if (!deleteBusy) setDeleteRow(null)
                }}
                icon={faIcon('fas', 'trash')}
                iconTone="danger"
                confirmButton={{
                    label: deleteBusy ? 'Deleting…' : 'Delete',
                    onClick: deleteUnavailable,
                    className: 'btn btn-danger',
                    disabled: deleteBusy,
                    icon: deleteBusy ? faIcon('fas', 'spinner') : undefined,
                    iconSpin: deleteBusy,
                }}
                cancelButton={{disabled: deleteBusy}}
                dismissOnOverlayClick={!deleteBusy}
            >
                <p>
                    Delete the download record for &quot;{deleteRow ? rowTitle(deleteRow) : ''}&quot;?
                    WireLoft will verify that no artifact is available before removing its history record.
                </p>
            </ConfirmDialog>
        </section>
    )
}