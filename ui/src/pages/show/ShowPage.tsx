import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'
import { useShow, useEpisodes, useMediaDownloadsView } from '../../lib/queries'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import EpisodeCard, {groupDownloadsByEpisodeSlug} from '../../components/Episode/EpisodeCard'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)


export default function ShowPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const PAGE_SIZE = 25

  const { data: show, isLoading, error } = useShow(id)
  const { data: episodesData } = useEpisodes(id)
  const episodes: any[] = episodesData ?? []
  const { data: downloads } = useMediaDownloadsView()
  const downloadsBySlug = useMemo(() => groupDownloadsByEpisodeSlug(downloads), [downloads])
  const [confirm, setConfirm] = useState(false)

  // Lazily reveal more episodes as the user scrolls, instead of paginating with buttons.
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  useEffect(() => {
    setVisibleCount(PAGE_SIZE)
  }, [id])

  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = sentinelRef.current
    if (!node) return
    const observer = new IntersectionObserver(
        (entries) => {
          if (entries[0]?.isIntersecting) {
            setVisibleCount((c) => Math.min(c + PAGE_SIZE, episodes.length))
          }
        },
        {rootMargin: '600px'},
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [episodes.length])

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
  const visibleItems = episodes.slice(0, visibleCount)
  const hasMore = visibleCount < total

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
          <div className="show-author">{show.authorName}</div>
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

        <div className="episodes-grid" role="list" aria-label={`${show.title} episodes`}>
          {visibleItems.map((ep: any) => (
            <EpisodeCard key={ep.id} ep={ep} showSlug={id} downloads={downloadsBySlug.get(ep.slug)}/>
          ))}
        </div>

        {hasMore && (
          <div ref={sentinelRef} className="episodes-load-more" aria-hidden>
            Loading more episodes…
          </div>
        )}
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
    </section>
  )
}
