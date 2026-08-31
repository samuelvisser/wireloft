import { useCallback, useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { toast } from 'react-hot-toast'
import './ShowSyncLogModal.css'

type SyncLogEntry = {
  synced_at: string
  episodes_found: number
  status?: 'completed' | 'failed'
}

type Props = {
  showSlug: string
  showTitle: string
  open: boolean
  syncing: boolean
  onClose: () => void
  onSyncNow: () => void | Promise<void>
}

const POLL_INTERVAL_MS = 2000

export default function ShowSyncLogModal({ showSlug, showTitle, open, syncing, onClose, onSyncNow }: Props) {
  const [entries, setEntries] = useState<SyncLogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const wasSyncingRef = useRef(false)

  const apiBase = (window as any).appConfig?.API_URL || '/api'

  const loadLog = useCallback(async () => {
    const response = await fetch(`${apiBase}/shows/${encodeURIComponent(showSlug)}/sync-log`, {
      credentials: 'include',
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data: SyncLogEntry[] = await response.json()
    setEntries(data)
    return data
  }, [apiBase, showSlug])

  useEffect(() => {
    if (!open) return
    setLoading(true)
    loadLog()
      .catch(() => toast.error('Could not load sync history'))
      .finally(() => setLoading(false))
  }, [loadLog, open])

  useEffect(() => {
    if (!open || !syncing) return
    const timer = window.setInterval(() => {
      loadLog().catch(() => undefined)
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [loadLog, open, syncing])

  useEffect(() => {
    if (!open) {
      wasSyncingRef.current = syncing
      return
    }

    if (wasSyncingRef.current && !syncing) {
      loadLog().catch(() => undefined)
    }
    wasSyncingRef.current = syncing
  }, [loadLog, open, syncing])

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
          {loading ? (
            <p className="modal-text">Loading sync history...</p>
          ) : entries.length === 0 ? (
            <p className="modal-text">No syncs have been recorded yet.</p>
          ) : (
            <div className="show-sync-log-table" role="table" aria-label="Recent syncs">
              <div className="show-sync-log-row show-sync-log-row-header" role="row">
                <span role="columnheader">Ran</span>
                <span role="columnheader">Episodes found</span>
              </div>
              {entries.map((entry) => (
                <div className="show-sync-log-row" role="row" key={entry.synced_at}>
                  <span role="cell">{new Date(entry.synced_at).toLocaleString()}</span>
                  <span role="cell" className={entry.status === 'failed' ? 'show-sync-log-failed' : undefined}>
                    {entry.status === 'failed' ? 'Failed' : entry.episodes_found}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose}>Close</button>
          <button type="button" className="btn btn-primary" onClick={() => void onSyncNow()} disabled={syncing}>
            <FontAwesomeIcon icon={['fas', syncing ? 'spinner' : 'arrows-rotate']} spin={syncing} aria-hidden="true" />
            <span>{syncing ? 'Syncing...' : 'Sync now'}</span>
          </button>
        </div>
      </div>
    </div>
  )
}
