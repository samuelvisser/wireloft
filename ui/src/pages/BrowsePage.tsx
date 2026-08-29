import {useMemo, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useNavigate, useSearchParams} from 'react-router-dom'

import {toImageUrl} from '../components/Episode/EpisodeCard'
import {useDailywireCatalog, useShows} from '../lib/queries'
import {DailywireCatalogShowRead} from '../types/schemas/dailywire_catalog'

type BrowseType = 'shows' | 'movies'
type ShowGrouping = 'alphabetical' | 'host'

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

export default function BrowsePage() {
    const navigate = useNavigate()
    const [params, setParams] = useSearchParams()
    const initialType = params.get('type') === 'movies' ? 'movies' : 'shows'
    const [activeType, setActiveType] = useState<BrowseType>(initialType)
    const [grouping, setGrouping] = useState<ShowGrouping>('alphabetical')
    const [search, setSearch] = useState('')
    const {data: catalog, isLoading, error} = useDailywireCatalog()
    const {data: localShows} = useShows()
    const localSlugs = useMemo(() => new Set(localShows?.map((show) => show.slug)), [localShows])
    const needle = search.trim().toLocaleLowerCase()

    const shows = useMemo(
        () => (catalog?.shows || []).filter((show) => !needle || `${show.title} ${show.authorName || ''}`.toLocaleLowerCase().includes(needle)),
        [catalog?.shows, needle],
    )
    const movies = useMemo(
        () => (catalog?.movies || []).filter((movie) => !needle || `${movie.title} ${movie.authorName || ''}`.toLocaleLowerCase().includes(needle)),
        [catalog?.movies, needle],
    )
    const groupedShows = useMemo(() => groupShows(shows, grouping), [grouping, shows])

    const chooseType = (type: BrowseType) => {
        setActiveType(type)
        setParams({type}, {replace: true})
    }

    const chooseShow = (show: DailywireCatalogShowRead) => {
        const url = `https://www.dailywire.com/show/${show.slug}`
        navigate(`/add-show?url=${encodeURIComponent(url)}`)
    }

    return (
        <section className="view browse-view" aria-labelledby="browse-title">
            <div className="view-header">
                <div>
                    <h1 id="browse-title">Browse Daily Wire</h1>
                    <p className="view-description">Choose a show to add, or a movie to view and download manually.</p>
                </div>
            </div>
            <div className="media-type-tabs browse-type-tabs" role="tablist" aria-label="Browse media type">
                <button type="button" role="tab" aria-selected={activeType === 'shows'} onClick={() => chooseType('shows')}>
                    <FontAwesomeIcon icon={['fas', 'tv']}/> Shows
                </button>
                <button type="button" role="tab" aria-selected={activeType === 'movies'} onClick={() => chooseType('movies')}>
                    <FontAwesomeIcon icon={['fas', 'clapperboard']}/> Movies
                </button>
            </div>
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

            {isLoading ? <p>Loading the Daily Wire catalog…</p> : error ? (
                <div className="form-error-card" role="alert">Could not load the Daily Wire catalog: {error.message}</div>
            ) : activeType === 'shows' ? (
                <div className="catalog-groups">
                    {groupedShows.map(([label, items]) => (
                        <section className="catalog-group" key={label} aria-labelledby={`catalog-${grouping}-${label}`}>
                            <h2 id={`catalog-${grouping}-${label}`}>{label}</h2>
                            <div className="catalog-show-grid">
                                {items.map((show) => {
                                    const image = toImageUrl(show.thumbnailPortraitPath || show.thumbnailLandscapePath || show.backgroundImagePath)
                                    const added = localSlugs.has(show.slug)
                                    return (
                                        <button className="catalog-show-card" type="button" key={show.slug} onClick={() => chooseShow(show)}>
                                            {image ? <img src={image} alt=""/> : <span className="catalog-placeholder"><FontAwesomeIcon icon={['fas', 'tv']}/></span>}
                                            <span><strong>{show.title}</strong><small>{show.authorName || 'Daily Wire'}</small></span>
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
                        return (
                            <button className="movie-poster-card" type="button" key={movie.slug} role="listitem" onClick={() => navigate(`/movie/${movie.slug}`)}>
                                <span className="movie-poster-art" style={image ? {backgroundImage: `url(${image})`} : undefined}/>
                                <span className="movie-poster-title">{movie.title}</span>
                                <span className="movie-poster-meta">{movie.authorName || 'Daily Wire'}</span>
                            </button>
                        )
                    })}
                </div>
            )}
        </section>
    )
}
