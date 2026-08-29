import {useEffect, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Link, useNavigate, useSearchParams} from 'react-router-dom'

import {toImageUrl} from '../components/Episode/EpisodeCard'
import {useMediaDownloadsView, useMovies, useShowsView} from '../lib/queries'
import {MediaDownloadViewRead} from '../types/schemas/media_download'

type LibraryType = 'shows' | 'movies'

function latestMovieDownload(downloads: MediaDownloadViewRead[] | undefined, slug: string) {
    return downloads?.find((download) => download.movieSlug === slug)
}

export default function LibraryPage() {
    const navigate = useNavigate()
    const [params, setParams] = useSearchParams()
    const {data: shows, isLoading: showsLoading, error: showsError} = useShowsView()
    const {data: movies, isLoading: moviesLoading, error: moviesError} = useMovies()
    const {data: downloads} = useMediaDownloadsView()
    const hasShows = !!shows?.length
    const hasMovies = !!movies?.length
    const requested = params.get('type') as LibraryType | null
    const initialType: LibraryType = requested === 'movies' ? 'movies' : 'shows'
    const [activeType, setActiveType] = useState<LibraryType>(initialType)

    useEffect(() => {
        if (hasShows && !hasMovies && activeType !== 'shows') setActiveType('shows')
        if (hasMovies && !hasShows && activeType !== 'movies') setActiveType('movies')
    }, [activeType, hasMovies, hasShows])

    const chooseType = (type: LibraryType) => {
        setActiveType(type)
        setParams({type}, {replace: true})
    }

    const loading = showsLoading || moviesLoading
    const error = showsError || moviesError
    const showTabs = hasShows && hasMovies

    return (
        <section className="view library-view" aria-labelledby="library-title">
            <div className="view-header">
                <div>
                    <h1 id="library-title">Library</h1>
                    <p className="view-description">Shows indexed by WireLoft and movies you have downloaded or queued.</p>
                </div>
                <button className="btn btn-primary" onClick={() => navigate('/browse')}>
                    <FontAwesomeIcon icon={['fas', 'compass']}/>
                    Browse Daily Wire
                </button>
            </div>

            {showTabs && (
                <div className="media-type-tabs" role="tablist" aria-label="Library media type">
                    <button type="button" role="tab" aria-selected={activeType === 'shows'} onClick={() => chooseType('shows')}>
                        <FontAwesomeIcon icon={['fas', 'tv']}/>
                        Shows <span>{shows?.length ?? 0}</span>
                    </button>
                    <button type="button" role="tab" aria-selected={activeType === 'movies'} onClick={() => chooseType('movies')}>
                        <FontAwesomeIcon icon={['fas', 'clapperboard']}/>
                        Movies <span>{movies?.length ?? 0}</span>
                    </button>
                </div>
            )}

            {loading && !hasShows && !hasMovies ? (
                <p>Loading library…</p>
            ) : error && !hasShows && !hasMovies ? (
                <div className="form-error-card" role="alert">{error.message}</div>
            ) : !hasShows && !hasMovies ? (
                <div className="library-empty">
                    <FontAwesomeIcon icon={['fas', 'book-open']}/>
                    <h2>Your library is empty</h2>
                    <p>Browse Daily Wire to add a show or manually download a movie.</p>
                    <button className="btn btn-primary" onClick={() => navigate('/browse')}>Browse Daily Wire</button>
                </div>
            ) : activeType === 'shows' && hasShows ? (
                <div className="library-show-list" role="list" aria-label="Shows">
                    {shows!.map((show) => {
                        const image = toImageUrl(
                            show.thumbnailPortraitPath || show.thumbnailLandscapePath || show.logoImagePath || show.authorHeadshotPath,
                        )
                        return (
                            <Link className="show-summary-card library-show-card" to={`/show/${show.slug}`} key={show.slug} role="listitem">
                                <span className="show-summary-art">
                                    {image ? <img src={image} alt="" loading="lazy" decoding="async"/> : <span className="show-art-placeholder"><FontAwesomeIcon icon={['fas', 'podcast']}/></span>}
                                </span>
                                <span className="show-summary-copy">
                                    <span className="show-summary-title">{show.title}</span>
                                    <span className="show-summary-author">{show.authorName || 'Daily Wire'}</span>
                                    <span className="show-summary-meta">{show.episodeCount} episodes{show.years ? ` • ${show.years}` : ''}</span>
                                    {show.description && <span className="show-summary-description">{show.description}</span>}
                                </span>
                                <FontAwesomeIcon icon={['fas', 'chevron-right']} aria-hidden="true"/>
                            </Link>
                        )
                    })}
                </div>
            ) : activeType === 'movies' && hasMovies ? (
                <div className="movie-poster-grid" role="list" aria-label="Movies">
                    {movies!.map((movie) => {
                        const image = toImageUrl(movie.thumbnailPortraitPath || movie.thumbnailLandscapePath || movie.backgroundImagePath)
                        const download = latestMovieDownload(downloads, movie.slug)
                        const status = String(download?.downloadStatus || '')
                        return (
                            <Link className="movie-poster-card" to={`/movie/${movie.slug}`} key={movie.slug} role="listitem">
                                <span className="movie-poster-art">
                                    {image
                                        ? <img src={image} alt="" loading="lazy" decoding="async"/>
                                        : <FontAwesomeIcon icon={['fas', 'clapperboard']}/>
                                    }
                                    {status === 'downloaded' || status === 'redownloaded' ? (
                                        <span className="movie-state is-complete" aria-label="Downloaded"><FontAwesomeIcon icon={['fas', 'check']}/></span>
                                    ) : status === 'downloading' || status === 'pending' ? (
                                        <span className="movie-state is-active" aria-label="Downloading"><FontAwesomeIcon icon={['fas', 'circle-down']}/></span>
                                    ) : status === 'error' ? (
                                        <span className="movie-state is-error" aria-label="Download failed"><FontAwesomeIcon icon={['fas', 'triangle-exclamation']}/></span>
                                    ) : null}
                                </span>
                                <span className="movie-poster-title">{movie.title}</span>
                                <span className="movie-poster-meta">{movie.authorName || 'Daily Wire'}</span>
                            </Link>
                        )
                    })}
                </div>
            ) : null}
        </section>
    )
}
