import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'
import { useDownloadProfilesView, useEpisodes, useMediaDownloadsView, useShow, useStreamProfilesView } from '../../lib/queries'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import EpisodeCard, {groupDownloadsByEpisodeSlug} from '../../components/Episode/EpisodeCard'
import ActionMenu from '../../components/ActionMenu/ActionMenu'
import ShowIndexingProgress from '../../components/ShowIndexingProgress/ShowIndexingProgress'
import {PreferredFormatReg} from '../../types/local_media_profile'
import './ShowPage.css'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)

function preferredFormatLabel(value?: string | null) {
  if (!value) return 'Unknown'
  const label = PreferredFormatReg.getLabelLoose(value)
  return label === 'Audio Only' ? 'Audio' : label
}

const EPISODE_SKELETON_COUNT = 12

export default function ShowPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const PAGE_SIZE = 25

  const { data: show, isLoading, error } = useShow(id)
  const { data: episodesData, isLoading: episodesLoading } = useEpisodes(id)
  const episodes: any[] = episodesData ?? []
  const { data: downloads } = useMediaDownloadsView()
  const { data: downloadProfiles } = useDownloadProfilesView()
  const { data: streamProfiles } = useStreamProfilesView()
  const downloadsBySlug = useMemo(() => groupDownloadsByEpisodeSlug(downloads), [downloads])
  const [confirm, setConfirm] = useState(false)
  const [copiedStreamProfileId, setCopiedStreamProfileId] = useState<number | null>(null)

  const attachedDownloadProfiles = useMemo(
    () => (downloadProfiles ?? []).filter((profile) => profile.showSlug === id),
    [downloadProfiles, id],
  )
  const attachedStreamProfiles = useMemo(
    () => (streamProfiles ?? []).filter((profile) => profile.showSlug === id),
    [streamProfiles, id],
  )

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

  const copyFeedUrl = async (profileId: number, feedUrl?: string) => {
    if (!feedUrl) return
    try {
      await navigator.clipboard.writeText(feedUrl)
      setCopiedStreamProfileId(profileId)
      window.setTimeout(() => setCopiedStreamProfileId((current) => current === profileId ? null : current), 1800)
    } catch {
      toast.error('Could not copy the RSS URL')
    }
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
    // Success: close modal, invalidate relevant queries, and return to the shows library.
    setConfirm(false)
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['shows'] }),
      qc.invalidateQueries({ queryKey: ['showsView'] }),
      qc.invalidateQueries({ queryKey: ['show', id] }),
      qc.invalidateQueries({ queryKey: ['episodes', id] }),
    ])
    navigate('/library?type=shows')
  }

  return (
    <section className="view show-view" aria-labelledby="show-title">
      <div className="view-header">
        <h1 id="show-title">{show.title}</h1>
      </div>

      <article className="show-details" aria-label="Show details">
        <header className="show-page-header">
          <div className="show-page-heading">
            <div className="show-author">{show.authorName}</div>
            <div className="show-meta">
              {total} episodes{show.years ? ` • ${show.years}` : ''}
            </div>
          </div>

          <div className="show-page-actions">
            <button type="button" className="btn" title="Edit show" onClick={onEdit}>
              <FontAwesomeIcon icon={['fas', 'pen-to-square'] as any} aria-hidden="true"/>
              <span>Edit</span>
            </button>
            <button type="button" className="btn btn-danger" onClick={onDelete}>
              <FontAwesomeIcon icon={['fas', 'trash'] as any} aria-hidden="true"/>
              <span>Delete</span>
            </button>
            <ActionMenu
              items={[
                {
                  label: 'Create download profile',
                  icon: ['fas', 'download'],
                  onSelect: () => navigate(`/add-download-profile?show=${encodeURIComponent(id)}`),
                },
                {
                  label: 'Create stream profile',
                  icon: ['fas', 'rss'],
                  onSelect: () => navigate(`/add-stream-profile?show=${encodeURIComponent(id)}`),
                },
              ]}
            />
          </div>

          <ShowIndexingProgress
            showId={show.id}
            showSlug={show.slug}
            pollForStart={episodes.length === 0}
            className="show-page-indexing"
          />

          {(attachedDownloadProfiles.length > 0 || attachedStreamProfiles.length > 0) && (
            <div className="show-profile-summary" aria-label="Profiles attached to this show">
              {attachedDownloadProfiles.length > 0 && (
                <div className="show-profile-group">
                  <div className="show-profile-group-label">
                    <FontAwesomeIcon icon={['fas', 'download'] as any} aria-hidden="true"/>
                    <span>Download {attachedDownloadProfiles.length === 1 ? 'profile' : 'profiles'}</span>
                  </div>
                  <div className="show-profile-links">
                    {attachedDownloadProfiles.map((profile) => (
                      <button
                        key={`${profile.type}-${profile.id}`}
                        type="button"
                        className="show-profile-chip"
                        onClick={() => navigate(`/edit-download-profile/${profile.type}/${profile.id}`, {state: profile})}
                        title={`Open ${preferredFormatLabel(profile.localMediaProfilePreferredFormat)} download profile`}
                      >
                        <span>{preferredFormatLabel(profile.localMediaProfilePreferredFormat)}</span>
                        <FontAwesomeIcon icon={['fas', 'arrow-up-right-from-square'] as any} aria-hidden="true"/>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {attachedStreamProfiles.length > 0 && (
                <div className="show-profile-group">
                  <div className="show-profile-group-label">
                    <FontAwesomeIcon icon={['fas', 'rss'] as any} aria-hidden="true"/>
                    <span>Stream {attachedStreamProfiles.length === 1 ? 'profile' : 'profiles'}</span>
                  </div>
                  <div className="show-profile-links">
                    {attachedStreamProfiles.map((profile) => {
                      const feedUrl = profile.type === 'rss' ? profile.streamProfileImpl?.feedUrl : undefined
                      const copied = copiedStreamProfileId === profile.id
                      const label = `${profile.type.toUpperCase()} ${preferredFormatLabel(profile.preferredFormat)}`
                      return (
                        <div key={`${profile.type}-${profile.id}`} className="show-profile-chip-group">
                          <button
                            type="button"
                            className="show-profile-chip show-profile-chip-main"
                            onClick={() => navigate(`/edit-stream-profile/${profile.type}/${profile.id}`, {state: profile})}
                            title={`Open ${label} stream profile`}
                          >
                            <span>{label}</span>
                            <FontAwesomeIcon icon={['fas', 'arrow-up-right-from-square'] as any} aria-hidden="true"/>
                          </button>
                          {profile.type === 'rss' && feedUrl && (
                            <button
                              type="button"
                              className="show-profile-copy"
                              onClick={() => copyFeedUrl(profile.id, feedUrl)}
                              aria-label={copied ? 'RSS URL copied' : 'Copy RSS URL'}
                              title={copied ? 'Copied!' : 'Copy RSS URL'}
                            >
                              <FontAwesomeIcon icon={['fas', copied ? 'check' : 'copy'] as any} aria-hidden="true"/>
                            </button>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </header>

        {episodesLoading && episodes.length === 0 ? (
          <div className="episodes-grid" role="status" aria-label="Loading episodes" aria-busy="true">
            {Array.from({length: EPISODE_SKELETON_COUNT}, (_, index) => (
              <div className="episode-card episode-card-skeleton" key={index} aria-hidden="true">
                <div className="episode-skeleton-cover"/>
                <div className="episode-skeleton-title"/>
                <div className="episode-skeleton-title episode-skeleton-title-short"/>
              </div>
            ))}
          </div>
        ) : (
          <div className="episodes-grid" role="list" aria-label={`${show.title} episodes`}>
            {visibleItems.map((ep: any) => (
              <EpisodeCard key={ep.id} ep={ep} showSlug={id} downloads={downloadsBySlug.get(ep.slug)}/>
            ))}
          </div>
        )}

        {hasMore && !episodesLoading && (
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
