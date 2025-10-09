import {useEffect, useMemo, useRef, useState} from 'react'
import {useQuery, useQueryClient} from '@tanstack/react-query'

// Lightweight fetch helper matching the app's pattern
async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: 'include', ...init })
  if (!r.ok) {
    let detail: string | undefined
    try {
      const body = await r.json()
      detail = typeof body?.detail === 'string' ? body.detail : undefined
    } catch (_) { /* ignore */ }
    throw new Error(detail || `HTTP ${r.status}`)
  }
  return r.json() as Promise<T>
}

// API models mirrored from backend for convenience
interface AuthStatusResponse {
  authenticated: boolean
  status: string
  token_expires_at?: string | null
  has_refresh_token: boolean
  last_auth_at?: string | null
}

interface DeviceStartResponse {
  url: string
  userCode?: string | null
  deviceCode: string
  interval: number
  expiresIn: number
  verificationUri?: string | null
  verificationUriComplete?: string | null
  issuer: string
}

interface DevicePollResponse {
  authenticated: boolean
  status: string
  expires_at?: string | null
  has_refresh_token: boolean
}

export default function SettingsPage() {
  const apiBase = (window as any).appConfig.API_URL as string
  const qc = useQueryClient()

  const { data: auth, isLoading, isFetching, refetch } = useQuery<AuthStatusResponse, Error>({
    queryKey: ['dwAuthStatus'],
    queryFn: () => fetchJSON<AuthStatusResponse>(`${apiBase}/dailywire/auth/device/status`),
    refetchOnMount: 'always',
  })

  const [deviceInfo, setDeviceInfo] = useState<DeviceStartResponse | null>(null)
  const [pollError, setPollError] = useState<string | null>(null)
  const [polling, setPolling] = useState(false)
  const pollTimer = useRef<number | null>(null)
  const deadlineAt = useMemo(() => {
    if (!deviceInfo) return null
    return new Date(Date.now() + (deviceInfo.expiresIn ?? 0) * 1000)
  }, [deviceInfo])

  useEffect(() => () => { if (pollTimer.current) window.clearInterval(pollTimer.current) }, [])

  async function startAuthorisation() {
    setPollError(null)
    setDeviceInfo(null)
    setPolling(false)
    try {
      const info = await fetchJSON<DeviceStartResponse>(`${apiBase}/dailywire/auth/device/start`, { method: 'POST' })
      setDeviceInfo(info)
      // Begin polling
      const startedAt = Date.now()
      const maxMs = info.expiresIn * 1000
      setPolling(true)
      pollTimer.current = window.setInterval(async () => {
        try {
          const elapsed = Date.now() - startedAt
          if (elapsed > maxMs) {
            if (pollTimer.current) window.clearInterval(pollTimer.current)
            setPolling(false)
            setPollError('Authorisation timed out. Please try again.')
            return
          }
          const resp = await fetchJSON<DevicePollResponse>(`${apiBase}/dailywire/auth/device/poll`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              deviceCode: info.deviceCode,
              issuer: info.issuer,
              interval: info.interval,
            }),
          })
          if (resp.authenticated) {
            if (pollTimer.current) window.clearInterval(pollTimer.current)
            setPolling(false)
            setDeviceInfo(null)
            await refetch()
            await qc.invalidateQueries({ queryKey: ['dwAuthStatus'] })
          }
        } catch (e: any) {
          // Store and keep polling until expiry
          setPollError(e?.message || 'Authorisation failed')
        }
      }, Math.max(2000, (info.interval || 5) * 1000))
    } catch (e: any) {
      setPollError(e?.message || 'Could not start authorisation')
    }
  }

  function StatusBadge({ label, tone }: { label: string, tone: 'ok'|'warn'|'err'|'muted' }) {
    const colors: Record<typeof tone, string> = {
      ok: '#0a7f2e',
      warn: '#9a6b00',
      err: '#9a002b',
      muted: '#666'
    }
    return (
      <span style={{
        display: 'inline-block', padding: '2px 8px', borderRadius: 999,
        background: '#f2f2f2', color: colors[tone], border: `1px solid ${colors[tone]}AA`, fontSize: 12,
      }}>{label}</span>
    )
  }

  const isAuthed = !!auth?.authenticated
  const statusTone: 'ok'|'warn'|'err'|'muted' = !auth ? 'muted' : isAuthed ? 'ok' : (auth.status === 'not_configured' ? 'warn' : 'err')

  return (
    <section className="view" aria-labelledby="settings-title">
      <h1 id="settings-title">Settings</h1>

      <section aria-labelledby="dw-auth-title" style={{ marginTop: 24 }}>
        <h2 id="dw-auth-title" style={{ marginBottom: 8 }}>Dailywire Authorisation</h2>
        <p style={{ marginTop: 0, color: '#555' }}>Connect your Dailywire account so Wireloft can access your shows.</p>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '8px 0' }}>
          <strong>Current status:</strong>
          {isLoading || isFetching ? (
            <StatusBadge label="Checking..." tone="muted" />
          ) : (
            <StatusBadge label={auth ? (auth.authenticated ? 'Authenticated' : (auth.status || 'Not authenticated')) : 'Unknown'} tone={statusTone} />
          )}
        </div>

        {auth?.last_auth_at && (
          <div style={{ color: '#555', fontSize: 13 }}>Last authorised: {new Date(auth.last_auth_at).toLocaleString()}</div>
        )}
        {auth?.token_expires_at && (
          <div style={{ color: '#555', fontSize: 13 }}>Access token expires: {new Date(auth.token_expires_at).toLocaleString()}</div>
        )}

        {!isAuthed && !deviceInfo && (
          <div style={{ marginTop: 12 }}>
            <button onClick={startAuthorisation}>Authorise Dailywire</button>
            {pollError && <div style={{ color: '#b3002d', marginTop: 8 }}>{pollError}</div>}
          </div>
        )}

        {deviceInfo && (
          <div style={{
            marginTop: 12, padding: 12, border: '1px solid #ddd', borderRadius: 8, background: '#fafafa'
          }}>
            <div style={{ marginBottom: 8 }}>
              <strong>Step 1:</strong> Visit{' '}
              {deviceInfo.verificationUriComplete ? (
                <a href={deviceInfo.verificationUriComplete} target="_blank" rel="noreferrer">this link</a>
              ) : (
                <a href={deviceInfo.url} target="_blank" rel="noreferrer">{deviceInfo.url}</a>
              )}
            </div>
            {deviceInfo.userCode && (
              <div style={{ marginBottom: 8 }}>
                <strong>Step 2:</strong> Enter this code: <code>{deviceInfo.userCode}</code>
              </div>
            )}
            <div style={{ color: '#555' }}>
              Waiting for authorisation... {polling ? '' : '(not polling)'}
              {deadlineAt && <span> (expires {deadlineAt.toLocaleTimeString()})</span>}
            </div>
            {pollError && <div style={{ color: '#b3002d', marginTop: 8 }}>{pollError}</div>}
          </div>
        )}
      </section>
    </section>
  )
}
