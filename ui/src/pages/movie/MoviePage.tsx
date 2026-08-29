import {useEffect, useMemo, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Link, useParams} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'

import ProgressBar from '../../components/common/ProgressBar'
import {toImageUrl} from '../../components/Episode/EpisodeCard'
import {useDailywireMovie, useLocalMediaProfiles, useMovieDownloads} from '../../lib/queries'
import {getErrorMessageFromResponse} from '../../utils/helpers'

function formatDuration(seconds: number) {
    if (!seconds) return null
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.round((seconds % 3600) / 60)
    return hours ? `${hours}h ${minutes}m` : `${minutes}m`
}

export default function MoviePage() {
    const {slug} = useParams()
    const queryClient = useQueryClient()
    const {data: movie, error} = useDailywireMovie(slug)
    const {data: profiles} = useLocalMediaProfiles()
    const {data: downloads} = useMovieDownloads(slug)
    const videoProfiles = useMemo(
        () => profiles?.filter((profile) => profile.type === 'movie') || [],
        [profiles],
    )
    const [profileId, setProfileId] = useState('')
    const [submitting, setSubmitting] = useState(false)

    useEffect(() => {
        if (!profileId && videoProfiles[0]) setProfileId(String(videoProfiles[0].id))
    }, [profileId, videoProfiles])

    const startDownload = async () => {
        if (!slug || !profileId) return
        setSubmitting(true)
        try {
            const response = await fetch(`${(window as any).appConfig.API_URL}/movies/${encodeURIComponent(slug)}/downloads`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({localMediaProfileId: Number(profileId)}),
            })
            if (!response.ok) {
                const {error: message} = await getErrorMessageFromResponse(response)
                toast.error(message || 'Could not start the movie download')
                return
            }
            toast.success('Movie download queued')
            await Promise.all([
                queryClient.invalidateQueries({queryKey: ['movies']}),
                queryClient.invalidateQueries({queryKey: ['movieDownloads', slug]}),
                queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
            ])
        } catch {
            toast.error('Could not start the movie download')
        } finally {
            setSubmitting(false)
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
                    <h2 id="download-movie-title">Download movie</h2>
                    <p>Movies are downloaded manually using a Local Media Profile. Download Profiles are not used.</p>
                    {videoProfiles.length ? (
                        <>
                            <label htmlFor="movie-profile">Local Media Profile</label>
                            <select id="movie-profile" className="input" value={profileId} onChange={(event) => setProfileId(event.target.value)}>
                                {videoProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
                            </select>
                            <button className="btn btn-primary movie-download-button" type="button" onClick={startDownload} disabled={submitting || !movie.isDownloadable}>
                                <FontAwesomeIcon icon={['fas', 'download']}/>
                                {submitting ? 'Queuing…' : 'Download movie'}
                            </button>
                        </>
                    ) : (
                        <div className="movie-profile-empty">
                            <p>Create a Movie Local Media Profile before downloading a movie.</p>
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
                            <div><strong>{download.localMediaProfileName}</strong><small>{download.formatDownloaded || download.preferredFormat || 'Waiting for format'}</small></div>
                            {(download.downloadStatus === 'downloading' || download.downloadStatus === 'pending') ? (
                                <div className="movie-download-progress"><ProgressBar value={download.progress} ariaLabel={`Download progress for ${movie.title}`}/><span>{download.downloadStatus === 'pending' ? 'Queued' : `${download.progress}%`}</span></div>
                            ) : <span className={`download-status status-${download.downloadStatus}`}>{String(download.downloadStatus).replace(/_/g, ' ')}</span>}
                        </div>
                    ))}
                </section>
            )}
        </section>
    )
}
