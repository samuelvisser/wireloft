import {useEffect, useMemo, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Link, useNavigate, useParams} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'

import ProgressBar from '../../components/common/ProgressBar'
import {toImageUrl} from '../../components/Episode/EpisodeCard'
import {useDailywireMovie, useLocalMediaProfiles, useMovieDownloads, useMovies} from '../../lib/queries'
import {getErrorMessageFromResponse} from '../../utils/helpers'

function formatDuration(seconds: number) {
    if (!seconds) return null
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.round((seconds % 3600) / 60)
    return hours ? `${hours}h ${minutes}m` : `${minutes}m`
}

export default function MoviePage() {
    const {slug} = useParams()
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const {data: movie, error} = useDailywireMovie(slug)
    const {data: localMovies} = useMovies()
    const {data: profiles} = useLocalMediaProfiles()
    const {data: downloads} = useMovieDownloads(slug)
    const localMovie = useMemo(
        () => localMovies?.find((item) => item.slug === slug),
        [localMovies, slug],
    )
    const videoProfiles = useMemo(
        () => profiles?.filter((profile) => profile.type === 'movie') || [],
        [profiles],
    )
    const [profileId, setProfileId] = useState('')
    const [submitting, setSubmitting] = useState<'movie' | 'trailer' | null>(null)
    const [confirmDelete, setConfirmDelete] = useState(false)
    const [deleting, setDeleting] = useState(false)
    const [retryingMetadata, setRetryingMetadata] = useState(false)

    useEffect(() => {
        if (!profileId && videoProfiles[0]) setProfileId(String(videoProfiles[0].id))
    }, [profileId, videoProfiles])

    const startDownload = async (mediaType: 'movie' | 'trailer') => {
        if (!slug || !profileId) return
        if (mediaType === 'trailer' && !movie?.trailer?.slug) return
        setSubmitting(mediaType)
        try {
            const path = mediaType === 'trailer'
                ? `/movies/${encodeURIComponent(slug)}/trailers/${encodeURIComponent(movie!.trailer!.slug)}/downloads`
                : `/movies/${encodeURIComponent(slug)}/downloads`
            const response = await fetch(`${(window as any).appConfig.API_URL}${path}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({localMediaProfileId: Number(profileId)}),
            })
            if (!response.ok) {
                const {error: message} = await getErrorMessageFromResponse(response)
                await queryClient.invalidateQueries({queryKey: ['movies']})
                toast.error(message || `Could not start the ${mediaType} download`)
                return
            }
            toast.success(`${mediaType === 'movie' ? 'Movie' : 'Trailer'} download queued`)
            await Promise.all([
                queryClient.invalidateQueries({queryKey: ['movies']}),
                queryClient.invalidateQueries({queryKey: ['movieDownloads', slug]}),
                queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
            ])
        } catch {
            toast.error(`Could not start the ${mediaType} download`)
        } finally {
            setSubmitting(null)
        }
    }

    const retryReleaseMetadata = async () => {
        if (!slug || !localMovie || retryingMetadata) return
        setRetryingMetadata(true)
        try {
            const response = await fetch(
                `${(window as any).appConfig.API_URL}/movies/${encodeURIComponent(slug)}/release-metadata/retry`,
                {method: 'POST', credentials: 'include'},
            )
            if (!response.ok) {
                const {error: message} = await getErrorMessageFromResponse(response)
                toast.error(message || 'Could not retry the TMDB lookup')
                return
            }

            const result = await response.json()
            await queryClient.invalidateQueries({queryKey: ['movies']})
            if (result.releaseDateLookupStatus === 'matched') {
                toast.success('Movie release date found')
            } else if (result.releaseDateLookupStatus === 'error') {
                toast.error(result.releaseDateLookupError || 'TMDB lookup failed again')
            } else if (result.releaseDateLookupStatus === 'ambiguous') {
                toast.error('TMDB found multiple possible matches and could not choose one safely')
            } else {
                toast.error('TMDB could not find a confident match for this movie')
            }
        } catch {
            toast.error('Could not retry the TMDB lookup')
        } finally {
            setRetryingMetadata(false)
        }
    }

    const deleteMovie = async () => {
        if (!slug || !localMovie || deleting) return
        setDeleting(true)
        try {
            const response = await fetch(
                `${(window as any).appConfig.API_URL}/movies/${encodeURIComponent(slug)}`,
                {method: 'DELETE', credentials: 'include'},
            )
            if (!response.ok) {
                const {error: message} = await getErrorMessageFromResponse(response)
                toast.error(message || 'Could not delete the movie')
                return
            }
            setConfirmDelete(false)
            await Promise.all([
                queryClient.invalidateQueries({queryKey: ['movies']}),
                queryClient.invalidateQueries({queryKey: ['movieDownloads', slug]}),
                queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
            ])
            navigate('/library?type=movies')
        } catch {
            toast.error('Could not delete the movie')
        } finally {
            setDeleting(false)
        }
    }

    if (!movie && !error) return <section className="view"><p>Loading movie…</p></section>
    if (error || !movie) return <section className="view"><div className="form-error-card" role="alert">Could not load this movie: {error?.message || 'Movie not found'}</div></section>

    const hero = toImageUrl(movie.backgroundImagePath || movie.thumbnailLandscapePath || movie.thumbnailPortraitPath)
    const duration = formatDuration(movie.duration)

    return (
        <section className="view movie-detail-view" aria-labelledby="movie-title">
            <div className="movie-hero" style={hero ? {backgroundImage: `linear-gradient(0deg, var(--bg) 0%, rgba(9,18,33,.15) 72%), url(${hero})`} : undefined}>
                <div>
                    <span className="movie-kicker"><FontAwesomeIcon icon={['fas', 'clapperboard']}/> Movie</span>
                    <h1 id="movie-title">{movie.title}</h1>
                    <p>{[movie.authorName, duration, movie.matureRating].filter(Boolean).join(' • ')}</p>
                </div>
            </div>

            <div className="movie-detail-actions">
                {movie.trailer?.sharingUrl && (
                    <a className="btn btn-secondary" href={movie.trailer.sharingUrl} target="_blank" rel="noreferrer">
                        <FontAwesomeIcon icon={['fas', 'play']}/> Watch trailer
                    </a>
                )}
                {movie.sharingUrl && (
                    <a className="btn" href={movie.sharingUrl} target="_blank" rel="noreferrer">
                        <FontAwesomeIcon icon={['fas', 'arrow-up-right-from-square']}/> Open on Daily Wire
                    </a>
                )}
                {localMovie?.releaseDateLookupStatus === 'error' && (
                    <button type="button" className="btn" onClick={() => void retryReleaseMetadata()} disabled={retryingMetadata}>
                        <FontAwesomeIcon icon={['fas', 'rotate']}/>
                        {retryingMetadata ? 'Retrying TMDB…' : 'Retry TMDB lookup'}
                    </button>
                )}
                {localMovie && (
                    <button type="button" className="btn btn-danger" onClick={() => setConfirmDelete(true)}>
                        <FontAwesomeIcon icon={['fas', 'trash']}/> Delete
                    </button>
                )}
            </div>

            <div className="movie-detail-layout">
                <div className="movie-description">
                    <h2>About this movie</h2>
                    <p>{movie.description || 'Daily Wire did not provide a description for this movie.'}</p>
                    {movie.trailer && (
                        <div className="movie-trailer-row">
                            {movie.trailer.thumbnailLandscapePath ? <img src={toImageUrl(movie.trailer.thumbnailLandscapePath)} alt=""/> : null}
                            <span><strong>{movie.trailer.title}</strong><small>{formatDuration(movie.trailer.duration)}</small></span>
                            <a href={movie.trailer.sharingUrl} target="_blank" rel="noreferrer" aria-label={`Watch ${movie.trailer.title}`}><FontAwesomeIcon icon={['fas', 'circle-play']}/></a>
                        </div>
                    )}
                </div>

                <aside className="movie-download-panel" aria-labelledby="download-movie-title">
                    <h2 id="download-movie-title">Download movie media</h2>
                    <p>Movies and trailers are downloaded manually using the same Movie Local Media Profile.</p>
                    {videoProfiles.length ? (
                        <>
                            <label htmlFor="movie-profile">Local Media Profile</label>
                            <select id="movie-profile" className="input" value={profileId} onChange={(event) => setProfileId(event.target.value)}>
                                {videoProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
                            </select>
                            <button className="btn btn-primary movie-download-button" type="button" onClick={() => startDownload('movie')} disabled={submitting !== null || !movie.isDownloadable}>
                                <FontAwesomeIcon icon={['fas', 'download']}/>
                                {submitting === 'movie' ? 'Queuing…' : 'Download movie'}
                            </button>
                            {movie.trailer && (
                                <button className="btn movie-download-button" type="button" onClick={() => startDownload('trailer')} disabled={submitting !== null}>
                                    <FontAwesomeIcon icon={['fas', 'download']}/>
                                    {submitting === 'trailer' ? 'Queuing…' : 'Download trailer'}
                                </button>
                            )}
                        </>
                    ) : (
                        <div className="movie-profile-empty">
                            <p>Create a Movie Local Media Profile before downloading a movie or trailer.</p>
                            <Link className="btn" to="/add-local-media-profile?type=movie">Create profile</Link>
                        </div>
                    )}
                </aside>
            </div>

            {!!downloads?.length && (
                <section className="movie-downloads" aria-labelledby="movie-downloads-title">
                    <h2 id="movie-downloads-title">Downloads</h2>
                    {downloads.map((download) => (
                        <div className="movie-download-row" key={download.id}>
                            <div>
                                <strong>{download.type === 'trailer' ? 'Trailer' : 'Movie'} · {download.localMediaProfileName}</strong>
                                <small>{download.formatDownloaded || download.preferredFormat || 'Waiting for format'}</small>
                            </div>
                            {(download.downloadStatus === 'downloading' || download.downloadStatus === 'pending') ? (
                                <div className="movie-download-progress"><ProgressBar value={download.progress} ariaLabel={`Download progress for ${movie.title}`}/><span>{download.downloadStatus === 'pending' ? 'Queued' : `${download.progress}%`}</span></div>
                            ) : <span className={`download-status status-${download.downloadStatus}`}>{String(download.downloadStatus).replace(/_/g, ' ')}</span>}
                        </div>
                    ))}
                </section>
            )}

            {confirmDelete && localMovie && (
                <div className="modal-overlay" role="presentation" onClick={() => !deleting && setConfirmDelete(false)}>
                    <div
                        className="modal"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="delete-title"
                        aria-describedby="delete-desc"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="modal-header">
                            <div className="modal-icon danger" aria-hidden>
                                <FontAwesomeIcon icon={['fas', 'trash']}/>
                            </div>
                            <h2 id="delete-title" className="modal-title">Delete movie</h2>
                        </div>
                        <p id="delete-desc" className="modal-text">
                            Are you sure you want to delete "{movie.title}" from WireLoft? This removes the movie and
                            its download history from the WireLoft database. Completed files already on disk will not
                            be changed. Any download still in progress will be cancelled and its partial files removed.
                        </p>
                        <div className="modal-actions">
                            <button type="button" className="btn" onClick={() => setConfirmDelete(false)} disabled={deleting}>Cancel</button>
                            <button type="button" className="btn btn-danger" onClick={() => void deleteMovie()} disabled={deleting}>
                                {deleting ? 'Deleting…' : 'Delete'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </section>
    )
}
