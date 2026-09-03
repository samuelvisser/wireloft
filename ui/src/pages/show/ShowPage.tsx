import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'
import { useDownloadProfilesView, useEpisodes, useMediaDownloadsView, useShow, useStreamProfilesView } from '../../lib/queries'
import { waitForMetadataRefreshCompletion } from '../../lib/metadataRefresh'
import { waitForShowRedownloadCompletion } from '../../lib/showRedownload'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import EpisodeCard, {groupDownloadsByEpisodeSlug} from '../../components/Episode/EpisodeCard'
import ActionMenu from '../../components/ActionMenu/ActionMenu'
import ShowIndexingProgress from '../../components/ShowIndexingProgress/ShowIndexingProgress'
import ShowSyncLogModal from '../../components/ShowSyncLogModal/ShowSyncLogModal'
import {PreferredFormatReg} from '../../types/local_media_profile'
import {loadEpisodesFromStorage, removeEpisodesFromStorage, saveEpisodesToStorage} from '../../lib/cache'
import './ShowPage.css'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)

function preferredFormatLabel(value?: string | null) {
  if (!value) return 'Unknown'
  const label = PreferredFormatReg.getLabelLoose(value)
  return label === 'Audio Only' ? 'Audio' : label
}

type ManualSyncLogEntry = {
  synced_at: string
  episodes_found: number
  status?: 'completed' | 'failed'
  manual_request_id?: string
  will_retry?: boolean
}

const EPISODE_SKELETON_COUNT = 12
const MANUAL_SYNC_POLL_INTERVAL_MS = 2000

export default function ShowPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const PAGE_SIZE = 25

  const { data: show, isLoading, error } = useShow(id)
  const {
    data: episodesData,
    isLoading: episodesLoading,
    isPlaceholderData: episodesPlaceholder,
  } = useEpisodes(id)
  const cachedEpisodes = useMemo(() => loadEpisodesFromStorage(id), [id])
  const hasCachedEpisodes = cachedEpisodes !== undefined
  const episodes: any[] = episodesPlaceholder
    ? (cachedEpisodes ?? [])
    : (episodesData ?? cachedEpisodes ?? [])
  const episodesInitialLoading = !hasCachedEpisodes && (episodesLoading || episodesPlaceholder)
  const { data: downloads } = useMediaDownloadsView()
  const { data: downloadProfiles } = useDownloadProfilesView()
  const { data: streamProfiles } = useStreamProfilesView()
  const downloadsBySlug = useMemo(() => groupDownloadsByEpisodeSlug(downloads), [downloads])
  const [confirm, setConfirm] = useState(false)
  const [metadataRefreshConfirm, setMetadataRefreshConfirm] = useState(false)
  const [metadataRefreshStarting, setMetadataRefreshStarting] = useState(false)
  const [redownloadConfirm, setRedownloadConfirm] = useState(false)
  const [redownloadStarting, setRedownloadStarting] = useState(false)
  const [redownloadProfileId, setRedownloadProfileId] = useState('')
  const [redownloadRequestId, setRedownloadRequestId] = useState<string | null>(null)
  const [syncLogOpen, setSyncLogOpen] = useState(false)
  const [manualSyncRequestId, setManualSyncRequestId] = useState<string | null>(null)
  const [copiedStreamProfileId, setCopiedStreamProfileId] = useState<number | null>(null)
  const manualSyncing = manualSyncRequestId !== null

  useEffect(() => {
    if (!id || episodesPlaceholder || episodesData === undefined) return
    saveEpisodesToStorage(id, episodesData)
  }, [episodesData, episodesPlaceholder, id])

  useEffect(() => {
    if (!id || !manualSyncRequestId) return

    let cancelled = false
    const apiBase = (window as any).appConfig?.API_URL || '/api'

    const pollForCompletion = async () => {
      try {
        const response = await fetch(`${apiBase}/shows/${encodeURIComponent(id)}/sync-log`, {
          credentials: 'include',
        })
        if (!response.ok) return

        const entries: ManualSyncLogEntry[] = await response.json()
        const requestEntries = entries.filter((entry) => entry.manual_request_id === manualSyncRequestId)
        if (cancelled) return

        const completedEntry = requestEntries.find((entry) => entry.status === 'completed')
        if (completedEntry) {
          setManualSyncRequestId(null)
          const episodesFound = Number.isFinite(completedEntry.episodes_found)
            ? completedEntry.episodes_found
            : 0
          toast.success(
            `Sync finished for ${show?.title ?? id}: ${episodesFound} new ${episodesFound === 1 ? 'episode' : 'episodes'} found`,
            { duration: 5000 },
          )
          void qc.invalidateQueries({ queryKey: ['episodes', id] })
          return
        }

        const terminalFailure = requestEntries.find(
          (entry) => entry.status === 'failed' && entry.will_retry === false,
        )
        if (terminalFailure) {
          setManualSyncRequestId(null)
          toast.error(`Sync failed for ${show?.title ?? id}`)
        }
      } catch {
        // Keep polling through transient errors; the completion entry is durable in the sync log.
      }
    }

    void pollForCompletion()
    const timer = window.setInterval(() => {
      void pollForCompletion()
    }, MANUAL_SYNC_POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [id, manualSyncRequestId, qc, show?.title])

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

  const syncNow = async () => {
    if (manualSyncRequestId) {
      toast(`A sync is already in progress for ${show.title}`)
      return
    }

    try {
      const base = (window as any).appConfig?.API_URL || '/api'
      const response = await fetch(`${base}/shows/${encodeURIComponent(id)}/sync`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const result = await response.json()
      if (typeof result?.request_id !== 'string' || !result.request_id) {
        throw new Error('Sync request did not return a request ID')
      }

      setManualSyncRequestId(result.request_id)
      toast.success(`Sync started for ${show.title}`)
    } catch {
      toast.error(`Could not start sync for ${show.title}`)
    }
  }

  const refreshAllMetadata = async () => {
    if (metadataRefreshStarting) return

    setMetadataRefreshStarting(true)
    try {
      const base = (window as any).appConfig?.API_URL || '/api'
      const response = await fetch(`${base}/shows/${encodeURIComponent(id)}/refresh-metadata`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const result = await response.json()
      const count = typeof result?.episodes_queued === 'number' ? result.episodes_queued : total
      if (typeof result?.request_id !== 'string' || !result.request_id) {
        throw new Error('Metadata refresh request did not return a request ID')
      }

      setMetadataRefreshConfirm(false)
      if (count === 0) {
        toast(`There are no episodes to refresh for ${show.title}`)
        return
      }

      toast.success(
        `Metadata refresh started for ${count} ${count === 1 ? 'episode' : 'episodes'} in ${show.title}`,
      )

      try {
        await waitForMetadataRefreshCompletion(result.request_id, count)
        toast.success(
          `Metadata refresh completed for ${count} ${count === 1 ? 'episode' : 'episodes'} in ${show.title}`,
          { duration: 5000 },
        )
        await qc.invalidateQueries({ queryKey: ['episodes', id] })
      } catch {
        toast.error(`Metadata refresh failed for ${show.title}`)
      }
    } catch {
      toast.error(`Could not start metadata refresh for ${show.title}`)
    } finally {
      setMetadataRefreshStarting(false)
    }
  }

  const openRedownloadConfirm = () => {
    if (!attachedDownloadProfiles.length) {
      toast(`There are no Download Profiles attached to ${show.title}`)
      return
    }
    setRedownloadProfileId(
      attachedDownloadProfiles.length > 1 ? 'all' : String(attachedDownloadProfiles[0].id),
    )
    setRedownloadConfirm(true)
  }

  const redownloadAllEpisodes = async () => {
    if (redownloadStarting || redownloadRequestId || !redownloadProfileId) return

    setRedownloadStarting(true)
    try {
      const base = (window as any).appConfig?.API_URL || '/api'
      const response = await fetch(`${base}/shows/${encodeURIComponent(id)}/redownload-episodes`, {
        method: 'POST',
        credentials: 'include',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          downloadProfileId: redownloadProfileId === 'all' ? null : Number(redownloadProfileId),
        }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const result = await response.json()
      if (typeof result?.request_id !== 'string' || !result.request_id) {
        throw new Error('Re-download request did not return a request ID')
      }

      const profileCount = typeof result?.download_profiles_queued === 'number'
        ? result.download_profiles_queued
        : (redownloadProfileId === 'all' ? attachedDownloadProfiles.length : 1)
      setRedownloadConfirm(false)
      setRedownloadRequestId(result.request_id)
      toast.success(
        `Re-download started for ${show.title} using ${profileCount} ${profileCount === 1 ? 'Download Profile' : 'Download Profiles'}`,
      )

      void waitForShowRedownloadCompletion(result.request_id)
        .then(async () => {
          setRedownloadRequestId(null)
          toast.success(`All selected episode files for ${show.title} were re-downloaded`, {duration: 5000})
          await Promise.all([
            qc.invalidateQueries({queryKey: ['mediaDownloadsView']}),
            qc.invalidateQueries({queryKey: ['episodes', id]}),
          ])
        })
        .catch(() => {
          setRedownloadRequestId(null)
          toast.error(`Re-download failed for ${show.title}`)
        })
    } catch {
      toast.error(`Could not start re-download for ${show.title}`)
    } finally {
      setRedownloadStarting(false)
    }
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
    // Success: close modal, invalidate relevant queries, clear persisted episode data, and return to the shows library.
    removeEpisodesFromStorage(id)
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
                  label: 'Sync now',
                  icon: ['fas', 'arrows-rotate'],
                  onSelect: () => void syncNow(),
                },
                {
                  label: 'Sync log',
                  icon: ['fas', 'clock-rotate-left'],
                  onSelect: () => setSyncLogOpen(true),
                },
                {
                  label: 'Refresh all metadata',
                  icon: ['fas', 'arrows-rotate'],
                  onSelect: () => setMetadataRefreshConfirm(true),
                },
                {
                  label: 'Delete and re-download all episodes',
                  icon: ['fas', 'arrows-rotate'],
                  tone: 'danger',
                  disabled: attachedDownloadProfiles.length === 0 || redownloadRequestId !== null,
                  onSelect: openRedownloadConfirm,
                },
                {
                  label: 'Create download profile',
                  icon: ['fas', 'download'],
                  separatorBefore: true,
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

        {episodesInitialLoading && episodes.length === 0 ? (
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

        {hasMore && !episodesInitialLoading && (
          <div ref={sentinelRef} className="episodes-load-more" aria-hidden>
            Loading more episodes…
          </div>
        )}
      </article>

      <ShowSyncLogModal
        showSlug={id}
        showTitle={show.title}
        open={syncLogOpen}
        syncing={manualSyncing}
        onClose={() => setSyncLogOpen(false)}
        onSyncNow={syncNow}
      />

      {metadataRefreshConfirm && (
        <div
          className="modal-overlay"
          role="presentation"
          onClick={() => {
            if (!metadataRefreshStarting) setMetadataRefreshConfirm(false)
          }}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="refresh-metadata-title"
            aria-describedby="refresh-metadata-desc"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div className="modal-icon" aria-hidden>
                <FontAwesomeIcon icon={['fas', 'arrows-rotate']} />
              </div>
              <h2 id="refresh-metadata-title" className="modal-title">Refresh all metadata</h2>
            </div>
            <p id="refresh-metadata-desc" className="modal-text">
              Refresh metadata for every episode in "{show.title}"? This can take a while and is usually not needed.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn"
                disabled={metadataRefreshStarting}
                onClick={() => setMetadataRefreshConfirm(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={metadataRefreshStarting}
                onClick={() => void refreshAllMetadata()}
              >
                {metadataRefreshStarting ? 'Starting…' : 'Refresh metadata'}
              </button>
            </div>
          </div>
        </div>
      )}

      {redownloadConfirm && (
        <div
          className="modal-overlay"
          role="presentation"
          onClick={() => {
            if (!redownloadStarting) setRedownloadConfirm(false)
          }}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="redownload-title"
            aria-describedby="redownload-desc"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div className="modal-icon danger" aria-hidden>
                <FontAwesomeIcon icon={['fas', 'arrows-rotate']} />
              </div>
              <h2 id="redownload-title" className="modal-title">Delete and re-download all episodes</h2>
            </div>
            <p id="redownload-desc" className="modal-text">
              This deletes the existing episode files selected below and downloads them again. This can take a long time, use significant bandwidth, and is usually not needed.
            </p>
            <div className="form-row">
              <label htmlFor="redownload-profile">Download Profile</label>
              <select
                id="redownload-profile"
                className="input"
                value={redownloadProfileId}
                disabled={redownloadStarting}
                onChange={(event) => setRedownloadProfileId(event.target.value)}
              >
                {attachedDownloadProfiles.length > 1 && (
                  <option value="all">All Download Profiles</option>
                )}
                {attachedDownloadProfiles.map((profile) => (
                  <option key={profile.id} value={String(profile.id)}>
                    {`${profile.type === 'series' ? 'Series' : 'Podcast'} · ${preferredFormatLabel(profile.localMediaProfilePreferredFormat)} · Profile #${profile.id}`}
                  </option>
                ))}
              </select>
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="btn"
                disabled={redownloadStarting}
                onClick={() => setRedownloadConfirm(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={redownloadStarting || !redownloadProfileId}
                onClick={() => void redownloadAllEpisodes()}
              >
                {redownloadStarting ? 'Starting…' : 'Delete and re-download'}
              </button>
            </div>
          </div>
        </div>
      )}

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
