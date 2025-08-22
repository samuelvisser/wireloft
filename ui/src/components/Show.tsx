import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)

// Local mock types (mirroring Home.tsx for demo purposes)
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

function statusIcon(status: EpisodeStatus) {
  switch (status) {
    case 'downloaded':
      return ['fas', 'circle-check'] as const
    case 'downloading':
      return ['fas', 'arrow-down'] as const
    case 'processing':
      return ['fas', 'spinner'] as const
    case 'error':
      return ['fas', 'circle-exclamation'] as const
  }
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

export default function Show() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const pageSize = 25

  const show = useMemo(() => (id ? makeShow(id) : null), [id])

  if (!id || !show) {
    return (
      <section className="view show-view">
        <div className="view-header">
          <h1>Show</h1>
        </div>
        <p>Show not found.</p>
      </section>
    )
  }

  const total = show.episodes.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const currentPage = Math.min(page, totalPages)
  const start = (currentPage - 1) * pageSize
  const end = start + pageSize
  const pageItems = show.episodes.slice(start, end)

  const onDelete = () => setConfirm(true)
  const onEdit = () => {
    // Edit page intentionally not implemented yet
    alert('Edit show is not implemented yet.')
  }

  const [confirm, setConfirm] = useState(false)
  const closeConfirm = () => setConfirm(false)
  const onConfirmDelete = () => {
    alert(`Delete show:\n${show.title} (${show.id})`)
    setConfirm(false)
    navigate('/')
  }

  return (
    <section className="view show-view" aria-labelledby="show-title">
      <div className="view-header">
        <h1 id="show-title">{show.title}</h1>
      </div>

      <article className="show-details" aria-label="Show details">
        <header className="show-header">
          <div className="show-author">{show.author}</div>
          <div className="show-meta">
            {total} episodes{show.years ? ` • ${show.years}` : ''}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button type="button" className="btn" title="Edit show (not implemented)" onClick={onEdit}>
              Edit
            </button>
            <button type="button" className="btn btn-danger" onClick={onDelete}>
              Delete
            </button>
          </div>
        </header>

        <div className="episodes-list" role="list" aria-label={`${show.title} episodes`}>
          {pageItems.map((ep) => {
            const icon = statusIcon(ep.status)
            const isProcessing = ep.status === 'processing'
            const label =
              ep.status === 'downloaded'
                ? 'Downloaded'
                : ep.status === 'downloading'
                  ? 'Downloading'
                  : ep.status === 'processing'
                    ? 'Waiting for processing'
                    : 'Error'
            return (
              <div key={ep.id} className="episode-list-item" role="listitem" aria-label={ep.title}>
                <div className="episode-thumb" aria-hidden>
                  <div className="thumb-inner">
                    <span className={`status status-${ep.status}`} aria-label={label} title={label}>
                      <FontAwesomeIcon icon={icon as any} spin={isProcessing} />
                    </span>
                    <span className="badge">#{ep.index}</span>
                  </div>
                </div>
                <div className="episode-info">
                  <div className="episode-title" title={ep.title}>{ep.title}</div>
                </div>
              </div>
            )
          })}
        </div>

        <div className="pagination" aria-label="Pagination" style={{ display: 'flex', gap: 8, marginTop: 16, alignItems: 'center' }}>
          <button className="btn" disabled={currentPage <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            Previous
          </button>
          <span>
            Page {currentPage} of {totalPages}
          </span>
          <button className="btn" disabled={currentPage >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
            Next
          </button>
        </div>
      </article>

      {confirm && (
        <div className="modal-overlay" role="presentation" onClick={closeConfirm}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-title"
            aria-describedby="delete-desc"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div className="modal-icon danger" aria-hidden>
                <FontAwesomeIcon icon={['fas', 'trash']} />
              </div>
              <h2 id="delete-title" className="modal-title">Delete show</h2>
            </div>
            <p id="delete-desc" className="modal-text">
              Are you sure you want to delete "{show.title}"? This action cannot be undone.
            </p>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={closeConfirm}>Cancel</button>
              <button type="button" className="btn btn-danger" onClick={onConfirmDelete}>Delete</button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        /* Basic large list thumbnail styling leveraging existing classes */
        .episodes-list { display: flex; flex-direction: column; gap: 12px; margin-top: 16px; }
        .episode-list-item { display: flex; gap: 12px; align-items: center; border: 1px solid var(--border-color, #ddd); border-radius: 8px; padding: 8px; }
        .episode-thumb { width: 120px; height: 68px; border-radius: 6px; background: var(--cover-bg, #222); position: relative; overflow: hidden; flex: 0 0 auto; }
        .episode-thumb .thumb-inner { position: relative; width: 100%; height: 100%; display: flex; align-items: end; justify-content: start; }
        .episode-info { flex: 1 1 auto; min-width: 0; }
        .episode-info .episode-title { font-weight: 600; }
        .badge { position: absolute; top: 6px; right: 6px; background: rgba(0,0,0,0.6); color: #fff; padding: 2px 6px; border-radius: 12px; font-size: 12px; }
        .status { position: absolute; left: 6px; bottom: 6px; color: #fff; background: rgba(0,0,0,0.5); padding: 4px; border-radius: 50%; }
      `}</style>
    </section>
  )
}
