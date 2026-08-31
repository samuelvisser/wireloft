import { useCallback, useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { toast } from 'react-hot-toast'
import './ShowSyncLogModal.css'

type SyncLogEntry = {
  synced_at: string
  episodes_found: number
}

type Props = {
  showSlug: string
  showTitle: string
  open: boolean
  onClose: () => void
  onSyncCompleted?: () => void
}

const POLL_INTERVAL_MS = 2000

export default function ShowSyncLogModal({ showSlug, showTitle, open, onClose, onSyncCompleted }: Props) {
  const [entries, setEntries] = useState<SyncLogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const previousLatestRef = useRef<string | null>(null)

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
      .then((data) => {
        previousLatestRef.current = data[0]?.synced_at ?? null
      })
      .catch(() => toast.error('Could not load sync history'))
      .finally(() => setLoading(false))
  }, [loadLog, open])

  useEffect(() => {
    if (!open || !syncing) return
    const timer = window.setInterval(() => {
      loadLog()
        .then((data) => {
          const latest = data[0]?.synced_at ?? null
          if (latest && latest !== previousLatestRef.current) {
            previousLatestRef.current = latest
            setSyncing(false)
            onSyncCompleted?.()
          }
        })
        .catch(() => undefined)
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [loadLog, onSyncCompleted, open, syncing])

  const syncNow = async () => {
    try {
      const response = await fetch(`${apiBase}/shows/${encodeURIComponent(showSlug)}/sync`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      previousLatestRef.current = entries[0]?.synced_at ?? null
      setSyncing(true)
      toast.success(`Sync started for ${showTitle}`)
    } catch {
      toast.error(`Could not start sync for ${showTitle}`)
    }
  }

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
            <p className="modal-text">No completed syncs have been recorded yet.</p>
          ) : (
            <div className="show-sync-log-table" role="table" aria-label="Recent syncs">
              <div className="show-sync-log-row show-sync-log-row-header" role="row">
                <span role="columnheader">Ran</span>
                <span role="columnheader">Episodes found</span>
              </div>
              {entries.map((entry) => (
                <div className="show-sync-log-row" role="row" key={entry.synced_at}>
                  <span role="cell">{new Date(entry.synced_at).toLocaleString()}</span>
                  <span role="cell">{entry.episodes_found}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose}>Close</button>
          <button type="button" className="btn btn-primary" onClick={syncNow} disabled={syncing}>
            <FontAwesomeIcon icon={['fas', syncing ? 'spinner' : 'arrows-rotate']} spin={syncing} aria-hidden="true" />
            <span>{syncing ? 'Syncing...' : 'Sync now'}</span>
          </button>
        </div>
      </div>
    </div>
  )
}
