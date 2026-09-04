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
import ActionMenu from '../../components/ActionMenu/ActionMenu'
import {useActiveOperation} from '../../components/OperationNotifier/OperationNotifier'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)

function formatDate(value: Date | string | null | undefined) {
    if (!value) return '—'
    const d = value instanceof Date ? value : new Date(value)
    try {
        return new Intl.DateTimeFormat(undefined, {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        }).format(d)
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
    const qc = useQueryClient()
    const [metadataRefreshStarting, setMetadataRefreshStarting] = useState(false)

    const {data: show, isLoading, error} = useShow(showId)
    const {data: episode, isLoading: isLoadingEpisode} = useEpisode(episodeId)
    const {data: profiles} = useLocalMediaProfiles()
    const {data: downloads} = useEpisodeDownloads(episodeId)
    const showProfiles = profiles?.filter((profile) => profile.type === 'show')
    const metadataRefreshOperation = useActiveOperation(
        'episode.refresh_metadata',
        'episode',
        episode?.id ?? null,
    )
    const metadataRefreshBusy = metadataRefreshStarting || metadataRefreshOperation !== undefined

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

    const coverUrl: string = episode.thumbnailLandscapePath
        || episode.backgroundImagePath
        || episode.thumbnailPortraitPath
        || `https://placehold.co/960x540/png?text=Episode+%23${episode.index}`

    const downloadByProfileId = new Map<number, MediaDownloadViewRead>(
        (downloads ?? []).map((d) => [d.localMediaProfileId, d]),
    )

    const refreshMetadata = async () => {
        if (metadataRefreshBusy) return

        setMetadataRefreshStarting(true)
        try {
            const base = (window as any).appConfig?.API_URL || '/api'
            const response = await fetch(
                `${base}/episodes/${encodeURIComponent(episode.slug)}/refresh-metadata`,
                {method: 'POST', credentials: 'include'},
            )
            if (!response.ok) {
                const {error: message} = await getErrorMessageFromResponse(response)
                toast.error(message || 'Could not start metadata refresh')
                return
            }

            const result = await response.json()
            if (typeof result?.operationId !== 'string' || !result.operationId) {
                throw new Error('Metadata refresh request did not return an operation ID')
            }

            await qc.invalidateQueries({queryKey: ['operations']})
            toast.success('Metadata refresh started')
        } catch {
            toast.error('Could not start metadata refresh')
        } finally {
            setMetadataRefreshStarting(false)
        }
    }

    return (
        <section className="view episode-view" aria-labelledby="episode-title">
            <article className="episode-details" aria-label="Episode details">
                <nav className="episode-breadcrumb" aria-label="Breadcrumb">
                    <Link to="/library">Library</Link>
                    <FontAwesomeIcon icon={['fas', 'chevron-right']} aria-hidden="true"/>
                    <Link to={`/show/${showId}`}>{show.title}</Link>
                </nav>

                <div className="episode-cover">
                    <img src={coverUrl} alt="Episode cover"/>
                    {isLive && (
                        <span className="episode-live-badge" aria-label="Episode is live">Live</span>
                    )}
                </div>

                <header className="episode-header">
                    <div className="episode-title-row">
                        <h1 id="episode-title" className="episode-title-text">{episode.title}</h1>
                        <ActionMenu
                            items={[
                                {
                                    label: 'Refresh metadata',
                                    icon: ['fas', 'arrows-rotate'],
                                    disabled: metadataRefreshBusy,
                                    disabledReason: metadataRefreshStarting
                                        ? 'WireLoft is starting a metadata refresh for this episode.'
                                        : metadataRefreshOperation
                                            ? 'A metadata refresh is already running for this episode.'
                                            : undefined,
                                    progress: metadataRefreshOperation
                                        ? (metadataRefreshOperation.progress ?? 0)
                                        : undefined,
                                    onSelect: () => void refreshMetadata(),
                                },
                            ]}
                        />
                    </div>
                    <div className="episode-summary" aria-label="Episode metadata">
                        <span className={`episode-status${isLive ? ' is-live' : ''}`}>
                            {isLive && <span className="episode-status-dot" aria-hidden="true"/>}
                            {statusLabel}
                        </span>
                        <span className="episode-summary-separator" aria-hidden="true"/>
                        <span className="episode-summary-item">
                            <FontAwesomeIcon icon={['fas', 'calendar']} aria-hidden="true"/>
                            <span>Released {formatDate(episode.publishedDate)}</span>
                        </span>
                        {episode.downloadedDate && (
                            <>
                                <span className="episode-summary-separator" aria-hidden="true"/>
                                <span className="episode-summary-item">
                                    <FontAwesomeIcon icon={['fas', 'circle-down']} aria-hidden="true"/>
                                    <span>Downloaded {formatDate(episode.downloadedDate)}</span>
                                </span>
                            </>
                        )}
                    </div>
                </header>

                {!!episode.description?.trim() && (
                    <section className="episode-description" aria-labelledby="episode-description-title">
                        <h2 id="episode-description-title">Episode Description</h2>
                        <p>{episode.description}</p>
                    </section>
                )}

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
        .episode-view { padding-top: 0; }
        .episode-details { width: min(100%, 980px); margin: 0 auto; }
        .episode-breadcrumb { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; color: var(--muted, #777); font-size: 0.9rem; }
        .episode-breadcrumb a { color: inherit; text-decoration: none; }
        .episode-breadcrumb a:hover { color: var(--link-color, #66267a); text-decoration: underline; }
        .episode-breadcrumb svg { width: 9px; opacity: 0.6; }
        .episode-cover { position: relative; overflow: hidden; border-radius: 10px; background: #111827; }
        .episode-cover img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; }
        .episode-live-badge { position: absolute; top: 18px; right: 18px; display: inline-flex; align-items: center; gap: 8px; padding: 9px 15px; border-radius: 999px; background: var(--error, #d64545); color: #fff; box-shadow: 0 2px 10px rgb(0 0 0 / 30%); font-size: 0.95rem; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase; }
        .episode-live-badge::before { content: ''; width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .episode-header { margin-top: 20px; }
        .episode-title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
        .episode-title-row .action-menu { flex: 0 0 auto; }
        .episode-title-text { min-width: 0; margin: 0; font-size: clamp(1.5rem, 3vw, 2.15rem); line-height: 1.18; letter-spacing: -0.025em; }
        .episode-summary { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 14px; color: var(--muted, #6b7280); font-size: 0.9rem; }
        .episode-status, .episode-summary-item { display: inline-flex; align-items: center; gap: 7px; }
        .episode-status.is-live { color: var(--error, #d64545); font-weight: 600; text-transform: uppercase; }
        .episode-status-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .episode-summary-separator { width: 1px; height: 18px; background: var(--border-color, #d9d9d9); }
        .episode-description { margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--border-color, #e2e2e2); }
        .episode-description h2 { margin: 0 0 8px; font-size: 1.05rem; }
        .episode-description p { margin: 0; max-width: 850px; line-height: 1.55; white-space: pre-line; }
        .episode-downloads { margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--border-color, #e2e2e2); }
        .episode-downloads h2 { font-size: 1.05rem; margin: 0 0 8px; }
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
          .episode-details { width: 100%; }
          .episode-breadcrumb { margin-bottom: 12px; font-size: 0.82rem; }
          .episode-cover { border-radius: 8px; }
          .episode-live-badge { top: 10px; right: 10px; padding: 7px 11px; font-size: 0.8rem; }
          .episode-header { margin-top: 14px; }
          .episode-title-row { gap: 10px; }
          .episode-title-text { font-size: 1.4rem; }
          .episode-summary { gap: 9px; margin-top: 10px; font-size: 0.8rem; }
          .episode-summary-separator { height: 16px; }
          .episode-description { margin-top: 18px; padding-top: 16px; }
          .episode-description p { font-size: 0.95rem; }
          .episode-downloads { margin-top: 18px; padding-top: 16px; }
          .download-row { flex-direction: column; align-items: flex-start; gap: 8px; }
        }
      `}</style>
        </section>
    )
}
