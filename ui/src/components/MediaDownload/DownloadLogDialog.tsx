import {useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'
import {getErrorMessageFromResponse} from '../../utils/helpers'
import DownloadStageTimings from '../DownloadProgress/DownloadStageTimings'
import DownloadProgressStatus from '../DownloadProgress/DownloadProgressStatus'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useMediaDownloadHistory} from '../../lib/mediaDownloadHistory'
import {MediaDownloadStatusReg} from '../../types/media_download'
import {PUBLISH_STATUS_LABELS} from '../../types/episode'
import {MediaDownloadViewRead} from '../../types/schemas/media_download'
import {movieExtraTypeLabel} from '../../utils/movieExtras'
import {faIcon} from '../../icons/faIcon'

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
    const qc = useQueryClient()
    const [confirmDelete, setConfirmDelete] = useState(false)
    const [deleteBusy, setDeleteBusy] = useState(false)

    const deleteDownload = async () => {
        if (!row || deleteBusy) return
        setDeleteBusy(true)
        try {
            const base = (window as any).appConfig.API_URL
            const response = await fetch(`${base}/media-downloads/${row.id}`, {
                method: 'DELETE',
                credentials: 'include',
            })
            if (!response.ok) {
                const {error} = await getErrorMessageFromResponse(response)
                toast.error(error || 'Could not delete the download')
                return
            }

            setConfirmDelete(false)
            onClose()
            toast.success('Download, history and files deleted')
            qc.removeQueries({queryKey: ['mediaDownloadHistory', row.id], exact: true})
            // A download is shown in multiple places, not just the Downloads page.
            for (const queryKey of [
                ['mediaDownloads'],
                ['mediaDownloadsView'],
                ['episodeDownloads'],
                ['showDownloads'],
                ['movieDownloads'],
                ['movies'],
                ['localMediaProfiles'],
            ]) {
                void qc.invalidateQueries({queryKey})
            }
        } catch {
            toast.error('Could not delete the download')
        } finally {
            setDeleteBusy(false)
        }
    }

    if (!row) return null

    const entries = history.data?.pages.flatMap((page) => page.items) ?? []
    const currentAttempt = attemptLabel(row.isRedownloadAttempt)
    const downloadedVersion = row.downloadedPublishStatus
        ? PUBLISH_STATUS_LABELS[row.downloadedPublishStatus] ?? row.downloadedPublishStatus
        : null

    return (
        <>
            <div className="modal-overlay" role="presentation" onClick={() => {
                if (!deleteBusy && !confirmDelete) onClose()
            }}>
                <div
                    className="modal modal-wide download-log-dialog"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="download-log-title"
                    onClick={(e) => e.stopPropagation()}
                >
                    <div className="modal-header">
                        <div className="modal-icon" aria-hidden>
                            <FontAwesomeIcon icon={faIcon('fass', 'file-lines')}/>
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
                                <DownloadProgressStatus download={row}/>
                            </dd>
                        </div>
                        {currentAttempt && <div><dt>Current attempt</dt><dd>{currentAttempt}</dd></div>}
                        {downloadedVersion && <div><dt>Version downloaded</dt><dd>{downloadedVersion}</dd></div>}
                    </dl>

                    <div className="log-history-scroll">
                        <dl className="log-meta log-file-meta">
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
                                        <DownloadStageTimings value={entry.metadata.lifecycle}/>
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
                            <div className="modal-actions log-history-actions">
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
                    </div>

                    <div className="modal-actions log-dialog-actions">
                        <button
                            type="button"
                            className="btn btn-danger log-dialog-delete"
                            disabled={deleteBusy}
                            onClick={() => setConfirmDelete(true)}
                        >
                            Delete download
                        </button>
                        <button type="button" className="btn" disabled={deleteBusy} onClick={onClose}>Close</button>
                    </div>
                </div>
            </div>
            <ConfirmDialog
                open={confirmDelete}
                title="Delete download and files?"
                onDismiss={() => {
                    if (!deleteBusy) setConfirmDelete(false)
                }}
                icon={faIcon('fass', 'trash')}
                iconTone="danger"
                confirmButton={{
                    label: deleteBusy ? 'Deleting…' : 'Delete download',
                    onClick: deleteDownload,
                    className: 'btn btn-danger',
                    disabled: deleteBusy,
                    icon: deleteBusy ? faIcon('fass', 'spinner') : undefined,
                    iconSpin: deleteBusy,
                }}
                cancelButton={{disabled: deleteBusy}}
                dismissOnOverlayClick={!deleteBusy}
            >
                <p>
                    Permanently delete the download for &quot;{mediaTitle(row)}&quot;?
                    This will stop any active download and remove its record, download history,
                    media file and associated downloaded files from the filesystem.
                </p>
                <p>This action cannot be undone. Automatic Download Profiles may download the media again later.</p>
            </ConfirmDialog>
        </>
    )
}
