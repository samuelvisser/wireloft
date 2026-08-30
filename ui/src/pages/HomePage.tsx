import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useNavigate} from 'react-router-dom'

import ProgressBar from '../components/common/ProgressBar'
import {useLocalMediaProfiles, useMediaDownloadsView, useMovies, useShows} from '../lib/queries'
import {ACTIVE_DOWNLOAD_STATUSES} from '../types/media_download'
import {MediaDownloadViewRead} from '../types/schemas/media_download'
import {movieExtraTypeLabel} from '../utils/movieExtras'

const PROBLEMS = new Set(['error', 'missing', 'corrupted'])
const COMPLETE = new Set(['downloaded', 'redownloaded'])

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
    const active = downloads?.filter((download) => ACTIVE_DOWNLOAD_STATUSES.has(String(download.downloadStatus))) || []
    const problems = downloads?.filter((download) => PROBLEMS.has(String(download.downloadStatus))) || []
    const metadataProblems = movies?.filter((movie) => movie.releaseDateLookupStatus === 'error') || []
    const complete = downloads?.filter((download) => COMPLETE.has(String(download.downloadStatus))).slice(0, 4) || []
    const hasAttention = problems.length > 0 || metadataProblems.length > 0 || profiles?.length === 0
    const attentionSummary = [
        problems.length ? `${problems.length} download problem${problems.length === 1 ? '' : 's'}` : null,
        metadataProblems.length ? `${metadataProblems.length} movie metadata problem${metadataProblems.length === 1 ? '' : 's'}` : null,
        profiles?.length === 0 ? 'No Local Media Profiles' : null,
    ].filter(Boolean).join(' • ')

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
                    <FontAwesomeIcon icon={['fas', 'plus']}/> Add media
                </button>
            </div>

            <div className={`system-health ${hasAttention ? 'needs-attention' : 'is-healthy'}`}>
                <FontAwesomeIcon icon={['fas', hasAttention ? 'triangle-exclamation' : 'circle-check']}/>
                <div>
                    <strong>{hasAttention ? 'WireLoft needs attention' : 'WireLoft is running normally'}</strong>
                    <small>{hasAttention ? attentionSummary : 'No download, metadata or profile problems detected'}</small>
                </div>
            </div>

            <div className="operation-stats" aria-label="WireLoft status summary">
                <button type="button" onClick={() => navigate('/downloads')}><span>Active</span><strong>{active.filter((item) => item.downloadStatus !== 'pending').length}</strong></button>
                <button type="button" onClick={() => navigate('/downloads')}><span>Queued</span><strong>{active.filter((item) => item.downloadStatus === 'pending').length}</strong></button>
                <button type="button" onClick={() => navigate('/downloads')}><span>Failed</span><strong>{problems.length}</strong></button>
                <button type="button" onClick={() => navigate('/library')}><span>Library</span><strong>{(shows?.length || 0) + (movies?.length || 0)}</strong></button>
            </div>

            {error && <div className="form-error-card" role="alert">Could not load download status: {error.message}</div>}

            <div className="operations-grid">
                <section className="operation-section" aria-labelledby="active-downloads-title">
                    <div className="operation-section-header"><h2 id="active-downloads-title">Downloading now</h2><button type="button" onClick={() => navigate('/downloads')}>All downloads</button></div>
                    {isLoading && !downloads ? <p>Loading downloads…</p> : active.length ? active.slice(0, 3).map((download) => (
                        <button className="operation-download" type="button" key={download.id} onClick={() => openDownload(download)}>
                            <span className="operation-icon"><FontAwesomeIcon icon={['fas', download.movieSlug ? 'clapperboard' : 'podcast']}/></span>
                            <span className="operation-download-copy"><strong>{mediaTitle(download)}</strong><small>{mediaContext(download)} • {download.localMediaProfileName}</small><ProgressBar value={download.progress} ariaLabel={`Progress for ${mediaTitle(download)}`}/></span>
                            <span>{download.downloadStatus === 'pending' ? 'Queued' : download.downloadStatus === 'local_processing' ? 'Processing' : `${download.progress}%`}</span>
                        </button>
                    )) : <div className="operation-empty"><FontAwesomeIcon icon={['fas', 'check']}/><span>No active downloads</span></div>}
                </section>

                <section className="operation-section" aria-labelledby="attention-title">
                    <div className="operation-section-header"><h2 id="attention-title">Needs attention</h2></div>
                    {profiles?.length === 0 && (
                        <button className="operation-alert" type="button" onClick={() => navigate('/add-local-media-profile')}>
                            <FontAwesomeIcon icon={['fas', 'folder-plus']}/><span><strong>No Local Media Profile</strong><small>Create one before downloading episodes or movies.</small></span><span>Fix</span>
                        </button>
                    )}
                    {metadataProblems.slice(0, 3).map((movie) => (
                        <button className="operation-alert" type="button" key={`movie-metadata-${movie.id}`} onClick={() => navigate(`/movie/${movie.slug}`)}>
                            <FontAwesomeIcon icon={['fas', 'triangle-exclamation']}/><span><strong>{movie.title} metadata</strong><small>{movie.releaseDateLookupError || 'TMDB release-date lookup failed. Open the movie to retry.'}</small></span><span>View</span>
                        </button>
                    ))}
                    {problems.slice(0, 3).map((download) => (
                        <button className="operation-alert" type="button" key={download.id} onClick={() => openDownload(download)}>
                            <FontAwesomeIcon icon={['fas', 'triangle-exclamation']}/><span><strong>{mediaTitle(download)}</strong><small>{download.errorMessage || `Download is ${download.downloadStatus}`}</small></span><span>View</span>
                        </button>
                    ))}
                    {!hasAttention && <div className="operation-empty"><FontAwesomeIcon icon={['fas', 'circle-check']}/><span>Nothing needs attention</span></div>}
                </section>
            </div>

            <section className="operation-section recent-activity" aria-labelledby="recent-title">
                <div className="operation-section-header"><h2 id="recent-title">Recently completed</h2><button type="button" onClick={() => navigate('/downloads')}>View history</button></div>
                {complete.length ? complete.map((download) => (
                    <button className="recent-download" type="button" key={download.id} onClick={() => openDownload(download)}>
                        <FontAwesomeIcon icon={['fas', 'circle-check']}/><span><strong>{mediaTitle(download)}</strong><small>{mediaContext(download)} • {download.localMediaProfileName}</small></span><time>{download.finishedAt?.toLocaleString() || ''}</time>
                    </button>
                )) : <div className="operation-empty"><span>No completed downloads yet</span></div>}
            </section>
        </section>
    )
}
