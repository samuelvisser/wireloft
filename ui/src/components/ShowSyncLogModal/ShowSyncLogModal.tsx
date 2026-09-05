import {useEffect, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useShow} from '../../lib/queries'
import {useTaskLedgerPage} from '../../lib/taskLedger'
import {TaskLedgerEntryRead} from '../../types/schemas/task'
import './ShowSyncLogModal.css'

type Props = {
  showSlug: string
  showTitle: string
  open: boolean
  syncing: boolean
  onClose: () => void
  onSyncNow: () => void | Promise<void>
}

const PAGE_SIZE = 10
const TERMINAL_STATUSES = ['SUCCEEDED', 'FAILED', 'CANCELED'] as const

function resultData(run: TaskLedgerEntryRead): Record<string, unknown> {
  const result = run.result
  if (!result || typeof result !== 'object') return {}
  const data = result.data
  return data && typeof data === 'object' && !Array.isArray(data)
    ? data as Record<string, unknown>
    : {}
}

function showResult(run: TaskLedgerEntryRead, showId: number): Record<string, unknown> | null {
  const data = resultData(run)
  if (run.resourceId === showId) return data
  if (run.resourceId !== 0) return null

  const shows = Array.isArray(data.shows) ? data.shows : []
  const matching = shows.find((item) => {
    if (!item || typeof item !== 'object') return false
    return Number((item as Record<string, unknown>).show_id) === showId
  })
  if (matching && typeof matching === 'object') return matching as Record<string, unknown>

  // Global fetches are scoped to every show that existed when they ran. The
  // ledger query starts at this show's creation time, so keep the row even if a
  // failed/canceled run (or an older result shape) has no per-show payload.
  return {}
}

function episodeCount(run: TaskLedgerEntryRead, showId: number): string | number {
  if (run.status === 'FAILED') return 'Failed'
  if (run.status === 'CANCELED') return 'Canceled'
  const found = showResult(run, showId)?.episodes_found
  return typeof found === 'number' && Number.isFinite(found) ? found : '—'
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const normalized = /(?:Z|[+-]\d\d:\d\d)$/i.test(value) ? value : `${value}Z`
  return new Date(normalized).toLocaleString()
}

export default function ShowSyncLogModal({showSlug, showTitle, open, syncing, onClose, onSyncNow}: Props) {
  const {data: show} = useShow(showSlug)
  const showId = show?.id
  const [page, setPage] = useState(1)

  useEffect(() => {
    if (open) setPage(1)
  }, [open, showSlug])

  const ledger = useTaskLedgerPage({
    definitionKey: 'fetch_new_episodes',
    resourceType: 'show',
    resourceId: showId === undefined ? undefined : [0, showId],
    status: TERMINAL_STATUSES,
    startedAfter: show?.createdAt,
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    enabled: open && showId !== undefined,
  })

  const total = ledger.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const entries = ledger.data?.items ?? []

  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  if (!open) return null

  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="modal show-sync-log-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="show-sync-log-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header show-sync-log-header">
          <div className="modal-icon" aria-hidden>
            <FontAwesomeIcon icon={['fas', 'arrows-rotate']} />
          </div>
          <div>
            <h2 id="show-sync-log-title" className="modal-title">Sync log</h2>
            <div className="show-sync-log-subtitle">{showTitle}</div>
          </div>
        </div>

        <div className="show-sync-log-content">
          {ledger.isLoading ? (
            <p className="modal-text">Loading sync history...</p>
          ) : ledger.isError ? (
            <p className="modal-text">Could not load sync history.</p>
          ) : entries.length === 0 ? (
            <p className="modal-text">No syncs have been recorded yet.</p>
          ) : (
            <div className="show-sync-log-table" role="table" aria-label="Recent syncs">
              <div className="show-sync-log-row show-sync-log-row-header" role="row">
                <span role="columnheader">Ran</span>
                <span role="columnheader">Episodes found</span>
              </div>
              {entries.map((entry) => (
                <div className="show-sync-log-row" role="row" key={entry.id}>
                  <span role="cell">{formatDate(entry.finishedAt ?? entry.startedAt)}</span>
                  <span
                    role="cell"
                    className={entry.status === 'FAILED' ? 'show-sync-log-failed' : undefined}
                  >
                    {showId === undefined ? '—' : episodeCount(entry, showId)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="show-sync-log-footer">
          <nav className="show-sync-log-pagination" aria-label="Sync log pages">
            <button
              type="button"
              className="btn"
              disabled={page <= 1 || ledger.isFetching}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              Previous
            </button>
            <span className="show-sync-log-page-label" aria-live="polite">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              className="btn"
              disabled={page >= totalPages || ledger.isFetching}
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
            >
              Next
            </button>
          </nav>

          <div className="modal-actions show-sync-log-actions">
            <button type="button" className="btn" onClick={onClose}>Close</button>
            <button type="button" className="btn btn-primary" onClick={() => void onSyncNow()} disabled={syncing}>
              <FontAwesomeIcon icon={['fas', syncing ? 'spinner' : 'arrows-rotate']} spin={syncing} aria-hidden="true" />
              <span>{syncing ? 'Syncing...' : 'Sync now'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
