import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useMediaDownloadHistory} from '../../lib/mediaDownloadHistory'
import {ACTIVE_DOWNLOAD_STATUSES, MediaDownloadStatusReg} from '../../types/media_download'
import {PUBLISH_STATUS_LABELS} from '../../types/episode'
import {MediaDownloadViewRead} from '../../types/schemas/media_download'
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

/** Full detail view for one download row: current state plus durable action history. */
export default function DownloadLogDialog({row, onClose}: Props) {
    const history = useMediaDownloadHistory(row?.id)

    if (!row) return null

    const entries = history.data?.pages.flatMap((page) => page.items) ?? []
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

                <p className="modal-text log-section-label">Download history</p>
                {history.isLoading ? (
                    <p className="modal-text">Loading…</p>
                ) : history.isError ? (
                    <p className="modal-text">Could not load download history.</p>
                ) : entries.length === 0 ? (
                    <p className="modal-text">No history recorded yet.</p>
                ) : (
                    <div className="log-attempts">
                        {entries.map((entry) => (
                            <div key={entry.id} className="log-attempt">
                                <div className="log-attempt-header">
                                    <span className={`log-attempt-status log-attempt-status-${entry.status}`}>
                                        {MediaDownloadStatusReg.getLabelLoose(entry.status)}
                                    </span>
                                    <span className="log-attempt-type">{entry.label}</span>
                                    <span className="log-attempt-time">
                                        {formatDateTime(entry.occurredAt)}
                                    </span>
                                </div>
                                {(entry.duration || entry.detail) && (
                                    <div className="log-attempt-details">
                                        {entry.duration && <span>Duration: {entry.duration}</span>}
                                        {entry.detail && <span>{entry.detail}</span>}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {history.hasNextPage && (
                    <div className="modal-actions">
                        <button
                            type="button"
                            className="btn"
                            disabled={history.isFetchingNextPage}
                            onClick={() => void history.fetchNextPage()}
                        >
                            {history.isFetchingNextPage ? 'Loading…' : 'Load older history'}
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
