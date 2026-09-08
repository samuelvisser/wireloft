import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useTaskLedger} from '../../lib/queries'
import {ACTIVE_DOWNLOAD_STATUSES, MediaDownloadStatusReg} from '../../types/media_download'
import {PUBLISH_STATUS_LABELS} from '../../types/episode'
import {MediaDownloadViewRead} from '../../types/schemas/media_download'
import {TaskLedgerEntryRead} from '../../types/schemas/task'
import {movieExtraTypeLabel} from '../../utils/movieExtras'

type Props = {
    row: MediaDownloadViewRead | null
    onClose: () => void
}

function formatDateTime(value: string | null | undefined): string {
    if (!value) return '—'
    try {
        const normalized = /(?:Z|[+-]\d\d:\d\d)$/i.test(value) ? value : `${value}Z`
        return new Date(normalized).toLocaleString()
    } catch {
        return String(value)
    }
}

function attemptLabel(isRedownload: boolean | null | undefined): string | null {
    if (isRedownload === true) return 'Redownload'
    if (isRedownload === false) return 'Initial download'
    return null
}

function mediaTypeLabel(type: string, movieExtraType?: string | null): string {
    if (type === 'movie') return 'Movie'
    if (type === 'movie_extra') return movieExtraTypeLabel(movieExtraType)
    if (type === 'episode') return 'Episode'
    return type ? type.replace(/_/g, ' ').replace(/^./, (char) => char.toUpperCase()) : 'Media'
}

function mediaTitle(row: MediaDownloadViewRead): string {
    return row.mediaTitle ?? row.movieTitle ?? row.episodeTitle ?? 'Download log'
}

function resultData(run: TaskLedgerEntryRead): Record<string, unknown> {
    const result = run.result
    if (!result || typeof result !== 'object') return {}
    const data = result.data
    return data && typeof data === 'object' && !Array.isArray(data)
        ? data as Record<string, unknown>
        : {}
}

function isRedownload(run: TaskLedgerEntryRead): boolean {
    const inputValue = run.inputs.is_redownload
    if (typeof inputValue === 'boolean') return inputValue
    return resultData(run).is_redownload === true
}

function presentationStatus(run: TaskLedgerEntryRead): string {
    if (run.status === 'FAILED') return 'error'
    if (run.status === 'CANCELED') return 'cancelled'
    if (run.status === 'RUNNING') return 'downloading'
    if (run.status === 'SUCCEEDED') return isRedownload(run) ? 'redownloaded' : 'downloaded'
    return 'pending'
}

function runError(run: TaskLedgerEntryRead): string | null {
    if (run.lastError) return run.lastError
    return run.status === 'FAILED' ? run.message ?? null : null
}

/** Full detail view for one download row: current state plus canonical TaskRun history. */
export default function DownloadLogDialog({row, onClose}: Props) {
    const definitionKey = row?.type === 'episode' ? 'download_episode' : 'download_movie'
    const ledger = useTaskLedger({
        definitionKey,
        resourceType: 'media_download',
        resourceId: row?.id,
        enabled: row !== null,
    })

    if (!row) return null

    const attempts = ledger.data?.pages.flatMap((page) => page.items) ?? []
    const currentAttempt = attemptLabel(row.isRedownloadAttempt)
    const downloadedVersion = row.downloadedPublishStatus
        ? PUBLISH_STATUS_LABELS[row.downloadedPublishStatus] ?? row.downloadedPublishStatus
        : null
    const isActive = ACTIVE_DOWNLOAD_STATUSES.has(String(row.downloadStatus))

    return (
        <div className="modal-overlay" role="presentation" onClick={onClose}>
            <div
                className="modal modal-wide"
                role="dialog"
                aria-modal="true"
                aria-labelledby="download-log-title"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="modal-header">
                    <div className="modal-icon" aria-hidden>
                        <FontAwesomeIcon icon={['fas', 'file-lines']}/>
                    </div>
                    <h2 id="download-log-title" className="modal-title">
                        {mediaTitle(row)}
                    </h2>
                </div>

                <dl className="log-meta">
                    <div><dt>Media type</dt><dd>{mediaTypeLabel(String(row.type), row.movieExtraType)}</dd></div>
                    {row.type === 'movie_extra' && <div><dt>Movie</dt><dd>{row.movieTitle ?? '—'}</dd></div>}
                    {row.type === 'episode' && <div><dt>Show</dt><dd>{row.showTitle ?? '—'}</dd></div>}
                    <div><dt>Profile</dt><dd>{row.localMediaProfileName ?? '—'}</dd></div>
                    <div>
                        <dt>Current status</dt>
                        <dd>
                            {MediaDownloadStatusReg.getLabelLoose(String(row.downloadStatus))}
                            {isActive ? ` (${row.progress}%)` : ''}
                        </dd>
                    </div>
                    {currentAttempt && <div><dt>Current attempt</dt><dd>{currentAttempt}</dd></div>}
                    {downloadedVersion && <div><dt>Version downloaded</dt><dd>{downloadedVersion}</dd></div>}
                    <div><dt>File</dt><dd className="mono">{row.filePath}</dd></div>
                </dl>

                <p className="modal-text log-section-label">Attempt history</p>
                {ledger.isLoading ? (
                    <p className="modal-text">Loading…</p>
                ) : ledger.isError ? (
                    <p className="modal-text">Could not load attempt history.</p>
                ) : attempts.length === 0 ? (
                    <p className="modal-text">No task runs recorded yet.</p>
                ) : (
                    <div className="log-attempts">
                        {attempts.map((run) => {
                            const status = presentationStatus(run)
                            const error = runError(run)
                            return (
                                <div key={run.id} className="log-attempt">
                                    <div className="log-attempt-header">
                                        <span className={`log-attempt-status log-attempt-status-${status}`}>
                                            {MediaDownloadStatusReg.getLabelLoose(status)}
                                        </span>
                                        <span className="log-attempt-type">
                                            {isRedownload(run) ? 'Redownload' : 'Initial download'}
                                        </span>
                                        <span className="log-attempt-time">
                                            {formatDateTime(run.finishedAt ?? run.startedAt)}
                                        </span>
                                    </div>
                                    {error && <pre className="log-output">{error}</pre>}
                                </div>
                            )
                        })}
                    </div>
                )}

                {ledger.hasNextPage && (
                    <div className="modal-actions">
                        <button
                            type="button"
                            className="btn"
                            disabled={ledger.isFetchingNextPage}
                            onClick={() => void ledger.fetchNextPage()}
                        >
                            {ledger.isFetchingNextPage ? 'Loading…' : 'Load older attempts'}
                        </button>
                    </div>
                )}

                <div className="modal-actions">
                    <button type="button" className="btn" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    )
}
