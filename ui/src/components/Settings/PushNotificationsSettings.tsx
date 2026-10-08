import {useEffect, useState} from 'react'
import {Link} from 'react-router-dom'

import {SettingsSection} from './SettingsControls'
import {
  DEFAULT_PUSH_CATEGORIES,
  PUSH_CATEGORIES,
  disablePush,
  enablePush,
  existingPushSubscription,
  fetchPushHistory,
  pushDeviceSettings,
  savePushCategories,
  supportsPush,
  type PushCategory,
  type PushHistoryEntry,
} from '../../lib/pushNotifications'

function historyLocation(entry: PushHistoryEntry): string {
  if (entry.kind.startsWith('media.download') || entry.resourceType === 'media_download') return '/downloads'
  return entry.source !== 'UI' || entry.status === 'FAILED' ? '/tasks' : '/'
}

function statusLabel(status: string) {
  return ({
    SUCCEEDED: 'Completed',
    PARTIAL: 'Partially completed',
    FAILED: 'Failed',
    CANCELED: 'Canceled',
  } as Record<string, string>)[status] || status
}

export default function PushNotificationsSettings() {
  const supported = supportsPush()
  const [subscription, setSubscription] = useState<PushSubscription | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [categories, setCategories] = useState<PushCategory[]>(DEFAULT_PUSH_CATEGORIES)
  const [history, setHistory] = useState<PushHistoryEntry[]>([])
  const [historyExpanded, setHistoryExpanded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const current = await existingPushSubscription()
        const device = current ? await pushDeviceSettings(current) : null
        const events = await fetchPushHistory()
        if (cancelled) return
        setSubscription(current)
        setEnabled(device?.enabled ?? false)
        setCategories(device?.categories ?? DEFAULT_PUSH_CATEGORIES)
        setHistory(events)
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load notification settings')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [])

  const enable = async () => {
    setBusy(true)
    setError(null)
    try {
      const current = await enablePush(categories)
      setSubscription(current)
      setEnabled(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not enable push notifications')
    } finally {
      setBusy(false)
    }
  }

  const disable = async () => {
    if (!subscription) return
    setBusy(true)
    setError(null)
    try {
      await disablePush(subscription)
      setEnabled(false)
      setSubscription(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not disable push notifications')
    } finally {
      setBusy(false)
    }
  }

  const toggleCategory = async (category: PushCategory) => {
    const selected = categories.includes(category)
      ? categories.filter((value) => value !== category)
      : [...categories, category]
    const previous = categories
    setCategories(selected)
    if (!enabled || !subscription) return

    setBusy(true)
    setError(null)
    try {
      await savePushCategories(subscription, selected)
    } catch (cause) {
      setCategories(previous)
      setError(cause instanceof Error ? cause.message : 'Could not save notification preferences')
    } finally {
      setBusy(false)
    }
  }

  return (
    <SettingsSection
      title="Push notifications"
      description="Get alerts on this device when WireLoft is not open in the foreground."
    >
      <div className="settings-field settings-field--wide">
        <p className="settings-field__help">
          Notifications are enabled separately on each installed device. When WireLoft is visible and focused,
          ordinary in-app toasts take precedence. Permission is requested only when you enable notifications.
        </p>
        {!supported ? (
          <p className="settings-field__help">
            Web Push requires a supported browser and HTTPS. On iOS, install WireLoft on your Home Screen first.
            Push is disabled in Vite development mode.
          </p>
        ) : (
          <>
            <div className="settings-actions__buttons">
              <button
                type="button"
                className={enabled ? 'btn btn-secondary' : 'btn btn-primary'}
                disabled={loading || busy}
                onClick={() => void (enabled ? disable() : enable())}
              >
                {busy ? 'Updating…' : enabled ? 'Disable push notifications' : 'Enable push notifications'}
              </button>
            </div>
            <p className="settings-field__help">
              {enabled ? 'Push notifications are active for this browser.' : 'Push notifications are off for this browser.'}
            </p>
            {Notification.permission === 'denied' ? (
              <p className="settings-field__help" role="status">
                Browser notifications are blocked. Allow them in the browser or operating-system settings.
              </p>
            ) : null}
          </>
        )}
        {error ? <p role="alert" className="error">{error}</p> : null}
      </div>

      <div className="settings-field settings-field--wide">
        <strong>Notification categories</strong>
        <div className="push-notification-categories">
          {PUSH_CATEGORIES.map(({key, label, description}) => (
            <label key={key} className="push-notification-category">
              <input
                type="checkbox"
                checked={categories.includes(key)}
                disabled={busy || loading}
                onChange={() => void toggleCategory(key)}
              />
              <span><strong>{label}</strong><small>{description}</small></span>
            </label>
          ))}
        </div>
      </div>

      <div className="settings-field settings-field--wide">
        <div className="push-notification-history-heading">
          <strong>Recent operation history</strong>
          <button className="btn btn-secondary" type="button" onClick={() => setHistoryExpanded((value) => !value)}>
            {historyExpanded ? 'Show less' : 'Show more'}
          </button>
        </div>
        <p className="settings-field__help">
          Completed operations stay available here even if a device was offline or its notification was dismissed.
        </p>
        {loading ? <p>Loading…</p> : history.length === 0 ? (
          <p className="settings-field__help">No completed operations yet.</p>
        ) : (
          <ul className="push-notification-history">
            {history.slice(0, historyExpanded ? 75 : 8).map((entry) => (
              <li key={entry.id}>
                <Link to={historyLocation(entry)}>{entry.title}</Link>
                <span>{statusLabel(entry.status)}</span>
                {entry.finishedAt ? <time dateTime={entry.finishedAt}>{new Date(entry.finishedAt).toLocaleString()}</time> : null}
                {entry.pushNotifiedAt ? <small>Push sent</small> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </SettingsSection>
  )
}
