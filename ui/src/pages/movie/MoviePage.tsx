import {useEffect, useMemo, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Link, useNavigate, useParams} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'

import ProgressBar from '../../components/common/ProgressBar'
import {toImageUrl} from '../../components/Episode/EpisodeCard'
import {useDailywireMovie, useLocalMediaProfiles, useMovieDownloads, useMovies} from '../../lib/queries'
import {MovieExtraType} from '../../types/schemas/dailywire_catalog'
import {getErrorMessageFromResponse} from '../../utils/helpers'
import {movieExtraTypeLabel} from '../../utils/movieExtras'

type MovieExtraSummary = {
    id?: number
    slug: string
    title: string
    movieExtraType: MovieExtraType
    duration: number
    sharingUrl?: string | null
    thumbnailLandscapePath?: string | null
    backgroundImagePath?: string | null
}

function formatDuration(seconds: number) {
    if (!seconds) return null
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.round((seconds % 3600) / 60)
    return hours ? `${hours}h ${minutes}m` : `${minutes}m`
}

function sleep(milliseconds: number) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
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
    const [submitting, setSubmitting] = useState<string | null>(null)
    const [addingMovie, setAddingMovie] = useState(false)
    const [confirmDelete, setConfirmDelete] = useState(false)
    const [deleting, setDeleting] = useState(false)
    const [retryingMetadata, setRetryingMetadata] = useState(false)
    const [refreshingExtras, setRefreshingExtras] = useState(false)

    useEffect(() => {
        if (!profileId && videoProfiles[0]) setProfileId(String(videoProfiles[0].id))
    }, [profileId, videoProfiles])

    const startMovieDownload = async () => {
        if (!slug || !profileId || !movie) return
        await startDownloadRequest({
            key: 'movie',
            path: `/movies/${encodeURIComponent(slug)}/downloads`,
            label: 'Movie',
            successMessage: `Started downloading movie: ${movie.title}`,
        })
    }

    const startExtraDownload = async (extra: MovieExtraSummary) => {
        if (!slug || !profileId) return
        await startDownloadRequest({
            key: `extra:${extra.slug}`,
            path: `/movies/${encodeURIComponent(slug)}/extras/${encodeURIComponent(extra.slug)}/downloads`,
            label: movieExtraTypeLabel(extra.movieExtraType),
            successMessage: `Started downloading movie extra: ${extra.title}`,
        })
    }

    const startDownloadRequest = async ({key, path, label, successMessage}: {key: string; path: string; label: string; successMessage: string}) => {
        if (!movie) return
        const movieWasAlreadyIndexed = Boolean(localMovie)
        setSubmitting(key)
        try {
            const response = await fetch(`${(window as any).appConfig.API_URL}${path}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({localMediaProfileId: Number(profileId)}),
            })
            if (!response.ok) {
                const {error: message} = await getErrorMessageFromResponse(response)
                await queryClient.invalidateQueries({queryKey: ['movies']})
                toast.error(message || `Could not start the ${label.toLocaleLowerCase()} download`)
                return
            }
            if (!movieWasAlreadyIndexed) toast.success(`${movie.title} added to WireLoft`)
            toast.success(successMessage)
            await Promise.all([
                queryClient.invalidateQueries({queryKey: ['movies']}),
                queryClient.invalidateQueries({queryKey: ['movieDownloads', slug]}),
                queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
            ])
        } catch {
            toast.error(`Could not start the ${label.toLocaleLowerCase()} download`)
        } finally {
            setSubmitting(null)
        }
    }

    const addMovie = async () => {
        if (!slug || !movie || addingMovie) return
        setAddingMovie(true)
        try {
            const response = await fetch(
                `${(window as any).appConfig.API_URL}/movies/${encodeURIComponent(slug)}/index`,
                {method: 'POST', credentials: 'include'},
            )
            if (!response.ok) {
                const {error: message} = await getErrorMessageFromResponse(response)
                toast.error(message || `Could not add ${movie.title} to WireLoft`)
                return
            }

            toast.success(`${movie.title} added to WireLoft`)
            await queryClient.invalidateQueries({queryKey: ['movies']})
            navigate(`/movie/${encodeURIComponent(slug)}`, {replace: true})
        } catch {
            toast.error(`Could not add ${movie.title} to WireLoft`)
        } finally {
            setAddingMovie(false)
        }
    }

    const refreshMovieExtras = async () => {
        if (!slug || !localMovie || refreshingExtras) return
        setRefreshingExtras(true)
        const requestedAt = Date.now() - 2_000
        try {
            const base = (window as any).appConfig.API_URL
            const response = await fetch(
                `${base}/movies/${encodeURIComponent(slug)}/extras/refresh`,
                {method: 'POST', credentials: 'include'},
            )
            if (!response.ok) {
                const {error: message} = await getErrorMessageFromResponse(response)
                toast.error(message || 'Could not start the movie-extra refresh')
                return
            }

            toast.success('Movie-extra refresh started')
            for (let attempt = 0; attempt < 60; attempt += 1) {
                await sleep(1_000)
                const params = new URLSearchParams({
                    resource_type: 'movie',
                    resource_id: String(localMovie.id),
                    definition_key: 'refresh_movie_extras',
                })
                const runResponse = await fetch(`${base}/tasks/runs?${params}`, {credentials: 'include'})
                if (!runResponse.ok) continue
                const runs = await runResponse.json()
                const run = Array.isArray(runs)
                    ? runs.find((candidate) => {
                        const startedAt = candidate?.startedAt ? Date.parse(candidate.startedAt) : 0
                        return startedAt >= requestedAt
                    })
                    : null
                if (!run) continue
                if (run.status === 'SUCCEEDED') {
                    await Promise.all([
                        queryClient.invalidateQueries({queryKey: ['movies']}),
                        queryClient.invalidateQueries({queryKey: ['dailywireMovie', slug]}),
                    ])
                    toast.success(run.message && run.message !== 'OK' ? run.message : 'Movie extras refreshed')
                    return
                }
                if (run.status === 'FAILED' || run.status === 'CANCELED') {
                    toast.error(run.lastError || run.message || 'Movie-extra refresh failed')
                    return
                }
            }
            toast.success('The refresh is still running in the background')
        } catch {
            toast.error('Could not refresh movie extras')
        } finally {
            setRefreshingExtras(false)
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
    const officialTrailer: MovieExtraSummary | null = localMovie?.officialTrailer ?? movie.trailer ?? null
    const movieExtras: MovieExtraSummary[] = localMovie?.movieExtras ?? movie.movieExtras

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
                {officialTrailer?.sharingUrl && (
                    <a className="btn btn-secondary" href={officialTrailer.sharingUrl} target="_blank" rel="noreferrer">
                        <FontAwesomeIcon icon={['fas', 'play']}/> Watch trailer
                    </a>
                )}
                {movie.sharingUrl && (
                    <a className="btn" href={movie.sharingUrl} target="_blank" rel="noreferrer">
                        <FontAwesomeIcon icon={['fas', 'arrow-up-right-from-square']}/> Open on Daily Wire
                    </a>
                )}
                {localMovies && !localMovie && (
                    <button type="button" className="btn btn-primary" onClick={() => void addMovie()} disabled={addingMovie || submitting !== null}>
                        <FontAwesomeIcon icon={['fas', 'plus']}/>
                        {addingMovie ? 'Adding to WireLoft…' : 'Add to WireLoft'}
                    </button>
                )}
                {localMovie && (
                    <button type="button" className="btn" onClick={() => void refreshMovieExtras()} disabled={refreshingExtras}>
                        <FontAwesomeIcon icon={['fas', 'rotate']} spin={refreshingExtras}/>
                        {refreshingExtras ? 'Refreshing extras…' : 'Refresh extras'}
                    </button>
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
                </div>

                <aside className="movie-download-panel" aria-labelledby="download-movie-title">
                    <h2 id="download-movie-title">Download movie media</h2>
                    <p>Movies and extras use the same Movie Local Media Profile.</p>
                    {videoProfiles.length ? (
                        <>
                            <label htmlFor="movie-profile">Local Media Profile</label>
                            <select id="movie-profile" className="input" value={profileId} onChange={(event) => setProfileId(event.target.value)}>
                                {videoProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
                            </select>
                            <button className="btn btn-primary movie-download-button" type="button" onClick={() => void startMovieDownload()} disabled={submitting !== null || addingMovie || !movie.isDownloadable}>
                                <FontAwesomeIcon icon={['fas', 'download']}/>
                                {submitting === 'movie' ? 'Queuing…' : 'Download movie'}
                            </button>
                            {officialTrailer && (
                                <button className="btn movie-download-button" type="button" onClick={() => void startExtraDownload(officialTrailer)} disabled={submitting !== null || addingMovie}>
                                    <FontAwesomeIcon icon={['fas', 'download']}/>
                                    {submitting === `extra:${officialTrailer.slug}` ? 'Queuing…' : 'Download trailer'}
                                </button>
                            )}
                        </>
                    ) : (
                        <div className="movie-profile-empty">
                            <p>Create a Movie Local Media Profile before downloading a movie or extra.</p>
                            <Link className="btn" to="/add-local-media-profile?type=movie">Create profile</Link>
                        </div>
                    )}
                </aside>
            </div>

            {movieExtras.length > 0 && (
                <section className="movie-extras" aria-labelledby="movie-extras-title">
                    <div className="movie-section-heading">
                        <div>
                            <h2 id="movie-extras-title">Extras</h2>
                            <p>{localMovie ? 'Extras indexed in your WireLoft library.' : 'Extra content available for this movie.'}</p>
                        </div>
                        <span>{movieExtras.length}</span>
                    </div>
                    <div className="movie-extra-grid">
                        {movieExtras.map((extra) => {
                            const thumbnail = toImageUrl(extra.thumbnailLandscapePath || extra.backgroundImagePath)
                            const isOfficial = officialTrailer?.slug === extra.slug
                            return (
                                <article className="movie-extra-card" key={extra.id ?? extra.slug}>
                                    <div className="movie-extra-art">
                                        {thumbnail
                                            ? <img src={thumbnail} alt=""/>
                                            : <FontAwesomeIcon icon={['fas', 'film']}/>
                                        }
                                        <span>{movieExtraTypeLabel(extra.movieExtraType)}</span>
                                    </div>
                                    <div className="movie-extra-copy">
                                        <div>
                                            <strong>{extra.title}</strong>
                                            <small>
                                                {[formatDuration(extra.duration), isOfficial ? 'Official trailer' : null].filter(Boolean).join(' • ') || 'Movie extra'}
                                            </small>
                                        </div>
                                        <div className="movie-extra-actions">
                                            {extra.sharingUrl && (
                                                <a className="btn btn-icon" href={extra.sharingUrl} target="_blank" rel="noreferrer" aria-label={`Watch ${extra.title}`} title="Watch on Daily Wire">
                                                    <FontAwesomeIcon icon={['fas', 'play']}/>
                                                </a>
                                            )}
                                            <button
                                                className="btn btn-primary"
                                                type="button"
                                                onClick={() => void startExtraDownload(extra)}
                                                disabled={submitting !== null || addingMovie || !profileId}
                                            >
                                                <FontAwesomeIcon icon={['fas', 'download']}/>
                                                {submitting === `extra:${extra.slug}` ? 'Queuing…' : 'Download'}
                                            </button>
                                        </div>
                                    </div>
                                </article>
                            )
                        })}
                    </div>
                </section>
            )}

            {!!downloads?.length && (
                <section className="movie-downloads" aria-labelledby="movie-downloads-title">
                    <h2 id="movie-downloads-title">Downloads</h2>
                    {downloads.map((download) => (
                        <div className="movie-download-row" key={download.id}>
                            <div>
                                <strong>{download.type === 'movie_extra' ? movieExtraTypeLabel(download.movieExtraType) : 'Movie'} · {download.localMediaProfileName}</strong>
                                <small>{download.mediaTitle && download.type === 'movie_extra' ? `${download.mediaTitle} • ` : ''}{download.formatDownloaded || download.preferredFormat || 'Waiting for format'}</small>
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
                            Are you sure you want to delete "{movie.title}" from WireLoft? This removes the movie, its
                            indexed extras, and their download history from the WireLoft database. Completed files
                            already on disk will not be changed. Any download still in progress will be cancelled and
                            its partial files removed.
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
