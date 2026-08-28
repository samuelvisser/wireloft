import {library} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@awesome.me/kit-83fa1ac5a9/icons'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Link} from 'react-router-dom'
import React from 'react'
import {useEpisodes, useMediaDownloadsView, useShowIndexingRun, useShowsView} from '../lib/queries'
import EpisodeCard, {groupDownloadsByEpisodeSlug, toImageUrl} from '../components/Episode/EpisodeCard'
import {EpisodeRead} from "../types/schemas/episode";
import {useQueryClient} from '@tanstack/react-query'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)
export type Episode = EpisodeRead

function ShowSection({show, downloadsBySlug}: { show: any; downloadsBySlug: Map<string, any[]> }) {
    const {data: episodes, isLoading} = useEpisodes(show.slug, { limit: 20 })
    const eps: Episode[] = episodes ?? []

    const {data: indexingRun} = useShowIndexingRun(show.id as number | undefined)
    const progress: number | undefined = indexingRun?.progress ?? undefined

    // When indexing completes (progressbar disappears), refetch episodes for this show
    const qc = useQueryClient()
    const prevHadRun = React.useRef<boolean>(false)
    React.useEffect(() => {
        const hasRun = !!indexingRun
        if (prevHadRun.current && !hasRun) {
            // Indexing finished: refresh the entire show card (metadata + episodes)
            qc.invalidateQueries({ queryKey: ['showsView'] })
            qc.invalidateQueries({ queryKey: ['episodes', show.slug], exact: false })
        }
        prevHadRun.current = hasRun
    }, [indexingRun, qc, show.slug])

    const author = show.authorName
    const portraitPath: string | undefined = show.thumbnailPortraitPath || show.thumbnailLandscapePath || show.logoImagePath || show.authorHeadshotPath
    const portrait = toImageUrl(portraitPath)

    return (
        <article className="show-section" key={show.id} aria-labelledby={`${show.slug}-title`}>
            <Link to={`/show/${show.slug}`} className="show-header" aria-labelledby={`${show.slug}-title`}>
                <div className="show-header-row">
                    {portrait ? (
                        <img className="show-portrait" src={portrait} alt={`${show.title} cover`} />
                    ) : null}
                    <div className="show-header-text">
                        <div className="show-author">{author}</div>
                        <h2 id={`${show.slug}-title`} className="show-title">{show.title}</h2>
                        <div className="show-meta">
                            {isLoading && !episodes
                                ? 'Loading episodes…'
                                : `${show.episodeCount} episodes${show.years ? ` • ${show.years}` : ''}`}
                        </div>
                    </div>
                </div>
            </Link>
            {indexingRun ? (
                <div className="show-progress" style={{ padding: '6px 0 10px 0' }} aria-live="polite">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                        <span style={{ fontSize: 12, color: '#666' }}>
                            {progress !== undefined ? `Indexing… ${progress}%` : 'Indexing…'}
                        </span>
                        {progress === undefined && (
                            <FontAwesomeIcon icon={["fas", "spinner"] as any} spin/>
                        )}
                    </div>
                    {progress !== undefined && (
                        <div
                            className="progress"
                            role="progressbar"
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-valuenow={progress}
                            aria-label="Indexing progress"
                            style={{ height: 6, background: '#eee', borderRadius: 4, overflow: 'hidden' }}
                        >
                            <div
                                className="progress-fill"
                                style={{ width: `${progress}%`, height: '100%', background: '#0d6efd', transition: 'width 0.3s ease' }}
                            />
                        </div>
                    )}
                </div>
            ) : null}
            <div className="episodes-row" role="list" aria-label={`${show.title} episodes`}>
                {eps.map((ep: Episode) => (
                    <EpisodeCard key={ep.id} ep={ep} showSlug={show.slug} downloads={downloadsBySlug.get(ep.slug)}/>
                ))}
            </div>
        </article>
    )
}

export default function HomePage({onAddShow}: { onAddShow: () => void }) {
    const {data: shows, isLoading, error} = useShowsView()
    const {data: downloads} = useMediaDownloadsView()
    const downloadsBySlug = React.useMemo(() => groupDownloadsByEpisodeSlug(downloads), [downloads])

    return (
        <section className="view shows-view" aria-labelledby="home-title">
            <div className="view-header">
                <h1 id="home-title">Shows</h1>
                <button className="btn btn-primary" onClick={onAddShow}>
                    Add show
                </button>
            </div>
            {isLoading && !shows ? (
                <p>Loading shows...</p>
            ) : !shows || shows.length === 0 ? (
                <p>{(error as any)?.message ?? 'No shows found'}</p>
            ) : (
                shows.map((show) => (
                    <ShowSection key={show.id} show={show} downloadsBySlug={downloadsBySlug}/>
                ))
            )}
        </section>
    )
}
