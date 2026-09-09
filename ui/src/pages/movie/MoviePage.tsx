import {useEffect, useMemo, useRef, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Link, useNavigate, useParams} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'

import ProgressBar from '../../components/common/ProgressBar'
import ConfirmDialog from '../../components/ConfirmDialog/ConfirmDialog'
import {toImageUrl} from '../../components/Episode/EpisodeCard'
import {useActiveOperation} from '../../components/OperationNotifier/OperationNotifier'
import {useDailywireMovie, useLocalMediaProfiles, useMovieDownloads, useMovies} from '../../lib/queries'
import {OperationStartError, useStartOperation} from '../../lib/operations'
import {MovieExtraType} from '../../types/schemas/dailywire_catalog'
import {getErrorMessageFromResponse} from '../../utils/helpers'
import {movieExtraTypeLabel} from '../../utils/movieExtras'
import './MoviePage.css'

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

function formatReleaseDate(value?: string | null) {
    if (!value) return null
    const parsed = new Date(`${value}T00:00:00Z`)
    if (Number.isNaN(parsed.getTime())) return value
    return parsed.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        timeZone: 'UTC',
    })
}

export default function MoviePage() {
    const {slug} = useParams()
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const startOperation = useStartOperation()
    const {data: localMovies, error: localMoviesError} = useMovies()
    const localMovie = useMemo(
        () => localMovies?.find((item) => item.slug === slug),
        [localMovies, slug],
    )
    const {
        data: dailywireMovie,
        error: dailywireMovieError,
    } = useDailywireMovie(localMovies && !localMovie ? slug : undefined)
    const movie = localMovie ?? dailywireMovie
    const refreshAttemptedSlugs = useRef(new Set<string>())
    const {data: profiles} = useLocalMediaProfiles()
    const {data: downloads} = useMovieDownloads(slug)
    const refreshExtrasOperation = useActiveOperation(
        'movie.refresh_extras',
        'movie',
        localMovie?.id ?? null,
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
    const [refreshingExtrasStarting, setRefreshingExtrasStarting] = useState(false)
    const refreshingExtras = refreshingExtrasStarting || refreshExtrasOperation !== undefined

    useEffect(() => {
        if (!profileId && videoProfiles[0]) setProfileId(String(videoProfiles[0].id))
    }, [profileId, videoProfiles])

    useEffect(() => {
        if (
            !slug
            || !localMovie
            || (localMovie.status === 'published' && localMovie.isDownloadable)
            || refreshAttemptedSlugs.current.has(slug)
        ) return

        refreshAttemptedSlugs.current.add(slug)
        const controller = new AbortController()
        const refresh = async () => {
            try {
                const response = await fetch(
                    `${(window as any).appConfig.API_URL}/movies/${encodeURIComponent(slug)}/refresh`,
                    {
                        method: 'POST',
                        credentials: 'include',
                        signal: controller.signal,
                    },
                )
                if (response.ok) {
                    await queryClient.invalidateQueries({queryKey: ['movies']})
                }
            } catch {
                // The persisted movie remains fully usable when Daily Wire is unavailable.
            }
        }
        void refresh()
        return () => controller.abort()
    }, [localMovie, queryClient, slug])

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
        setRefreshingExtrasStarting(true)
        try {
            const base = (window as any).appConfig.API_URL
            await startOperation(
                `${base}/movies/${encodeURIComponent(slug)}/extras/refresh`,
                {method: 'POST'},
            )
            toast.success('Movie-extra refresh started')
        } catch (error) {
            const detail = error instanceof OperationStartError ? error.message : undefined
            toast.error(detail ? `Could not refresh movie extras: ${detail}` : 'Could not refresh movie extras')
        } finally {
            setRefreshingExtrasStarting(false)
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

    const movieError = localMoviesError ?? dailywireMovieError
    if (!movie && !movieError) return <section className="view"><p>Loading movie…</p></section>
    if (movieError || !movie) return <section className="view"><div className="form-error-card" role="alert">Could not load this movie: {movieError?.message || 'Movie not found'}</div></section>

    const isUpcoming = localMovie ? localMovie.status === 'scheduled' : dailywireMovie?.isUpcoming ?? false
    const hero = toImageUrl(movie.backgroundImagePath || movie.thumbnailLandscapePath || movie.thumbnailPortraitPath)
    const duration = formatDuration(movie.duration)
    const featuredTrailer: MovieExtraSummary | null = localMovie?.officialTrailer ?? dailywireMovie?.trailer ?? null
    const movieExtras: MovieExtraSummary[] = localMovie?.movieExtras ?? dailywireMovie?.movieExtras ?? []
    const expectedReleaseDate = formatReleaseDate(
        localMovie ? (isUpcoming ? localMovie.releaseDate : null) : dailywireMovie?.expectedReleaseDate,
    )

    return (
        <section className="view movie-detail-view" aria-labelledby="movie-title">
            <div className="movie-hero" style={hero ? {backgroundImage: `linear-gradient(0deg, var(--bg) 0%, rgba(9,18,33,.15) 72%), url(${hero})`} : undefined}>
                <div>
                    <div className="movie-kicker-row">
                        <span className="movie-kicker"><FontAwesomeIcon icon={['fas', 'clapperboard']}/> Movie</span>
                        {isUpcoming && <span className="movie-upcoming-badge">Upcoming</span>}
                    </div>
                    <h1 id="movie-title">{movie.title}</h1>
                    <p>{[movie.authorName, duration, movie.matureRating].filter(Boolean).join(' • ')}</p>
                    {isUpcoming && expectedReleaseDate && (
                        <p className="movie-expected-release">Expected release {expectedReleaseDate}</p>
                    )}
                </div>
            </div>

            <div className="movie-detail-actions">
                {featuredTrailer?.sharingUrl && (
                    <a className="btn btn-secondary" href={featuredTrailer.sharingUrl} target="_blank" rel="noreferrer">
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
                    <p>
                        {isUpcoming
                            ? 'The full movie is not available yet. Published extras can be downloaded now.'
                            : 'Movies and extras use the same Movie Local Media Profile.'}
                    </p>
                    {videoProfiles.length ? (
                        <>
                            <label htmlFor="movie-profile">Local Media Profile</label>
                            <select id="movie-profile" className="input" value={profileId} onChange={(event) => setProfileId(event.target.value)}>
                                {videoProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
                            </select>
                            {movie.isDownloadable ? (
                                <button className="btn btn-primary movie-download-button" type="button" onClick={() => void startMovieDownload()} disabled={submitting !== null || addingMovie}>
                                    <FontAwesomeIcon icon={['fas', 'download']}/>
                                    {submitting === 'movie' ? 'Queuing…' : 'Download movie'}
                                </button>
                            ) : (
                                <div className="movie-download-unavailable" role="status">
                                    {isUpcoming
                                        ? expectedReleaseDate
                                            ? `Full movie expected ${expectedReleaseDate}.`
                                            : 'Full movie has not been released yet.'
                                        : 'Daily Wire does not currently offer the full movie for download.'}
                                </div>
                            )}
                            {featuredTrailer && (
                                <button className="btn movie-download-button" type="button" onClick={() => void startExtraDownload(featuredTrailer)} disabled={submitting !== null || addingMovie}>
                                    <FontAwesomeIcon icon={['fas', 'download']}/>
                                    {submitting === `extra:${featuredTrailer.slug}` ? 'Queuing…' : 'Download trailer'}
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
                            <p>{localMovie ? 'Extras available for this movie.' : 'Extra content available for this movie.'}</p>
                        </div>
                        <span>{movieExtras.length}</span>
                    </div>
                    <div className="movie-extra-grid">
                        {movieExtras.map((extra) => {
                            const thumbnail = toImageUrl(extra.thumbnailLandscapePath || extra.backgroundImagePath)
                            const isFeatured = featuredTrailer?.slug === extra.slug
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
                                                {[formatDuration(extra.duration), isFeatured ? 'Featured trailer' : null].filter(Boolean).join(' • ') || 'Movie extra'}
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

            <ConfirmDialog
                open={confirmDelete && Boolean(localMovie)}
                title="Delete movie"
                onDismiss={() => {
                    if (!deleting) setConfirmDelete(false)
                }}
                icon={['fas', 'trash']}
                iconTone="danger"
                dismissOnOverlayClick={!deleting}
                cancelButton={{disabled: deleting}}
                confirmButton={{
                    label: deleting ? 'Deleting…' : 'Delete',
                    onClick: deleteMovie,
                    className: 'btn btn-danger',
                    disabled: deleting,
                }}
            >
                <p>
                    Are you sure you want to delete "{movie.title}" from WireLoft? This removes the movie, its
                    indexed extras, and their download history from the WireLoft database. Completed files
                    already on disk will not be changed. Any download still in progress will be cancelled and
                    its partial files removed.
                </p>
            </ConfirmDialog>
        </section>
    )
}
