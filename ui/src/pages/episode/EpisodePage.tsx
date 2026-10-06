import {useState} from 'react'
import {Link, useParams} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useShow, useEpisode, useEpisodeDownloads, useLocalMediaProfiles} from '../../lib/queries'
import {useSettings} from '../../lib/settings'
import {OperationStartError, useStartOperation} from '../../lib/operations'
import {isShowLocalMediaProfileAvailableFor, PreferredFormatReg} from '../../types/local_media_profile'
import {EpisodePublishStatus, PUBLISH_STATUS_LABELS} from '../../types/episode'
import {MediaDownloadViewRead} from '../../types/schemas/media_download'
import {LocalMediaProfileRead} from '../../types/schemas/local_media_profile'
import {getErrorMessageFromResponse} from '../../utils/helpers'
import DownloadProgressStatus from '../../components/DownloadProgress/DownloadProgressStatus'
import DownloadLogDialog from '../../components/MediaDownload/DownloadLogDialog'
import ProgressExplanation from '../../components/common/ProgressExplanation'
import ActionMenu from '../../components/ActionMenu/ActionMenu'
import ConfirmDialog from '../../components/ConfirmDialog/ConfirmDialog'
import {useActiveOperation} from '../../components/OperationNotifier/OperationNotifier'
import {formatDate, formatDurationMinutes} from "../../utils/formatting";
import './EpisodePage.css'
import {faIcon} from '../../icons/faIcon'


const OPERATION_STARTING_MESSAGE = 'This task is starting...'

function EpisodePageSkeleton() {
    return (
        <section
            className="view episode-view episode-page-skeleton"
            aria-label="Loading episode"
            aria-busy="true"
        >
            <article className="episode-details" aria-hidden="true">
                <div className="episode-page-skeleton-block episode-page-skeleton-breadcrumb"/>
                <div className="episode-page-skeleton-block episode-page-skeleton-cover"/>
                <div className="episode-page-skeleton-header">
                    <div className="episode-page-skeleton-block episode-page-skeleton-title"/>
                    <div className="episode-page-skeleton-meta">
                        <div className="episode-page-skeleton-block episode-page-skeleton-meta-item"/>
                        <div className="episode-page-skeleton-block episode-page-skeleton-meta-item episode-page-skeleton-meta-item-wide"/>
                    </div>
                </div>
                <div className="episode-page-skeleton-description">
                    <div className="episode-page-skeleton-block episode-page-skeleton-section-title"/>
                    <div className="episode-page-skeleton-block episode-page-skeleton-line"/>
                    <div className="episode-page-skeleton-block episode-page-skeleton-line episode-page-skeleton-line-medium"/>
                    <div className="episode-page-skeleton-block episode-page-skeleton-line episode-page-skeleton-line-short"/>
                </div>
            </article>

        </section>
    )
}

function ProfileDownloadRow({
                                profile,
                                download,
                                episodeSlug,
                                confirmCountdownDownload,
                            }: {
    profile: LocalMediaProfileRead
    download?: MediaDownloadViewRead
    episodeSlug: string
    confirmCountdownDownload: boolean
}) {
    const qc = useQueryClient()
    const [busy, setBusy] = useState(false)
    const [showLog, setShowLog] = useState(false)
    const [countdownConfirm, setCountdownConfirm] = useState(false)
    const [redownloadWhenFinal, setRedownloadWhenFinal] = useState(true)

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

    const startDownload = (redownloadFinal = false) =>
        request(
            `${(window as any).appConfig.API_URL}/episodes/${encodeURIComponent(episodeSlug)}/downloads`,
            {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({localMediaProfileId: profile.id, redownloadWhenFinal: redownloadFinal}),
            },
            'Could not start the download',
        )

    const requestDownload = () => {
        if (confirmCountdownDownload) {
            setRedownloadWhenFinal(true)
            setCountdownConfirm(true)
            return
        }
        void startDownload()
    }

    const retryDownload = () =>
        request(
            `${(window as any).appConfig.API_URL}/media-downloads/${download!.id}/retry`,
            {method: 'POST'},
            'Could not retry the download',
        )

    const cancelDownload = () =>
        request(
            `${(window as any).appConfig.API_URL}/media-downloads/${download!.id}/cancel`,
            {method: 'POST'},
            'Could not cancel the download',
        )

    const showDownloadButton = !download
        || (!download.presentation.active && download.presentation.status === 'not_downloaded')

    return (
        <div className="download-row" role="listitem" aria-label={`Download for ${profile.name}`}>
            <div className="download-row-info">
                <div className="download-row-name">{profile.name}</div>
                <div className="download-row-format">{PreferredFormatReg.getLabelLoose(profile.preferredFormat)}</div>
            </div>
            <div className="download-row-state">
                {download && !showDownloadButton
                    ? <DownloadProgressStatus download={download} details={false}/>
                    : <button
                        type="button"
                        className="btn btn-primary"
                        onClick={requestDownload}
                        disabled={busy}
                        aria-label={`Download ${profile.name}`}
                    >
                        <FontAwesomeIcon icon={faIcon('fas', 'download')}/>
                        Download
                    </button>}
            </div>
            {download && (
                <div className="download-row-actions" aria-label={`Actions for ${profile.name}`}>
                    <ProgressExplanation
                        detail={download.presentation.detail + (download.presentation.secondary
                            ? ` ${download.presentation.secondary}.`
                            : '')}
                    />
                    {download.presentation.active && download.presentation.canCancel && (
                        <button
                            type="button"
                            className="icon-btn"
                            onClick={cancelDownload}
                            disabled={busy}
                            title="Cancel download"
                            aria-label={`Cancel download for ${profile.name}`}
                        >
                            <FontAwesomeIcon icon={faIcon('fas', 'ban')}/>
                        </button>
                    )}
                    {!download.presentation.active && download.presentation.canRetry && (
                        <button
                            type="button"
                            className="icon-btn"
                            onClick={retryDownload}
                            disabled={busy}
                            title={download.presentation.outcome === 'success' ? 'Re-download' : 'Retry download'}
                            aria-label={download.presentation.outcome === 'success'
                                ? `Re-download ${profile.name}`
                                : `Retry download for ${profile.name}`}
                        >
                            <FontAwesomeIcon icon={faIcon('fas', 'rotate-right')}/>
                        </button>
                    )}
                    <button
                        type="button"
                        className="icon-btn"
                        onClick={() => setShowLog(true)}
                        title="View log"
                        aria-label={`View log for ${profile.name}`}
                    >
                        <FontAwesomeIcon icon={faIcon('fas', 'file-lines')}/>
                    </button>
                </div>
            )}
            <ConfirmDialog
                open={countdownConfirm}
                title="Download episode with countdown?"
                onDismiss={() => {
                    if (!busy) setCountdownConfirm(false)
                }}
                icon={faIcon('fas', 'circle-exclamation')}
                dismissOnOverlayClick={!busy}
                cancelButton={{disabled: busy}}
                confirmButton={{
                    label: busy ? 'Starting…' : 'Yes, download',
                    onClick: async () => {
                        await startDownload(redownloadWhenFinal)
                        setCountdownConfirm(false)
                    },
                    icon: faIcon('fas', 'download'),
                    disabled: busy,
                }}
            >
                <p>
                    This episode is published, but its current media still contains The Daily Wire countdown.
                </p>
                <p>
                    If you continue, WireLoft will download the current media as-is, including that countdown.
                </p>
                <label className="confirm-dialog-option">
                    <input
                        type="checkbox"
                        checked={redownloadWhenFinal}
                        onChange={(event) => setRedownloadWhenFinal(event.target.checked)}
                        disabled={busy}
                    />
                    <span>Re-download automatically when the countdown is gone</span>
                </label>
            </ConfirmDialog>
            <DownloadLogDialog row={showLog ? (download ?? null) : null} onClose={() => setShowLog(false)}/>
        </div>
    )
}

export default function EpisodePage() {
    const {id: showId, episodeId} = useParams()
    const qc = useQueryClient()
    const startOperation = useStartOperation()
    const [metadataRefreshStarting, setMetadataRefreshStarting] = useState(false)
    const [earlyDeleteConfirm, setEarlyDeleteConfirm] = useState(false)
    const [earlyDeleteStarting, setEarlyDeleteStarting] = useState(false)

    const {data: show, isPending: isShowPending, isFetching: isShowFetching, error} = useShow(showId)
    const {
        data: episode,
        isPending: isEpisodePending,
        isFetching: isEpisodeFetching,
    } = useEpisode(episodeId)
    const {data: profiles} = useLocalMediaProfiles()
    const {data: downloads} = useEpisodeDownloads(episodeId)
    const settingsQuery = useSettings()
    const showProfiles = profiles?.filter((profile) => isShowLocalMediaProfileAvailableFor(profile, show?.type))
    const metadataRefreshOperation = useActiveOperation(
        'episode.refresh_metadata',
        'episode',
        episode?.id ?? null,
    )
    const earlyDeleteOperation = useActiveOperation(
        'episode.early_delete',
        'episode',
        episode?.id ?? null,
    )
    const metadataRefreshBusy = metadataRefreshStarting || metadataRefreshOperation !== undefined
    const earlyDeleteBusy = earlyDeleteStarting || earlyDeleteOperation !== undefined

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

    if (!show && (isShowPending || isShowFetching)) return <EpisodePageSkeleton/>

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

    if (!episode && (isEpisodePending || isEpisodeFetching)) return <EpisodePageSkeleton/>

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
    const earlyDeleteAvailable = episode.earlyDeleteAvailable
    const containsCountdown = (
        publishStatus === 'published_with_countdown'
        || publishStatus === EpisodePublishStatus.publishedWithCountdown
    )
    const isDownloadable = (
        containsCountdown
        || publishStatus === 'published_final'
        || publishStatus === EpisodePublishStatus.publishedFinal
    )
    const earlyDeleteAfterMinutes = settingsQuery.data?.values.episodeStatusTiming.noUsableMediaDeleteAfterMinutes
    const earlyDeleteDisabledReason = earlyDeleteStarting
        ? OPERATION_STARTING_MESSAGE
        : earlyDeleteOperation
            ? 'An early delete is running for this episode.'
            : settingsQuery.error
                ? 'WireLoft could not load the automatic deletion delay.'
                : earlyDeleteAfterMinutes === undefined
                    ? 'WireLoft is loading the automatic deletion delay.'
                    : undefined

    const coverUrl: string = episode.thumbnailLandscapePath
        || episode.backgroundImagePath
        || episode.thumbnailPortraitPath
        || `https://placehold.co/960x540/png?text=Episode+%23${episode.index}`

    const downloadByProfileId = new Map<number, MediaDownloadViewRead>(
        (downloads ?? []).map((d) => [d.localMediaProfileId, d]),
    )
    const latestDownloadedAt = (downloads ?? []).reduce<Date | null>((latest, download) => {
        if (download.artifactStatus !== 'available' || !download.downloadedAt) return latest
        return latest === null || download.downloadedAt.getTime() > latest.getTime()
            ? download.downloadedAt
            : latest
    }, null)

    const refreshMetadata = async () => {
        if (metadataRefreshBusy) return

        setMetadataRefreshStarting(true)
        try {
            const base = (window as any).appConfig?.API_URL || '/api'
            await startOperation(
                `${base}/episodes/${encodeURIComponent(episode.slug)}/refresh-metadata`,
                {method: 'POST'},
            )
            toast.success('Metadata refresh started')
        } catch (error) {
            const detail = error instanceof OperationStartError ? error.message : undefined
            toast.error(detail || 'Could not start metadata refresh')
        } finally {
            setMetadataRefreshStarting(false)
        }
    }

    const earlyDelete = async () => {
        if (earlyDeleteBusy) return

        setEarlyDeleteStarting(true)
        try {
            const base = (window as any).appConfig?.API_URL || '/api'
            await startOperation(
                `${base}/episodes/${encodeURIComponent(episode.slug)}/early-delete`,
                {method: 'POST'},
            )

            setEarlyDeleteConfirm(false)
            await qc.invalidateQueries({queryKey: ['episode', episode.slug]})
            toast.success('Early delete started')
        } catch (error) {
            const detail = error instanceof OperationStartError ? error.message : undefined
            toast.error(detail || 'Could not start early delete')
        } finally {
            setEarlyDeleteStarting(false)
        }
    }

    return (
        <section className="view episode-view" aria-labelledby="episode-title">
            <article className="episode-details" aria-label="Episode details">
                <nav className="episode-breadcrumb" aria-label="Breadcrumb">
                    <Link to="/library">Library</Link>
                    <FontAwesomeIcon icon={faIcon('fas', 'chevron-right')} aria-hidden="true"/>
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
                                    icon: faIcon('fas', 'arrows-rotate'),
                                    disabled: metadataRefreshBusy,
                                    disabledReason: metadataRefreshStarting
                                        ? OPERATION_STARTING_MESSAGE
                                        : metadataRefreshOperation
                                            ? 'A metadata refresh is running for this episode.'
                                            : undefined,
                                    operation: metadataRefreshOperation,
                                    onSelect: () => void refreshMetadata(),
                                },
                                ...(earlyDeleteAvailable ? [{
                                    label: 'Early Delete',
                                    icon: faIcon('fas', 'trash') as [string, string],
                                    tone: 'danger' as const,
                                    separatorBefore: true,
                                    disabled: earlyDeleteDisabledReason !== undefined,
                                    disabledReason: earlyDeleteDisabledReason,
                                    operation: earlyDeleteOperation,
                                    onSelect: () => setEarlyDeleteConfirm(true),
                                }] : []),
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
                            <FontAwesomeIcon icon={faIcon('fas', 'calendar')} aria-hidden="true"/>
                            <span>Released {formatDate(episode.publishedDate)}</span>
                        </span>
                        {latestDownloadedAt && (
                            <>
                                <span className="episode-summary-separator" aria-hidden="true"/>
                                <span className="episode-summary-item">
                                    <FontAwesomeIcon icon={faIcon('fas', 'circle-down')} aria-hidden="true"/>
                                    <span>Downloaded {formatDate(latestDownloadedAt)}</span>
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
                                        confirmCountdownDownload={containsCountdown}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </article>

            {earlyDeleteAvailable && earlyDeleteAfterMinutes !== undefined && (
                <ConfirmDialog
                    open={earlyDeleteConfirm}
                    title="Early Delete"
                    onDismiss={() => {
                        if (!earlyDeleteBusy) setEarlyDeleteConfirm(false)
                    }}
                    icon={faIcon('fas', 'trash')}
                    iconTone="danger"
                    dismissOnOverlayClick={!earlyDeleteBusy}
                    cancelButton={{disabled: earlyDeleteBusy}}
                    confirmButton={{
                        label: earlyDeleteBusy ? 'Deleting…' : 'Delete now',
                        onClick: earlyDelete,
                        className: 'btn btn-danger',
                        disabled: earlyDeleteBusy,
                    }}>
                    <p>
                        Daily Wire currently returns 404 for this episode, so WireLoft cannot recover media from its current slug.
                    </p>
                    <p>
                        WireLoft will normally keep checking it and only delete it automatically after
                        {' '}<strong>{formatDurationMinutes(earlyDeleteAfterMinutes)}</strong> in the continuous <code>no_usable_media</code> state.
                    </p>
                    <p>
                        Deleting early skips that waiting period. However, if it turns out this episode slug returned to The Daily Wire, WireLoft
                        will refuse to delete it.
                    </p>
                </ConfirmDialog>
            )}

        </section>
    )
}
