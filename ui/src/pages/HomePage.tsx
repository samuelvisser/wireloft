import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {library} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@awesome.me/kit-83fa1ac5a9/icons'
import {Link, useNavigate} from 'react-router-dom'
import React from 'react'
import {useShows, useEpisodes} from '../lib/queries'
import {statusIcon, statusLabel} from '../utils/showStatus'
import {EpisodeRead} from "../types/schemas/episode";

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
    const {data: episodes, isLoading} = useEpisodes(show.slug)
    const eps: Episode[] = episodes ?? []

    const author = show.author || show.authorName
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
                            {isLoading && !episodes ? 'Loading episodes…' : `${eps.length} episodes${show.years ? ` • ${show.years}` : ''}`}
                        </div>
                    </div>
                </div>
            </Link>
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
    const style = ep.cover ? {backgroundImage: `url(${ep.cover})`} : undefined
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
                {!ep.cover && (
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
    const {data: shows, isLoading, error} = useShows()

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
