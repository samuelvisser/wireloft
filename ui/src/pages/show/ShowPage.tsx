import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'
import { useShow, useEpisodes } from '../../lib/queries'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import {statusIcon, statusLabel} from '../../utils/showStatus'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)


export default function ShowPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const pageSize = 25

  const { data: show, isLoading, error } = useShow(id)
  const { data: episodesData } = useEpisodes(id)
  const episodes: any[] = episodesData ?? []
  const [confirm, setConfirm] = useState(false)

  if (!id) {
    return (
      <section className="view show-view">
        <div className="view-header">
          <h1>Show</h1>
        </div>
        <p>Show not found.</p>
      </section>
    )
  }

  if (isLoading && !show) {
    return (
      <section className="view show-view">
        <div className="view-header">
          <h1>Show</h1>
        </div>
        <p>Loading show...</p>
      </section>
    )
  }

  if (!show) {
    return (
      <section className="view show-view">
        <div className="view-header">
          <h1>Show</h1>
        </div>
        <p>{(error as any)?.message ?? 'Show not found.'}</p>
      </section>
    )
  }

  const total = episodes.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const currentPage = Math.min(page, totalPages)
  const start = (currentPage - 1) * pageSize
  const end = start + pageSize
  const pageItems = episodes.slice(start, end)

  const onDelete = () => setConfirm(true)
  const onEdit = () => {
    navigate(`/edit-show/${id}`)
  }

  const closeConfirm = () => setConfirm(false)
  const onConfirmDelete = async () => {
    if (!id) return
    const url = `${(window as any).appConfig.API_URL}/shows/${id}`
    const r = await fetch(url, { method: 'DELETE', credentials: 'include' })
    if (!r.ok) {
      let friendly = `Failed to delete show (HTTP ${r.status})`
      try {
        const data = await r.json().catch(() => null as any)
        const details: any[] | undefined = data?.detail
        if (Array.isArray(details)) {
          const allErr = details.find((d) => Array.isArray(d?.loc) && d.loc[0] === 'body' && d.loc[1] === '__all__')
          if (allErr) {
            if (typeof allErr.msg === 'string' && allErr.msg.trim()) {
              friendly = allErr.msg
            }
          }
        }
      } catch (_) {
        // ignore JSON parse errors
      }
      console.error(friendly)
      toast.error(friendly)
      // Keep the confirm modal open so the user can retry or cancel
      return
    }
    // Success: close modal, invalidate relevant queries, and navigate home
    setConfirm(false)
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['shows'] }),
      qc.invalidateQueries({ queryKey: ['show', id] }),
      qc.invalidateQueries({ queryKey: ['episodes', id] }),
    ])
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
          {pageItems.map((ep: any) => {
            const icon = statusIcon(ep.unified_status)
            const isProcessing = ep.unified_status === 'dw_processing' || ep.unified_status === 'local_processing'
            const label = statusLabel(ep.unified_status)
            return (
              <div
                key={ep.id}
                className="episode-list-item"
                role="listitem"
                aria-label={ep.title}
                tabIndex={0}
                onClick={() => navigate(`/show/${id}/episode/${ep.slug}`)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    navigate(`/show/${id}/episode/${ep.slug}`)
                  }
                }}
              >
                <div className="episode-thumb" aria-hidden>
                  <div className="thumb-inner">
                    <span className={`status status-${ep.unified_status}`} aria-label={label} title={label}>
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
        .episode-list-item { display: flex; gap: 12px; align-items: center; border: 1px solid var(--border-color, #ddd); border-radius: 8px; padding: 8px; cursor: pointer; }
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
