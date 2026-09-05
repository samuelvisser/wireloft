import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'
import { useDownloadProfilesView, useEpisodes, useMediaDownloadsView, useShow, useShowSeasons, useStreamProfilesView } from '../../lib/queries'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import EpisodeCard, {groupDownloadsByEpisodeSlug} from '../../components/Episode/EpisodeCard'
import ActionMenu from '../../components/ActionMenu/ActionMenu'
import {useActiveOperation} from '../../components/OperationNotifier/OperationNotifier'
import ShowIndexingProgress from '../../components/ShowIndexingProgress/ShowIndexingProgress'
import ShowSyncLogModal from '../../components/ShowSyncLogModal/ShowSyncLogModal'
import {OperationControlError, type OperationControlAction, useControlOperation} from '../../lib/operations'
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

const EPISODE_SKELETON_COUNT = 12
const OPERATION_WAITING_MESSAGE = 'Operation is waiting, it should resume soon.'

export default function ShowPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const controlOperation = useControlOperation()
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
  const isSeries = show?.type === 'series'
  const {
    data: seasonsData,
    isLoading: seasonsLoading,
    isPlaceholderData: seasonsPlaceholder,
  } = useShowSeasons(isSeries ? id : undefined)
  const seasons = useMemo(() => {
    if (seasonsPlaceholder) return []
    return [...(seasonsData ?? [])].sort((a, b) => b.index - a.index)
  }, [seasonsData, seasonsPlaceholder])
  const { data: downloads } = useMediaDownloadsView()
  const {
    data: downloadProfiles,
    isLoading: downloadProfilesLoading,
    error: downloadProfilesError,
  } = useDownloadProfilesView()
  const { data: streamProfiles } = useStreamProfilesView()
  const downloadsBySlug = useMemo(() => groupDownloadsByEpisodeSlug(downloads), [downloads])
  const [confirm, setConfirm] = useState(false)
  const [syncStarting, setSyncStarting] = useState(false)
  const [metadataRefreshConfirm, setMetadataRefreshConfirm] = useState(false)
  const [metadataRefreshStarting, setMetadataRefreshStarting] = useState(false)
  const [redownloadConfirm, setRedownloadConfirm] = useState(false)
  const [redownloadStarting, setRedownloadStarting] = useState(false)
  const [redownloadProfileId, setRedownloadProfileId] = useState('')
  const [syncLogOpen, setSyncLogOpen] = useState(false)
  const [copiedStreamProfileId, setCopiedStreamProfileId] = useState<number | null>(null)
  const [selectedSeasonId, setSelectedSeasonId] = useState<number | null>(null)
  const [operationControlBusy, setOperationControlBusy] = useState<string | null>(null)

  const operationResourceId = show?.id ?? null
  const syncOperation = useActiveOperation('show.sync', 'show', operationResourceId)
  const metadataRefreshOperation = useActiveOperation('show.refresh_metadata', 'show', operationResourceId)
  const redownloadOperation = useActiveOperation('show.redownload_episodes', 'show', operationResourceId)
  const manualSyncing = syncOperation !== undefined
  const syncBusy = syncStarting || manualSyncing
  const metadataRefreshBusy = metadataRefreshStarting || metadataRefreshOperation !== undefined
  const redownloadBusy = redownloadStarting || redownloadOperation !== undefined

  useEffect(() => {
    if (!id || episodesPlaceholder || episodesData === undefined) return
    saveEpisodesToStorage(id, episodesData)
  }, [episodesData, episodesPlaceholder, id])

  useEffect(() => {
    if (!isSeries || seasons.length === 0) {
      setSelectedSeasonId(null)
      return
    }

    setSelectedSeasonId((current) => {
      if (current !== null && seasons.some((season) => season.id === current)) return current
      return seasons[0].id
    })
  }, [isSeries, seasons])

  const attachedDownloadProfiles = useMemo(
    () => (downloadProfiles ?? []).filter((profile) => profile.showSlug === id),
    [downloadProfiles, id],
  )
  const attachedStreamProfiles = useMemo(
    () => (streamProfiles ?? []).filter((profile) => profile.showSlug === id),
    [streamProfiles, id],
  )
  const displayedEpisodes = useMemo(() => {
    if (!isSeries) return episodes
    if (selectedSeasonId === null) return []
    return episodes.filter((episode) => episode.seasonId === selectedSeasonId)
  }, [episodes, isSeries, selectedSeasonId])
  const seasonViewLoading = Boolean(
    isSeries && (
      seasonsLoading
      || seasonsPlaceholder
      || (seasons.length > 0 && selectedSeasonId === null)
    )
  )

  // Lazily reveal more episodes as the user scrolls, instead of paginating with buttons.
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  useEffect(() => {
    setVisibleCount(PAGE_SIZE)
  }, [id, selectedSeasonId])

  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = sentinelRef.current
    if (!node) return
    const observer = new IntersectionObserver(
        (entries) => {
          if (entries[0]?.isIntersecting) {
            setVisibleCount((c) => Math.min(c + PAGE_SIZE, displayedEpisodes.length))
          }
        },
        {rootMargin: '600px'},
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [displayedEpisodes.length])

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
  const visibleItems = displayedEpisodes.slice(0, visibleCount)
  const hasMore = visibleCount < displayedEpisodes.length
  const episodesViewLoading = episodesInitialLoading || seasonViewLoading

  const syncDisabledReason = syncStarting
    ? `WireLoft is starting a sync for ${show.title}.`
    : syncOperation
      ? syncOperation.status === 'WAITING'
        ? syncOperation.message || OPERATION_WAITING_MESSAGE
        : `A sync is running for ${show.title}.`
      : undefined
  const metadataRefreshDisabledReason = metadataRefreshStarting
    ? `WireLoft is starting a metadata refresh for ${show.title}.`
    : metadataRefreshOperation
      ? metadataRefreshOperation.status === 'WAITING'
        ? metadataRefreshOperation.message || OPERATION_WAITING_MESSAGE
        : `A metadata refresh is running for ${show.title}.${metadataRefreshOperation.progressTotal > 0
          ? ` ${metadataRefreshOperation.progressCurrent}/${metadataRefreshOperation.progressTotal} episodes have finished.`
          : ''}`
      : undefined
  const downloadProfileStateUnknown = downloadProfilesLoading && downloadProfiles === undefined
  const downloadProfileStateFailed = Boolean(downloadProfilesError) && downloadProfiles === undefined
  const redownloadDisabledReason = redownloadStarting
    ? `WireLoft is starting a delete and re-download operation for ${show.title}.`
    : redownloadOperation
      ? redownloadOperation.status === 'WAITING'
        ? redownloadOperation.message || OPERATION_WAITING_MESSAGE
        : `A delete and re-download operation is running for ${show.title}.`
      : downloadProfileStateUnknown
        ? 'WireLoft is still checking which Download Profiles are attached to this show.'
        : downloadProfileStateFailed
          ? 'WireLoft could not determine which Download Profiles are attached to this show.'
          : attachedDownloadProfiles.length === 0
            ? `No Download Profiles are attached to ${show.title}.`
            : undefined

  const controlTaskOperation = async (
    operationId: string,
    action: OperationControlAction,
    label: string,
  ) => {
    if (operationControlBusy !== null) return
    const busyKey = `${operationId}:${action}`
    setOperationControlBusy(busyKey)
    try {
      await controlOperation(operationId, action)
      toast.success(action === 'restart' ? `${label} restarted` : `${label} canceled`)
    } catch (error) {
      const detail = error instanceof OperationControlError ? error.message : undefined
      toast.error(`Could not ${action} ${label}${detail ? `: ${detail}` : ''}`)
    } finally {
      setOperationControlBusy((current) => current === busyKey ? null : current)
    }
  }

  const operationControls = (operationId: string | undefined, label: string) => {
    if (!operationId) return undefined
    const controlsBusy = operationControlBusy !== null
    return [
      {
        label: `Restart ${label}`,
        icon: ['fas', 'rotate-right'],
        disabled: controlsBusy,
        onSelect: () => void controlTaskOperation(operationId, 'restart', label),
      },
      {
        label: `Cancel ${label}`,
        icon: ['fas', 'xmark'],
        tone: 'danger' as const,
        disabled: controlsBusy,
        onSelect: () => void controlTaskOperation(operationId, 'cancel', label),
      },
    ]
  }

  const onDelete = () => setConfirm(true)
  const onEdit = () => {
    navigate(`/edit-show/${id}`)
  }

  const syncNow = async () => {
    if (syncBusy) {
      toast(`A sync is already in progress for ${show.title}`)
      return
    }

    setSyncStarting(true)
    try {
      const base = (window as any).appConfig?.API_URL || '/api'
      const response = await fetch(`${base}/shows/${encodeURIComponent(id)}/sync`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const result = await response.json()
      if (typeof result?.operationId !== 'string' || !result.operationId) {
        throw new Error('Sync request did not return an operation ID')
      }

      await qc.invalidateQueries({queryKey: ['operations']})
      toast.success(`Sync started for ${show.title}`)
    } catch {
      toast.error(`Could not start sync for ${show.title}`)
    } finally {
      setSyncStarting(false)
    }
  }

  const refreshAllMetadata = async () => {
    if (metadataRefreshBusy) return

    setMetadataRefreshStarting(true)
    try {
      const base = (window as any).appConfig?.API_URL || '/api'
      const response = await fetch(`${base}/shows/${encodeURIComponent(id)}/refresh-metadata`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const result = await response.json()
      const count = typeof result?.episodesQueued === 'number' ? result.episodesQueued : total
      if (typeof result?.operationId !== 'string' || !result.operationId) {
        throw new Error('Metadata refresh request did not return an operation ID')
      }

      setMetadataRefreshConfirm(false)
      await qc.invalidateQueries({queryKey: ['operations']})
      if (count > 0) {
        toast.success(
          `Metadata refresh started for ${count} ${count === 1 ? 'episode' : 'episodes'} in ${show.title}`,
        )
      }
    } catch {
      toast.error(`Could not start metadata refresh for ${show.title}`)
    } finally {
      setMetadataRefreshStarting(false)
    }
  }

  const openRedownloadConfirm = () => {
    if (downloadProfileStateUnknown) {
      toast('WireLoft is still checking the Download Profiles attached to this show')
      return
    }
    if (downloadProfileStateFailed) {
      toast.error('Could not determine which Download Profiles are attached to this show')
      return
    }
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
    if (redownloadBusy || !redownloadProfileId) return

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
      if (typeof result?.operationId !== 'string' || !result.operationId) {
        throw new Error('Re-download request did not return an operation ID')
      }

      const profileCount = typeof result?.downloadProfilesQueued === 'number'
        ? result.downloadProfilesQueued
        : (redownloadProfileId === 'all' ? attachedDownloadProfiles.length : 1)
      setRedownloadConfirm(false)
      await qc.invalidateQueries({queryKey: ['operations']})
      toast.success(
        `Re-download started for ${show.title} using ${profileCount} ${profileCount === 1 ? 'Download Profile' : 'Download Profiles'}`,
      )
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
                  disabled: syncBusy,
                  disabledReason: syncDisabledReason,
                  progress: syncOperation ? (syncOperation.progress ?? 0) : undefined,
                  controls: operationControls(syncOperation?.id, 'sync'),
                  onSelect: () => void syncNow(),
                },
                {
                  label: 'Sync log',
                  icon: ['fas', 'clock-rotate-left'],
                  onSelect: () => setSyncLogOpen(true),
                },
                {
                  label: 'Refresh all metadata',
                  icon: ['fas', 'gallery-thumbnails'],
                  disabled: metadataRefreshBusy,
                  disabledReason: metadataRefreshDisabledReason,
                  progress: metadataRefreshOperation ? (metadataRefreshOperation.progress ?? 0) : undefined,
                  controls: operationControls(metadataRefreshOperation?.id, 'metadata refresh'),
                  onSelect: () => setMetadataRefreshConfirm(true),
                },
                {
                  label: 'Delete and re-download all episodes',
                  icon: ['fas', 'trash'],
                  tone: 'danger',
                  disabled: redownloadDisabledReason !== undefined,
                  disabledReason: redownloadDisabledReason,
                  progress: redownloadOperation ? (redownloadOperation.progress ?? 0) : undefined,
                  controls: operationControls(redownloadOperation?.id, 're-download'),
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
                            title={`Open ${label}`}
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

        {isSeries && seasons.length > 0 && (
          <div className="show-season-filter" aria-label="Season selection">
            <label htmlFor="show-season">Season</label>
            <select
              id="show-season"
              className="input show-season-select"
              value={selectedSeasonId === null ? '' : String(selectedSeasonId)}
              onChange={(event) => setSelectedSeasonId(Number(event.target.value))}
            >
              {selectedSeasonId === null && <option value="" disabled>Select a season</option>}
              {seasons.map((season) => (
                <option key={season.id} value={String(season.id)}>
                  {season.name?.trim() || `Season ${season.index}`}
                </option>
              ))}
            </select>
            <span className="show-season-count">
              {displayedEpisodes.length} {displayedEpisodes.length === 1 ? 'episode' : 'episodes'}
            </span>
          </div>
        )}

        {isSeries && !seasonViewLoading && seasons.length === 0 ? (
          <div className="show-season-empty" role="status">No seasons are available for this series.</div>
        ) : episodesViewLoading ? (
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

        {hasMore && !episodesViewLoading && (
          <div ref={sentinelRef} className="episodes-load-more" aria-hidden>
            Loading more episodes…
          </div>
        )}
      </article>

      <ShowSyncLogModal
        showSlug={id}
        showTitle={show.title}
        open={syncLogOpen}
        syncing={syncBusy}
        onClose={() => setSyncLogOpen(false)}
        onSyncNow={syncNow}
      />

      {metadataRefreshConfirm && (
        <div
          className="modal-overlay"
          role="presentation"
          onClick={() => {
            if (!metadataRefreshBusy) setMetadataRefreshConfirm(false)
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
                disabled={metadataRefreshBusy}
                onClick={() => setMetadataRefreshConfirm(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={metadataRefreshBusy}
                onClick={() => void refreshAllMetadata()}
              >
                {metadataRefreshBusy ? 'Starting…' : 'Refresh metadata'}
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
            if (!redownloadBusy) setRedownloadConfirm(false)
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
                disabled={redownloadBusy}
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
                disabled={redownloadBusy}
                onClick={() => setRedownloadConfirm(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={redownloadBusy || !redownloadProfileId}
                onClick={() => void redownloadAllEpisodes()}
              >
                {redownloadBusy ? 'Starting…' : 'Delete and re-download'}
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
