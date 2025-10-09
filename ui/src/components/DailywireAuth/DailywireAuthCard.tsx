import {useCallback, useEffect, useRef, useState} from 'react'
import { DeviceAuthResponse, DeviceAuthResponseSchema, PollResponse, PollResponseSchema, StatusResponse, StatusResponseSchema } from '../../types/schemas/dailywire_auth'


function apiBase() {
    const base = (window as any).appConfig?.API_URL?.replace(/\/+$/, '')
    return `${base}/dailywire/auth`
}

export default function DailywireAuthCard() {
    const [status, setStatus] = useState<StatusResponse | null>(null)
    const [loading, setLoading] = useState<boolean>(true)
    const [error, setError] = useState<string | null>(null)

    // Device flow state
    const [flow, setFlow] = useState<DeviceAuthResponse | null>(null)
    const [flowStatus, setFlowStatus] = useState<PollResponse | null>(null)
    const [isPolling, setIsPolling] = useState<boolean>(false)

    const abortRef = useRef<AbortController | null>(null)

    const refreshStatus = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            const r = await fetch(`${apiBase()}/status`, {credentials: 'include'})
            if (!r.ok) throw new Error(`Failed to load status (HTTP ${r.status})`)
            const j = StatusResponseSchema.parse(await r.json())
            setStatus(j)
        } catch (e: any) {
            setError(e?.message || 'Failed to load status')
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        void refreshStatus()
        // Cleanup on unmount
        return () => {
            if (abortRef.current) {
                abortRef.current.abort()
            }
        }
    }, [refreshStatus])

    const startFlow = useCallback(async () => {
        setError(null)
        setFlow(null)
        setFlowStatus(null)
        setIsPolling(false)
        try {
            const r = await fetch(`${apiBase()}/device`, {
                method: 'POST',
                credentials: 'include',
            })
            if (!r.ok) throw new Error(`Failed to start authorization (HTTP ${r.status})`)
            const j = DeviceAuthResponseSchema.parse(await r.json())

            setFlow(j)
            // Kick off polling immediately
            void pollUntilAuthorized(j)
            // Try to open the verification URL in a new tab for convenience
            const url = j.verificationUriComplete || j.verificationUri
            if (url) {
                try {
                    window.open(url, '_blank', 'noopener,noreferrer')
                } catch {
                    // ignore if popup blocked
                }
            }
        } catch (e: any) {
            setError(e?.message || 'Failed to start authorization')
        }
    }, [])

    const pollUntilAuthorized = useCallback(async (j: DeviceAuthResponse) => {
        if (abortRef.current) abortRef.current.abort()
        const ac = new AbortController()
        abortRef.current = ac
        setIsPolling(true)
        setFlowStatus(null)
        try {
            const r = await fetch(`${apiBase()}/poll`, {
                method: 'POST',
                credentials: 'include',
                signal: ac.signal,
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({device_code: j.deviceCode}),
            })
            if (!r.ok) {
                // try to parse error
                let detail = `Failed to complete authorization (HTTP ${r.status})`
                try {
                    const body = await r.json()
                    if (typeof body?.detail === 'string') detail = body.detail
                } catch {
                }
                throw new Error(detail)
            }
            const pr = PollResponseSchema.parse(await r.json())
            setFlowStatus(pr)
            if (pr.status === 'authorized') {
                await refreshStatus()
            }
        } catch (e: any) {
            if (e?.name === 'AbortError') return
            setError(e?.message || 'Authorization failed')
            setFlowStatus({status: 'denied', message: 'Authorization failed'})
        } finally {
            setIsPolling(false)
        }
    }, [refreshStatus])

    const disconnect = useCallback(async () => {
        setError(null)
        // stop any active polling and clear local device-flow state immediately
        if (abortRef.current) {
            try {
                abortRef.current.abort()
            } catch {
            }
            abortRef.current = null
        }
        setIsPolling(false)
        setFlow(null)
        setFlowStatus(null)
        try {
            const r = await fetch(`${apiBase()}/logout`, {method: 'POST', credentials: 'include'})
            if (!r.ok) throw new Error(`Failed to disconnect (HTTP ${r.status})`)
        } catch (e: any) {
            setError(e?.message || 'Failed to disconnect')
        } finally {
            await refreshStatus()
        }
    }, [refreshStatus])

    const copyCode = useCallback(async () => {
        if (!flow?.userCode) return
        try {
            await navigator.clipboard.writeText(flow.userCode)
        } catch {
            // ignore
        }
    }, [flow?.userCode])

    return (
        <div className="card dailywire-auth-card" aria-live="polite">
            <div className="card-header" style={{display: 'flex', alignItems: 'center', gap: 12}}>
                <img src="/dw-logo-plus-compact.png" alt="DailyWire logo" style={{height: 28}}/>
                <h2 style={{margin: 0, fontSize: 18}}>DailyWire Account</h2>
                <div style={{marginLeft: 'auto'}}>
                    {status?.authenticated ? (
                        <span className="dw-status-badge" title="Connected">Connected</span>
                    ) : (
                        <span className="dw-status-badge" title="Not connected">Not connected</span>
                    )}
                </div>
            </div>

            <div className="card-body" style={{display: 'grid', gap: 12}}>
                {loading ? (
                    <p>Checking status…</p>
                ) : (
                    <>
                        {error ? (
                            <div role="alert" className="alert" style={{color: 'var(--red-600, #b91c1c)'}}>{error}</div>
                        ) : null}

                        {status?.authenticated ? (
                            <>
                                <p>You are connected to DailyWire.</p>
                                <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
                                    <button className="btn" onClick={refreshStatus}>Refresh status</button>
                                    <button className="btn btn-danger" onClick={disconnect}>Disconnect</button>
                                </div>
                            </>
                        ) : (
                            <>
                                <p>Connect your DailyWire account to download members-only content.</p>
                                {!flow ? (
                                    <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
                                        <button className="btn btn-primary" onClick={startFlow}>Connect DailyWire</button>
                                        <button className="btn" onClick={refreshStatus}>Refresh status</button>
                                    </div>
                                ) : (
                                    <div className="device-flow" style={{display: 'grid', gap: 10}}>
                                        <ol style={{margin: 0, paddingLeft: 18}}>
                                            <li>
                                                Open DailyWire authorization page:
                                                <div style={{marginTop: 6}}>
                                                    <a className="btn btn-secondary"
                                                       href={flow.verificationUriComplete || flow.verificationUri}
                                                       target="_blank" rel="noreferrer noopener">Open authorization</a>
                                                </div>
                                            </li>
                                            <li style={{marginTop: 10}}>
                                                When prompted, enter this code:
                                                <div style={{
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: 8,
                                                    marginTop: 6
                                                }}>
                                                    <code
                                                        style={{fontSize: 20, fontWeight: 700}}>{flow.userCode}</code>
                                                    <button className="btn" onClick={copyCode}
                                                            aria-label="Copy code">Copy
                                                    </button>
                                                </div>
                                            </li>
                                        </ol>
                                        <div>
                                            {isPolling ? (
                                                <p>Waiting for authorization…</p>
                                            ) : flowStatus ? (
                                                flowStatus.status === 'authorized' ? (
                                                    <p style={{color: 'var(--green-700, #15803d)'}}>Connected successfully.</p>
                                                ) : flowStatus.status === 'expired' ? (
                                                    <p style={{color: 'var(--red-700, #b91c1c)'}}>Code expired. Please try again.</p>
                                                ) : (
                                                    <p style={{color: 'var(--red-700, #b91c1c)'}}>Authorization denied. You can try again.</p>
                                                )
                                            ) : null}
                                        </div>
                                        <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
                                            {!isPolling && (
                                                <button className="btn btn-primary" onClick={startFlow}>Try again</button>
                                            )}
                                            {!isPolling && (
                                                <button className="btn" onClick={() => setFlow(null)}>Cancel</button>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </>
                        )}
                    </>
                )}
            </div>
        </div>
    )
}
