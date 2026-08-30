import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useMediaDownloadAttempts} from '../../lib/queries'
import {ACTIVE_DOWNLOAD_STATUSES, MediaDownloadStatusReg} from '../../types/media_download'
import {PUBLISH_STATUS_LABELS} from '../../types/episode'
import {MediaDownloadViewRead} from '../../types/schemas/media_download'

type Props = {
    row: MediaDownloadViewRead | null
    onClose: () => void
}

function formatDateTime(value: Date | null | undefined): string {
    if (!value) return '—'
    try {
        return value.toLocaleString()
    } catch {
        return String(value)
    }
}

function attemptLabel(isRedownload: boolean | null | undefined): string | null {
    if (isRedownload === true) return 'Redownload'
    if (isRedownload === false) return 'Initial download'
    return null
}

/** Full detail view for one download row: current state plus its permanent attempt ledger. */
export default function DownloadLogDialog({row, onClose}: Props) {
    // Called unconditionally (Rules of Hooks): disabled via `enabled` while row is null.
    const {data: attempts, isLoading} = useMediaDownloadAttempts(row?.id)

    if (!row) return null

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
                        {row.movieTitle ?? row.episodeTitle ?? 'Download log'}
                    </h2>
                </div>

                <dl className="log-meta">
                    <div><dt>Media type</dt><dd>{row.movieTitle ? 'Movie' : 'Episode'}</dd></div>
                    {!row.movieTitle && <div><dt>Show</dt><dd>{row.showTitle ?? '—'}</dd></div>}
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
                {isLoading ? (
                    <p className="modal-text">Loading…</p>
                ) : !attempts || attempts.length === 0 ? (
                    <p className="modal-text">No completed attempts yet.</p>
                ) : (
                    <div className="log-attempts">
                        {attempts.map((a) => (
                            <div key={a.id} className="log-attempt">
                                <div className="log-attempt-header">
                                    <span className={`log-attempt-status log-attempt-status-${String(a.status)}`}>
                                        {MediaDownloadStatusReg.getLabelLoose(String(a.status))}
                                    </span>
                                    <span className="log-attempt-type">
                                        {a.isRedownload ? 'Redownload' : 'Initial download'}
                                    </span>
                                    <span className="log-attempt-time">{formatDateTime(a.finishedAt ?? a.startedAt)}</span>
                                </div>
                                {a.errorMessage && <pre className="log-output">{a.errorMessage}</pre>}
                            </div>
                        ))}
                    </div>
                )}

                <div className="modal-actions">
                    <button type="button" className="btn" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    )
}
