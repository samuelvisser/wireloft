import {useState} from 'react'
import {Link, useParams} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {library} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@awesome.me/kit-83fa1ac5a9/icons'
import {useShow, useEpisode, useEpisodeDownloads, useLocalMediaProfiles} from '../../lib/queries'
import {PreferredFormatReg} from '../../types/local_media_profile'
import {MediaDownloadStatusReg} from '../../types/media_download'
import {EpisodePublishStatus, PUBLISH_STATUS_LABELS} from '../../types/episode'
import {MediaDownloadViewRead} from '../../types/schemas/media_download'
import {LocalMediaProfileRead} from '../../types/schemas/local_media_profile'
import {getErrorMessageFromResponse} from '../../utils/helpers'
import ProgressBar from '../../components/common/ProgressBar'
import DownloadLogDialog from '../../components/MediaDownload/DownloadLogDialog'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)

function formatDate(value: Date | string | null | undefined) {
    if (!value) return '—'
    const d = value instanceof Date ? value : new Date(value)
    try {
        const year = d.getFullYear()
        const month = String(d.getMonth() + 1).padStart(2, '0')
        const day = String(d.getDate()).padStart(2, '0')
        const hours = String(d.getHours()).padStart(2, '0')
        const minutes = String(d.getMinutes()).padStart(2, '0')
        return `${year}-${month}-${day} ${hours}:${minutes}`
    } catch {
        return d?.toString() ?? ''
    }
}

function formatBytes(n: number | null | undefined) {
    if (!n && n !== 0) return ''
    if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GiB`
    if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MiB`
    return `${Math.round(n / 1024)} KiB`
}

function ProfileDownloadRow({
    profile,
    download,
    episodeSlug,
}: {
    profile: LocalMediaProfileRead
    download?: MediaDownloadViewRead
    episodeSlug: string
}) {
    const qc = useQueryClient()
    const [busy, setBusy] = useState(false)
    const [showLog, setShowLog] = useState(false)

    const invalidate = () =>
        Promise.all([
            qc.invalidateQueries({queryKey: ['episodeDownloads', episodeSlug]}),
            qc.invalidateQueries({queryKey: ['mediaDownloadsView']}),
        ])

    async function request(url: string, init: RequestInit, failure: string) {
        setBusy(true)
        try {
            const r = await fetch(url, {credentials: 'include', ...init})
            if (!r.ok) {
                const {error} = await getErrorMessageFromResponse(r)
                toast.error(error || failure)
            }
            await invalidate()
        } catch {
            toast.error(failure)
        } finally {
            setBusy(false)
        }
    }

    const startDownload = () =>
        request(
            `${(window as any).appConfig.API_URL}/episodes/${encodeURIComponent(episodeSlug)}/downloads`,
            {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({localMediaProfileId: profile.id}),
            },
            'Could not start the download',
        )

    const retryDownload = () =>
        request(
            `${(window as any).appConfig.API_URL}/media-downloads/${download!.id}/retry`,
            {method: 'POST'},
            'Could not retry the download',
        )

    const status = download ? String(download.downloadStatus) : null

    return (
        <div className="download-row" role="listitem" aria-label={`Download for ${profile.name}`}>
            <div className="download-row-info">
                <div className="download-row-name">{profile.name}</div>
                <div className="download-row-format">{PreferredFormatReg.getLabelLoose(profile.preferredFormat)}</div>
            </div>
            <div className="download-row-state">
                {!download && (
                    <button className="btn btn-primary" onClick={startDownload} disabled={busy}>
                        <FontAwesomeIcon icon={['fas', 'download']}/> Download
                    </button>
                )}
                {download && (status === 'pending' || status === 'downloading') && (
                    <div className="download-row-progress" aria-live="polite">
                        <ProgressBar value={download.progress} ariaLabel={`Download progress for ${profile.name}`}/>
                        <span className="download-row-progress-label">
                            {status === 'pending' ? 'Queued…' : `${download.progress}%`}
                        </span>
                    </div>
                )}
                {download && status === 'downloaded' && (
                    <div className="download-row-done">
                        <span className="download-state-ok">
                            <FontAwesomeIcon icon={['fas', 'circle-check']}/>{' '}
                            Downloaded{download.formatDownloaded ? ` (${download.formatDownloaded}` : ''}
                            {download.formatDownloaded && download.downloadedBytes ? `, ${formatBytes(download.downloadedBytes)})` : download.formatDownloaded ? ')' : ''}
                        </span>
                        <div className="download-row-path mono truncate" title={download.filePath}>{download.filePath}</div>
                    </div>
                )}
                {download && (status === 'error' || status === 'missing' || status === 'corrupted') && (
                    <div className="download-row-error">
                        <span className="download-state-error">
                            <FontAwesomeIcon icon={['fas', 'circle-exclamation']}/>{' '}
                            {download.errorMessage || MediaDownloadStatusReg.getLabelLoose(status)}
                        </span>
                        <button className="btn" onClick={retryDownload} disabled={busy}>
                            <FontAwesomeIcon icon={['fas', 'rotate-right']}/> Retry
                        </button>
                    </div>
                )}
                {download && status === 'cancelled' && (
                    <div className="download-row-error">
                        <span>{MediaDownloadStatusReg.getLabelLoose(status)}</span>
                        <button className="btn" onClick={startDownload} disabled={busy}>
                            <FontAwesomeIcon icon={['fas', 'download']}/> Download
                        </button>
                    </div>
                )}
                {download && status && !['pending', 'downloading', 'downloaded', 'cancelled', 'error', 'missing', 'corrupted'].includes(status) && (
                    <span>{MediaDownloadStatusReg.getLabelLoose(status)}</span>
                )}
            </div>
            {download && (
                <button
                    type="button"
                    className="icon-btn"
                    onClick={() => setShowLog(true)}
                    title="View log"
                    aria-label={`View log for ${profile.name}`}
                >
                    <FontAwesomeIcon icon={['fas', 'file-lines']}/>
                </button>
            )}
            <DownloadLogDialog row={showLog ? (download ?? null) : null} onClose={() => setShowLog(false)}/>
        </div>
    )
}

export default function EpisodePage() {
    const {id: showId, episodeId} = useParams()

    const {data: show, isLoading, error} = useShow(showId)
    const {data: episode, isLoading: isLoadingEpisode} = useEpisode(episodeId)
    const {data: profiles} = useLocalMediaProfiles()
    const {data: downloads} = useEpisodeDownloads(episodeId)
    const showProfiles = profiles?.filter((profile) => profile.type === 'show')

    if (!showId) {
        return (
            <section className="view episode-view">
                <div className="view-header">
                    <h1>Episode</h1>
                </div>
                <p>Show not found.</p>
                <p><Link to="/">Go home</Link></p>
            </section>
        )
    }

    if (isLoading && !show) {
        return (
            <section className="view episode-view">
                <div className="view-header">
                    <h1>Episode</h1>
                </div>
                <p>Loading episode...</p>
            </section>
        )
    }

    if (!show) {
        return (
            <section className="view episode-view">
                <div className="view-header">
                    <h1>Episode</h1>
                </div>
                <p>{(error as any)?.message ?? 'Show not found.'}</p>
                <p><Link to="/">Go home</Link></p>
            </section>
        )
    }

    if (isLoadingEpisode && !episode) {
        return (
            <section className="view episode-view">
                <div className="view-header">
                    <h1>Episode</h1>
                </div>
                <p>Loading episode...</p>
            </section>
        )
    }

    if (!episode) {
        return (
            <section className="view episode-view">
                <div className="view-header">
                    <h1>Episode</h1>
                </div>
                <p>Episode not found.</p>
                <p><Link to={`/show/${showId}`}>Back to show</Link></p>
            </section>
        )
    }

    const publishStatus = String(episode.publishStatus)
    const statusLabel = PUBLISH_STATUS_LABELS[publishStatus] ?? publishStatus
    const isLive = publishStatus === 'live' || publishStatus === EpisodePublishStatus.live
    const isDownloadable = !episode.isNoShowToday && (
        publishStatus === 'published_final' || publishStatus === EpisodePublishStatus.publishedFinal
    )

    // Placeholder cover image
    const coverUrl: string = episode.thumbnailPortraitPath || `https://placehold.co/640x360/png?text=Episode+%23${episode.index}`

    const downloadByProfileId = new Map<number, MediaDownloadViewRead>(
        (downloads ?? []).map((d) => [d.localMediaProfileId, d]),
    )

    return (
        <section className="view episode-view" aria-labelledby="episode-title">
            <div className="view-header">
                <h1 id="episode-title">Episode</h1>
            </div>

            <article className="episode-details" aria-label="Episode details">
                <header className="episode-header">
                    <div className="episode-show"><Link to={`/show/${showId}`}>{show.title}</Link></div>
                    <div className="episode-title-text">{episode.title}</div>
                </header>

                <div className="episode-content">
                    <div className="episode-cover">
                        <img src={coverUrl} alt="Episode cover"/>
                        {isLive && (
                            <span className="episode-live-badge" aria-label="Episode is live">Live</span>
                        )}
                    </div>
                    <div className="episode-meta">
                        <table className="meta-table">
                            <tbody>
                            <tr>
                                <th scope="row">Title</th>
                                <td>{episode.title}</td>
                            </tr>
                            <tr>
                                <th scope="row">Status</th>
                                <td>{statusLabel}</td>
                            </tr>
                            <tr>
                                <th scope="row">Release date</th>
                                <td>{formatDate(episode.publishedDate)}</td>
                            </tr>
                            <tr>
                                <th scope="row">Download date</th>
                                <td>{formatDate(episode.downloadedDate)}</td>
                            </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                {isDownloadable && (
                    <div className="episode-downloads" aria-labelledby="episode-downloads-title">
                        <h2 id="episode-downloads-title">Downloads</h2>
                        {!showProfiles?.length && (
                            <p>
                                No Local Media Profiles configured yet.{' '}
                                <Link to="/add-local-media-profile">Add one</Link> to download this episode.
                            </p>
                        )}
                        {!!showProfiles?.length && (
                            <div role="list" aria-label="Available downloads per Local Media Profile">
                                {showProfiles.map((profile) => (
                                    <ProfileDownloadRow
                                        key={profile.id}
                                        profile={profile}
                                        download={downloadByProfileId.get(profile.id)}
                                        episodeSlug={episode.slug}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </article>

            <style>{`
        .episode-header { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
        .episode-title-text { font-size: 1.1rem; font-weight: 600; }
        .episode-content { display: grid; grid-template-columns: minmax(280px, 480px) 1fr; gap: 16px; align-items: start; }
        .episode-cover { position: relative; }
        .episode-cover img { display: block; width: 100%; height: auto; border-radius: 8px; border: 1px solid var(--border-color, #ddd); }
        .episode-live-badge { position: absolute; top: 14px; right: 14px; display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 999px; background: var(--error, #d64545); color: #fff; box-shadow: 0 2px 8px rgb(0 0 0 / 30%); font-size: 1rem; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase; }
        .episode-live-badge::before { content: ''; width: 9px; height: 9px; border-radius: 50%; background: currentColor; }
        .meta-table { width: 100%; border-collapse: collapse; }
        .meta-table th, .meta-table td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border-color, #e2e2e2); vertical-align: top; }
        .meta-table th { width: 180px; color: var(--muted-fg, #555); font-weight: 500; }
        .episode-downloads { margin-top: 24px; }
        .episode-downloads h2 { font-size: 1.05rem; margin-bottom: 8px; }
        .download-row { display: flex; align-items: center; gap: 16px; padding: 10px 0; border-bottom: 1px solid var(--divider, #e2e2e2); }
        .download-row-info { min-width: 200px; }
        .download-row-name { font-weight: 600; }
        .download-row-format { color: var(--muted, #777); font-size: 0.9rem; }
        .download-row-state { flex: 1; min-width: 0; }
        .download-row-progress { display: flex; align-items: center; gap: 10px; }
        .download-row-progress .progress { flex: 1; max-width: 380px; }
        .download-row-progress-label { min-width: 60px; color: var(--muted, #777); }
        .download-row-path { color: var(--muted, #777); font-size: 0.85rem; margin-top: 4px; }
        .download-row-error { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
        .download-state-ok { color: #2fa84f; }
        .download-state-error { color: var(--error, #d64545); }
        @media (max-width: 720px) {
          .episode-content { grid-template-columns: 1fr; }
          .download-row { flex-direction: column; align-items: flex-start; gap: 8px; }
        }
      `}</style>
        </section>
    )
}
