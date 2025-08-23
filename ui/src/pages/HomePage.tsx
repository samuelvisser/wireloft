import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'
import { Link, useNavigate } from 'react-router-dom'
import React from 'react'
import { useShows } from '../lib/queries'
import type { Episode } from '../domain/show'
import { statusIcon, statusLabel } from '../utils/showStatus'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)

function EpisodeCard({ ep, showId }: { ep: Episode; showId: string }) {
  const initials = ep.title
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 3)
    .toUpperCase()
  const style = ep.cover ? { backgroundImage: `url(${ep.cover})` } : undefined
  const icon = statusIcon(ep.status)
  const label = statusLabel(ep.status)
  const isProcessing = ep.status === 'processing'

  const navigate = useNavigate()
  const goToEpisode = () => navigate(`/show/${showId}/episode/${ep.id}`)
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
        <span className={`status status-${ep.status}`} aria-label={label} title={label}>
          <FontAwesomeIcon icon={icon as any} spin={isProcessing} />
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

export default function HomePage({ onAddShow }: { onAddShow: () => void }) {
  const { data: shows, isLoading, error } = useShows()

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
          <article className="show-section" key={show.id} aria-labelledby={`${show.id}-title`}>
            <Link to={`/show/${show.id}`} className="show-header" aria-labelledby={`${show.id}-title`}>
              <div className="show-author">{show.author}</div>
              <h2 id={`${show.id}-title`} className="show-title">
                {show.title}
              </h2>
              <div className="show-meta">
                {show.episodes.length} episodes{show.years ? ` • ${show.years}` : ''}
              </div>
            </Link>
            <div className="episodes-row" role="list" aria-label={`${show.title} episodes`}>
              {show.episodes.map((ep: Episode) => (
                <EpisodeCard key={ep.id} ep={ep} showId={show.id} />
              ))}
            </div>
          </article>
        ))
      )}
    </section>
  )
}
