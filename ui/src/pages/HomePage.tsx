import {useMemo} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useNavigate} from 'react-router-dom'
import {faIcon} from '../icons/faIcon'

import DownloadProgressStatus from '../components/DownloadProgress/DownloadProgressStatus'
import {
    useLocalMediaProfiles,
    useMediaDownloadsView,
    useMovies,
    useRecentlyIndexedEpisodes,
    useShows,
} from '../lib/queries'
import {downloadsUrlForStatusFilters} from '../lib/downloadStatusFilters'
import {ACTIVE_DOWNLOAD_STATUSES} from '../types/media_download'
import {EpisodeIndexedActivityRead} from '../types/schemas/episode'
import {MediaDownloadViewRead} from '../types/schemas/media_download'
import {movieExtraTypeLabel} from '../utils/movieExtras'

const PROBLEMS = new Set(['error', 'missing', 'corrupted'])
const COMPLETE = new Set(['downloaded', 'redownloaded'])
const RECENT_ACTIVITY_LIMIT = 9

type RecentActivityItem =
    | {kind: 'download'; occurredAt: Date; download: MediaDownloadViewRead}
    | {kind: 'episode-indexed'; occurredAt: Date; episode: EpisodeIndexedActivityRead}

function mediaTitle(download: MediaDownloadViewRead) {
    return download.mediaTitle || download.movieTitle || download.episodeTitle || 'Unknown media'
}

function mediaContext(download: MediaDownloadViewRead) {
    if (download.type === 'movie_extra') {
        return `${movieExtraTypeLabel(download.movieExtraType)} • ${download.movieTitle || 'Movie'}`
    }
    return download.movieTitle ? 'Movie' : download.showTitle || 'Episode'
}

export default function HomePage() {
    const navigate = useNavigate()
    const {data: shows} = useShows()
    const {data: movies} = useMovies()
    const {data: profiles} = useLocalMediaProfiles()
    const {data: downloads, isLoading, error} = useMediaDownloadsView()
    const {data: indexedEpisodes} = useRecentlyIndexedEpisodes(RECENT_ACTIVITY_LIMIT)
    const active = downloads?.filter((download) => ACTIVE_DOWNLOAD_STATUSES.has(String(download.downloadStatus))) || []
    const problems = downloads?.filter((download) => PROBLEMS.has(String(download.downloadStatus))) || []
    const metadataProblems = movies?.filter((movie) => movie.releaseDateLookupStatus === 'error') || []
    const hasAttention = problems.length > 0 || metadataProblems.length > 0 || profiles?.length === 0
    const activeSectionIsEmpty = !isLoading && downloads !== undefined && active.length === 0
    const attentionSectionIsEmpty = downloads !== undefined
        && movies !== undefined
        && profiles !== undefined
        && !hasAttention
    const attentionSummary = [
        problems.length ? `${problems.length} download problem${problems.length === 1 ? '' : 's'}` : null,
        metadataProblems.length ? `${metadataProblems.length} movie metadata problem${metadataProblems.length === 1 ? '' : 's'}` : null,
        profiles?.length === 0 ? 'No Local Media Profiles' : null,
    ].filter(Boolean).join(' • ')
    const recentActivity = useMemo(() => {
        const activity: RecentActivityItem[] = []

        for (const download of downloads ?? []) {
            if (!COMPLETE.has(String(download.downloadStatus))) continue
            const occurredAt = download.finishedAt ?? download.downloadedAt
            if (!occurredAt) continue
            activity.push({kind: 'download', occurredAt, download})
        }

        for (const episode of indexedEpisodes ?? []) {
            activity.push({
                kind: 'episode-indexed',
                occurredAt: episode.indexedAt,
                episode,
            })
        }

        return activity
            .sort((left, right) => right.occurredAt.getTime() - left.occurredAt.getTime())
            .slice(0, RECENT_ACTIVITY_LIMIT)
    }, [downloads, indexedEpisodes])

    const openDownload = (download: MediaDownloadViewRead) => {
        if (download.movieSlug) navigate(`/movie/${download.movieSlug}`)
        else if (download.showSlug && download.episodeSlug) navigate(`/show/${download.showSlug}/episode/${download.episodeSlug}`)
        else navigate('/downloads')
    }

    return (
        <section className="view operations-home" aria-labelledby="home-title">
            <div className="view-header">
                <div>
                    <h1 id="home-title">Home</h1>
                    <p className="view-description">What WireLoft is doing now and anything that needs your attention.</p>
                </div>
                <button className="btn btn-primary" onClick={() => navigate('/browse')}>
                    <FontAwesomeIcon icon={faIcon('fas', 'plus')}/> Add media
                </button>
            </div>

            <div className={`system-health ${hasAttention ? 'needs-attention' : 'is-healthy'}`}>
                <FontAwesomeIcon icon={faIcon('fas', hasAttention ? 'triangle-exclamation' : 'circle-check')}/>
                <div>
                    <strong>{hasAttention ? 'WireLoft needs attention' : 'WireLoft is running normally'}</strong>
                    <small>{hasAttention ? attentionSummary : 'No download, metadata or profile problems detected'}</small>
                </div>
            </div>

            <div className="operation-stats" aria-label="WireLoft status summary">
                <button type="button" onClick={() => navigate(downloadsUrlForStatusFilters('downloading', 'local_processing'))}><span>Active</span><strong>{active.filter((item) => item.downloadStatus !== 'pending').length}</strong></button>
                <button type="button" onClick={() => navigate(downloadsUrlForStatusFilters('pending'))}><span>Queued</span><strong>{active.filter((item) => item.downloadStatus === 'pending').length}</strong></button>
                <button type="button" onClick={() => navigate(downloadsUrlForStatusFilters('error', 'missing', 'corrupted'))}><span>Failed</span><strong>{problems.length}</strong></button>
                <button type="button" onClick={() => navigate('/library')}><span>Library</span><strong>{(shows?.length || 0) + (movies?.length || 0)}</strong></button>
            </div>

            {error && <div className="form-error-card" role="alert">Could not load download status: {error.message}</div>}

            <div className="operations-grid">
                <section
                    className={`operation-section${activeSectionIsEmpty ? ' mobile-empty-section' : ''}`}
                    aria-labelledby="active-downloads-title"
                >
                    <div className="operation-section-header"><h2 id="active-downloads-title">Downloading now</h2><button type="button" onClick={() => navigate('/downloads')}>All downloads</button></div>
                    {isLoading && !downloads ? <p>Loading downloads…</p> : active.length ? active.slice(0, 3).map((download) => (
                        <button className="operation-download" type="button" key={download.id} onClick={() => openDownload(download)}>
                            <span className="operation-icon"><FontAwesomeIcon icon={faIcon('fas', download.movieSlug ? 'clapperboard' : 'podcast')}/></span>
                            <span className="operation-download-copy"><strong>{mediaTitle(download)}</strong><small>{mediaContext(download)} • {download.localMediaProfileName}</small><DownloadProgressStatus download={download} compact details={false}/></span>
                        </button>
                    )) : <div className="operation-empty"><FontAwesomeIcon icon={faIcon('fas', 'check')}/><span>No active downloads</span></div>}
                </section>

                <section
                    className={`operation-section${attentionSectionIsEmpty ? ' mobile-empty-section' : ''}`}
                    aria-labelledby="attention-title"
                >
                    <div className="operation-section-header"><h2 id="attention-title">Needs attention</h2></div>
                    {profiles?.length === 0 && (
                        <button className="operation-alert" type="button" onClick={() => navigate('/add-local-media-profile')}>
                            <FontAwesomeIcon icon={faIcon('fas', 'folder-plus')}/><span><strong>No Local Media Profile</strong><small>Create one before downloading episodes or movies.</small></span><span>Fix</span>
                        </button>
                    )}
                    {metadataProblems.slice(0, 3).map((movie) => (
                        <button className="operation-alert" type="button" key={`movie-metadata-${movie.id}`} onClick={() => navigate(`/movie/${movie.slug}`)}>
                            <FontAwesomeIcon icon={faIcon('fas', 'triangle-exclamation')}/><span><strong>{movie.title} metadata</strong><small>{movie.releaseDateLookupError || 'TMDB release-date lookup failed. Open the movie to retry.'}</small></span><span>View</span>
                        </button>
                    ))}
                    {problems.slice(0, 3).map((download) => (
                        <button className="operation-alert" type="button" key={download.id} onClick={() => openDownload(download)}>
                            <FontAwesomeIcon icon={faIcon('fas', 'triangle-exclamation')}/><span><strong>{mediaTitle(download)}</strong><small>{download.errorMessage || `Download is ${download.downloadStatus}`}</small></span><span>View</span>
                        </button>
                    ))}
                    {!hasAttention && <div className="operation-empty"><FontAwesomeIcon icon={faIcon('fas', 'circle-check')}/><span>Nothing needs attention</span></div>}
                </section>
            </div>

            <section className="operation-section recent-activity" aria-labelledby="recent-title">
                <div className="operation-section-header"><h2 id="recent-title">Recent activity</h2></div>
                {recentActivity.length ? recentActivity.map((activity) => {
                    if (activity.kind === 'download') {
                        const {download} = activity
                        return (
                            <button className="recent-download" type="button" key={`download-${download.id}`} onClick={() => openDownload(download)}>
                                <FontAwesomeIcon icon={faIcon('fas', 'circle-check')}/><span><strong>{mediaTitle(download)}</strong><small>{mediaContext(download)} • {download.localMediaProfileName}</small></span><time>{activity.occurredAt.toLocaleString()}</time>
                            </button>
                        )
                    }

                    const {episode} = activity
                    return (
                        <button
                            className="recent-download recent-indexed-episode"
                            type="button"
                            key={`episode-indexed-${episode.id}`}
                            onClick={() => navigate(`/show/${episode.showSlug}/episode/${episode.slug}`)}
                        >
                            <FontAwesomeIcon icon={faIcon('fas', 'circle-plus')}/><span><strong>{episode.title}</strong><small>{episode.showTitle} • Indexed</small></span><time>{activity.occurredAt.toLocaleString()}</time>
                        </button>
                    )
                }) : <div className="operation-empty"><span>No recent activity yet</span></div>}
            </section>
        </section>
    )
}
