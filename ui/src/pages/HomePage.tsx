import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {library} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@awesome.me/kit-83fa1ac5a9/icons'
import {Link, useNavigate} from 'react-router-dom'
import React from 'react'
import {useEpisodes, useShowIndexingRun, useShowsView} from '../lib/queries'
import {statusIcon, statusLabel} from '../utils/showStatus'
import {EpisodeRead} from "../types/schemas/episode";
import {useQueryClient} from '@tanstack/react-query'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)
export type Episode = EpisodeRead

function toImageUrl(path?: string): string | undefined {
    if (!path) return undefined
    // If already an absolute URL, return as-is
    if (/^https?:\/\//i.test(path)) return path
    const base = (window as any).appConfig?.API_URL?.replace(/\/+$/, '')
    if (!base) return path
    // If path is already rooted, just prefix API base
    if (path.startsWith('/')) return base + path
    // Default: serve from generic assets path
    return `${base}/assets/${path}`
}

function ShowSection({show}: { show: any }) {
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
                    <EpisodeCard key={ep.id} ep={ep} showSlug={show.slug}/>
                ))}
            </div>
        </article>
    )
}

function EpisodeCard({ep, showSlug}: { ep: Episode; showSlug: string }) {
    const initials = ep.title
        .split(' ')
        .map((w: any) => w[0])
        .join('')
        .slice(0, 3)
        .toUpperCase()

    // Prefer episode thumbnailPortraitPath; if missing/empty, use a placeholder with the episode index.
    const portraitPath = (ep.thumbnailPortraitPath && ep.thumbnailPortraitPath.trim() !== '') ? ep.thumbnailPortraitPath : undefined
    const imageUrl = portraitPath ? toImageUrl(portraitPath) : `https://placehold.co/640x360/png?text=Episode+%23${ep.index}`
    const style = imageUrl ? { backgroundImage: `url(${imageUrl})` } : undefined

    const icon = statusIcon(ep.publishStatus)
    const label = statusLabel(ep.publishStatus)
    const isProcessing = ep.publishStatus === 'dw_processing' || ep.publishStatus === 'local_processing'

    const navigate = useNavigate()
    const goToEpisode = () => navigate(`/show/${showSlug}/episode/${ep.slug}`)
    const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            goToEpisode()
        }
    }

    return (
        <div className="episode-card" role="listitem" aria-label={ep.title} tabIndex={0} onKeyDown={onKeyDown}>
            <div className="cover" style={style} onClick={goToEpisode}>
                {/* status icon in bottom-left */}
                <span className={`status status-${ep.unified_status}`} aria-label={label} title={label}>
          <FontAwesomeIcon icon={icon as any} spin={isProcessing}/>
        </span>
                {/* Show initials only if we are using the placeholder (i.e., no real thumbnail) */}
                {!portraitPath && (
                    <span className="cover-text" aria-hidden>
            {initials}
          </span>
                )}
                <span className="badge">#{ep.index}</span>
            </div>
            <div className="episode-title" title={ep.title}>{ep.title}</div>
        </div>
    )
}

export default function HomePage({onAddShow}: { onAddShow: () => void }) {
    const {data: shows, isLoading, error} = useShowsView()

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
                    <ShowSection key={show.id} show={show}/>
                ))
            )}
        </section>
    )
}
