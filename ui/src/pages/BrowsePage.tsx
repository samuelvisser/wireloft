import {useEffect, useMemo, useRef, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useNavigate, useSearchParams} from 'react-router-dom'

import {toImageUrl} from '../components/Episode/EpisodeCard'
import MediaTypeTabs, {MediaType} from '../components/MediaTypeTabs/MediaTypeTabs'
import {useDailywireMovieCatalog, useDailywireShowCatalog, useMovies, useShows} from '../lib/queries'
import {
    DailywireCatalogMovieRead,
    DailywireCatalogShowRead,
} from '../types/schemas/dailywire_catalog'

type ShowGrouping = 'alphabetical' | 'host'

type BrowsePageProps = {
    onboarding?: boolean
    onShowSelect?: (show: DailywireCatalogShowRead) => void
    onMovieSelect?: (movie: DailywireCatalogMovieRead) => void
    onSkip?: () => void
}

function groupShows(shows: DailywireCatalogShowRead[], grouping: ShowGrouping) {
    const groups = new Map<string, DailywireCatalogShowRead[]>()
    for (const show of shows) {
        const key = grouping === 'host' ? (show.authorName || 'Other') : (show.title[0]?.toUpperCase() || '#')
        const group = groups.get(key) || []
        group.push(show)
        groups.set(key, group)
    }
    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right))
}

export default function BrowsePage({onboarding = false, onShowSelect, onMovieSelect, onSkip}: BrowsePageProps = {}) {
    const navigate = useNavigate()
    const [params, setParams] = useSearchParams()
    const initialType = params.get('type') === 'movies' ? 'movies' : 'shows'
    const [activeType, setActiveType] = useState<MediaType>(initialType)
    const [grouping, setGrouping] = useState<ShowGrouping>('host')
    const [search, setSearch] = useState('')
    const [debouncedSearch, setDebouncedSearch] = useState('')
    useEffect(() => {
        const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 250)
        return () => window.clearTimeout(timer)
    }, [search])

    const showCatalog = useDailywireShowCatalog(debouncedSearch, grouping, activeType === 'shows')
    const movieCatalog = useDailywireMovieCatalog(debouncedSearch, activeType === 'movies')
    const {data: localShows} = useShows()
    const {data: localMovies} = useMovies()
    const localShowsBySlug = useMemo(
        () => new Map(localShows?.map((show) => [show.slug, show]) ?? []),
        [localShows],
    )
    const localMovieSlugs = useMemo(
        () => new Set(localMovies?.map((movie) => movie.slug) ?? []),
        [localMovies],
    )

    const shows = useMemo(
        () => showCatalog.data?.pages.flatMap((page) => page.items) || [],
        [showCatalog.data],
    )
    const movies = useMemo(
        () => movieCatalog.data?.pages.flatMap((page) => page.items) || [],
        [movieCatalog.data],
    )
    const groupedShows = useMemo(() => groupShows(shows, grouping), [grouping, shows])

    const activeQuery = activeType === 'shows' ? showCatalog : movieCatalog
    const hasItems = activeType === 'shows' ? shows.length > 0 : movies.length > 0
    const loadMoreRef = useRef<HTMLDivElement | null>(null)
    useEffect(() => {
        const node = loadMoreRef.current
        if (!node || !activeQuery.hasNextPage || activeQuery.isFetchingNextPage || activeQuery.isFetchNextPageError) return
        const observer = new IntersectionObserver((entries) => {
            if (entries[0]?.isIntersecting) void activeQuery.fetchNextPage()
        }, {rootMargin: '600px'})
        observer.observe(node)
        return () => observer.disconnect()
    }, [activeQuery.fetchNextPage, activeQuery.hasNextPage, activeQuery.isFetchNextPageError, activeQuery.isFetchingNextPage, activeType])

    const chooseType = (type: MediaType) => {
        setActiveType(type)
        setParams({type}, {replace: true})
    }

    const chooseShow = (show: DailywireCatalogShowRead) => {
        if (onShowSelect) {
            onShowSelect(show)
            return
        }
        const localShow = localShowsBySlug.get(show.slug)
        if (localShow) {
            navigate(`/show/${localShow.slug}`)
            return
        }
        const url = `https://www.dailywire.com/show/${show.slug}`
        navigate(`/add-show?url=${encodeURIComponent(url)}`)
    }

    const chooseMovie = (movie: DailywireCatalogMovieRead) => {
        if (onMovieSelect) {
            onMovieSelect(movie)
            return
        }
        navigate(`/movie/${movie.slug}`)
    }

    return (
        <section className={`view browse-view${onboarding ? ' browse-view--onboarding' : ''}`} aria-labelledby="browse-title">
            <div className="view-header">
                <div>
                    <h1 id="browse-title">{onboarding ? 'Add your first media' : 'Browse Daily Wire'}</h1>
                    <p className="view-description">
                        {onboarding
                            ? 'Choose a show or movie. WireLoft will let you confirm its download location before anything is saved.'
                            : 'Choose a show or movie to add, view, or download.'}
                    </p>
                </div>
                {onSkip && (
                    <button className="btn" type="button" onClick={onSkip}>
                        Skip for now
                    </button>
                )}
            </div>
            <MediaTypeTabs activeType={activeType} onChange={chooseType} ariaLabel="Browse media type"/>
            <div className="browse-toolbar">
                <label className="browse-search">
                    <span className="sr-only">Search {activeType}</span>
                    <FontAwesomeIcon icon={['fas', 'magnifying-glass']} aria-hidden="true"/>
                    <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${activeType}`}/>
                </label>
                {activeType === 'shows' && (
                    <div className="compact-switch" role="group" aria-label="Group shows">
                        <button type="button" aria-pressed={grouping === 'alphabetical'} onClick={() => setGrouping('alphabetical')}>A–Z</button>
                        <button type="button" aria-pressed={grouping === 'host'} onClick={() => setGrouping('host')}>By host</button>
                    </div>
                )}
            </div>

            {activeQuery.isPending && !hasItems ? <p>Loading the Daily Wire catalog…</p> : activeQuery.error && !hasItems ? (
                <div className="form-error-card" role="alert">Could not load the Daily Wire catalog: {activeQuery.error.message}</div>
            ) : !hasItems ? (
                <div className="catalog-empty">
                    <FontAwesomeIcon icon={['fas', 'magnifying-glass']}/>
                    <p>No {activeType} match your search.</p>
                </div>
            ) : activeType === 'shows' ? (
                <div className="catalog-groups">
                    {groupedShows.map(([label, items], groupIndex) => (
                        <section className="catalog-group" key={label} aria-labelledby={`catalog-${grouping}-${groupIndex}`}>
                            <h2 id={`catalog-${grouping}-${groupIndex}`}>{label}</h2>
                            <div className="catalog-show-grid">
                                {items.map((show) => {
                                    const image = toImageUrl(show.thumbnailPortraitPath || show.thumbnailLandscapePath || show.backgroundImagePath)
                                    const added = localShowsBySlug.has(show.slug)
                                    return (
                                        <button className="show-summary-card catalog-show-card" type="button" key={show.slug} onClick={() => chooseShow(show)}>
                                            <span className="show-summary-art">
                                                {image ? <img src={image} alt="" loading="lazy" decoding="async"/> : <span className="show-art-placeholder"><FontAwesomeIcon icon={['fas', 'tv']}/></span>}
                                            </span>
                                            <span className="show-summary-copy">
                                                <strong className="show-summary-title">{show.title}</strong>
                                                <span className="show-summary-author">{show.authorName || 'Daily Wire'}</span>
                                                {show.description && <span className="show-summary-description">{show.description}</span>}
                                            </span>
                                            {added && <span className="catalog-added"><FontAwesomeIcon icon={['fas', 'check']}/> In library</span>}
                                        </button>
                                    )
                                })}
                            </div>
                        </section>
                    ))}
                </div>
            ) : (
                <div className="movie-poster-grid catalog-movie-grid" role="list" aria-label="Daily Wire movies">
                    {movies.map((movie) => {
                        const image = toImageUrl(movie.thumbnailPortraitPath || movie.thumbnailLandscapePath || movie.backgroundImagePath)
                        const added = localMovieSlugs.has(movie.slug)
                        return (
                            <button className="movie-poster-card" type="button" key={movie.slug} role="listitem" onClick={() => chooseMovie(movie)}>
                                <span className="movie-poster-art">
                                    {image
                                        ? <img src={image} alt="" loading="lazy" decoding="async"/>
                                        : <FontAwesomeIcon icon={['fas', 'clapperboard']}/>
                                    }
                                    {added && <span className="badge" style={{top: 8, bottom: 'auto'}}>In library</span>}
                                </span>
                                <span className="movie-poster-title">{movie.title}</span>
                                <span className="movie-poster-meta">{movie.authorName || 'Daily Wire'}</span>
                            </button>
                        )
                    })}
                </div>
            )}

            {activeQuery.hasNextPage && !activeQuery.isFetchNextPageError && (
                <div ref={loadMoreRef} className="catalog-load-more" aria-live="polite" aria-busy={activeQuery.isFetchingNextPage}>
                    {activeQuery.isFetchingNextPage && <><FontAwesomeIcon icon={['fas', 'circle-notch']} spin/> Loading more {activeType}…</>}
                </div>
            )}
            {activeQuery.isFetchNextPageError && (
                <div className="catalog-load-error" role="alert">
                    Could not load more {activeType}.
                    <button type="button" className="btn" onClick={() => void activeQuery.fetchNextPage()}>Try again</button>
                </div>
            )}
        </section>
    )
}
