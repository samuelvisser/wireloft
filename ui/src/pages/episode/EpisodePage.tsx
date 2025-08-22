import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)

// Local mock types, aligned with ShowPage.tsx
export type EpisodeStatus = 'downloaded' | 'downloading' | 'processing' | 'error'

export type Episode = {
  id: string
  title: string
  index: number
  cover?: string
  status: EpisodeStatus
}

export type Show = {
  id: string
  author: string
  title: string
  years?: string
  episodes: Episode[]
}

function randomEpisodeTitle(showTitle: string, i: number): string {
  const topics = [
    'free speech',
    'AI and the future',
    'parenting',
    'college campuses',
    'elections',
    'the economy',
    'culture wars',
    'movies and media',
    'sports',
    'education',
    'technology',
    'faith and culture',
  ]
  const t = topics[Math.floor(Math.random() * topics.length)]
  const n = i + 1
  const patterns = [
    `${showTitle} — Quick Take on ${t}`,
    `${showTitle}: Full Episode #${n} — ${t} Explained in Depth With Examples and Context`,
    `${showTitle} Clip: ${t} in 60 Seconds`,
    `${showTitle} — ${t} | Highlights and Reactions`,
    `${showTitle} (Ep ${n}): ${t}, Mailbag, and More`,
    `${showTitle}: ${t} — What You Need To Know Right Now`,
    `${showTitle} — ${t} and Why It Matters More Than You Think in 2025`,
  ]
  return patterns[Math.floor(Math.random() * patterns.length)]
}

function makeShow(showId: string): Show | null {
  // Simple demo data aligned with Home.tsx IDs
  const map: Record<string, { author: string; title: string; years?: string; count: number }> = {
    'the-ben-shapiro-show': { author: 'Ben Shapiro', title: 'The Ben Shapiro Show', years: '2015-2025', count: 30 },
    'the-matt-walsh-show': { author: 'Matt Walsh', title: 'The Matt Walsh Show', years: '2018 – 2025', count: 20 },
    'ben-after-dark': { author: 'Ben Shapiro', title: 'Ben After Dark', years: '2025 - 2025', count: 7 },
  }
  const base = map[showId]
  if (!base) return null

  // Build episodes list for the show
  const statuses: EpisodeStatus[] = ['downloaded', 'downloading', 'processing', 'error']
  const episodes: Episode[] = Array.from({ length: base.count }, (_, i) => {
    const status = statuses[i % statuses.length]
    return {
      id: `${showId}-${i + 1}`,
      title: randomEpisodeTitle(base.title, i),
      index: i + 1,
      status,
      cover: undefined,
    }
  })

  return {
    id: showId,
    author: base.author,
    title: base.title,
    years: base.years,
    episodes,
  }
}

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
    return d.toLocaleString()
  }
}

export default function EpisodePage() {
  const { id: showId, episodeId } = useParams()

  const show = useMemo(() => (showId ? makeShow(showId) : null), [showId])
  const episode = useMemo(() => show?.episodes.find((e) => e.id === episodeId), [show, episodeId])

  if (!showId || !show) {
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

  // Mock dates based on index
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
