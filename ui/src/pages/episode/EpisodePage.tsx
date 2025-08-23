import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'
import { useShow } from '../../lib/queries'
import type { Episode } from '../../domain/show'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)

// Types centralized in domain module

function formatDate(d: Date | null | undefined) {
  if (!d) return '—'
  try {
    return new Intl.DateTimeFormat(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(d)
  } catch {
    return d?.toString() ?? ''
  }
}

export default function EpisodePage() {
  const { id: showId, episodeId } = useParams()

  const { data: show, isLoading, error } = useShow(showId)

  const episode = useMemo(() => show?.episodes.find((e: Episode) => e.id === episodeId), [show, episodeId])

  if (!showId) {
    return (
      <section className="view episode-view">
        <div className="view-header">
          <h1>Episode</h1>
        </div>
        <p>Show not found.</p>
        <p><Link to="/">Go home</Link></p>
      </section>
    )
  }

  if (isLoading && !show) {
    return (
      <section className="view episode-view">
        <div className="view-header">
          <h1>Episode</h1>
        </div>
        <p>Loading episode...</p>
      </section>
    )
  }

  if (!show) {
    return (
      <section className="view episode-view">
        <div className="view-header">
          <h1>Episode</h1>
        </div>
        <p>{(error as any)?.message ?? 'Show not found.'}</p>
        <p><Link to="/">Go home</Link></p>
      </section>
    )
  }

  if (!episode) {
    return (
      <section className="view episode-view">
        <div className="view-header">
          <h1>Episode</h1>
        </div>
        <p>Episode not found.</p>
        <p><Link to={`/show/${showId}`}>Back to show</Link></p>
      </section>
    )
  }

  // Mock dates based on index (UI only)
  const releaseDate = new Date(Date.now() - episode.index * 24 * 60 * 60 * 1000)
  const downloadDate = episode.status === 'downloaded' ? new Date(releaseDate.getTime() + 6 * 60 * 60 * 1000) : null

  const statusLabel =
    episode.status === 'downloaded'
      ? 'Downloaded'
      : episode.status === 'downloading'
      ? 'Downloading'
      : episode.status === 'processing'
      ? 'Waiting for processing'
      : 'Error'

  // Placeholder cover image
  const coverUrl = episode.cover || `https://placehold.co/640x360/png?text=Episode+%23${episode.index}`

  return (
    <section className="view episode-view" aria-labelledby="episode-title">
      <div className="view-header">
        <h1 id="episode-title">Episode</h1>
      </div>

      <article className="episode-details" aria-label="Episode details">
        <header className="episode-header">
          <div className="episode-show"><Link to={`/show/${showId}`}>{show.title}</Link></div>
          <div className="episode-title-text">{episode.title}</div>
        </header>

        <div className="episode-content">
          <div className="episode-cover">
            <img src={coverUrl} alt="Episode cover" />
          </div>
          <div className="episode-meta">
            <table className="meta-table">
              <tbody>
                <tr>
                  <th scope="row">Title</th>
                  <td>{episode.title}</td>
                </tr>
                <tr>
                  <th scope="row">Status</th>
                  <td>{statusLabel}</td>
                </tr>
                <tr>
                  <th scope="row">Release date</th>
                  <td>{formatDate(releaseDate)}</td>
                </tr>
                <tr>
                  <th scope="row">Download date</th>
                  <td>{formatDate(downloadDate)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </article>

      <style>{`
        .episode-header { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
        .episode-title-text { font-size: 1.1rem; font-weight: 600; }
        .episode-content { display: grid; grid-template-columns: minmax(280px, 480px) 1fr; gap: 16px; align-items: start; }
        .episode-cover img { width: 100%; height: auto; border-radius: 8px; border: 1px solid var(--border-color, #ddd); }
        .meta-table { width: 100%; border-collapse: collapse; }
        .meta-table th, .meta-table td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border-color, #e2e2e2); vertical-align: top; }
        .meta-table th { width: 180px; color: var(--muted-fg, #555); font-weight: 500; }
        @media (max-width: 720px) {
          .episode-content { grid-template-columns: 1fr; }
        }
      `}</style>
    </section>
  )
}
