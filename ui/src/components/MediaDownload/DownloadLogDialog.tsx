import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {MediaDownloadStatusReg} from '../../types/media_download'
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

function attemptLabel(row: MediaDownloadViewRead): string | null {
    if (row.isRedownloadAttempt === true) return 'Redownload'
    if (row.isRedownloadAttempt === false) return 'Initial download'
    return null
}

/** Full detail view for one download row: attempt type, versions, timestamps and the full error. */
export default function DownloadLogDialog({row, onClose}: Props) {
    if (!row) return null

    const attempt = attemptLabel(row)
    const downloadedVersion = row.downloadedPublishStatus
        ? PUBLISH_STATUS_LABELS[row.downloadedPublishStatus] ?? row.downloadedPublishStatus
        : null

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
                        {row.episodeTitle ?? 'Download log'}
                    </h2>
                </div>

                <dl className="log-meta">
                    <div><dt>Show</dt><dd>{row.showTitle ?? '—'}</dd></div>
                    <div><dt>Profile</dt><dd>{row.localMediaProfileName ?? '—'}</dd></div>
                    <div><dt>Status</dt><dd>{MediaDownloadStatusReg.getLabelLoose(String(row.downloadStatus))}</dd></div>
                    {attempt && <div><dt>Attempt</dt><dd>{attempt}</dd></div>}
                    {downloadedVersion && <div><dt>Version downloaded</dt><dd>{downloadedVersion}</dd></div>}
                    <div><dt>Started</dt><dd>{formatDateTime(row.startedAt)}</dd></div>
                    <div><dt>Finished</dt><dd>{formatDateTime(row.finishedAt)}</dd></div>
                    <div><dt>File</dt><dd className="mono">{row.filePath}</dd></div>
                </dl>

                {row.errorMessage ? (
                    <>
                        <p className="modal-text log-section-label">Full error</p>
                        <pre className="log-output">{row.errorMessage}</pre>
                    </>
                ) : (
                    <p className="modal-text">No errors recorded for this download.</p>
                )}

                <div className="modal-actions">
                    <button type="button" className="btn" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    )
}
