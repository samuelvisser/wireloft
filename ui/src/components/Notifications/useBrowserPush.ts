import {useCallback, useEffect, useState} from 'react'

import {
    DEFAULT_PUSH_EVENTS,
    disablePush,
    enablePush,
    existingPushSubscription,
    pushDeviceSettings,
    savePushEvents,
    supportsPush,
} from '../../lib/pushNotifications'

/** State of Web Push on this browser, exposed as one more destination next to the Apprise channels. */
export function useBrowserPush() {
    const supported = supportsPush()
    const [subscription, setSubscription] = useState<PushSubscription | null>(null)
    const [enabled, setEnabled] = useState(false)
    const [events, setEvents] = useState<string[]>(DEFAULT_PUSH_EVENTS)
    const [loading, setLoading] = useState(supported)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (!supported) return
        let cancelled = false
        void (async () => {
            try {
                const current = await existingPushSubscription()
                const device = current ? await pushDeviceSettings(current) : null
                if (cancelled) return
                setSubscription(current)
                setEnabled(device?.enabled ?? false)
                setEvents(device?.events ?? DEFAULT_PUSH_EVENTS)
            } catch (cause) {
                if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load push settings')
            } finally {
                if (!cancelled) setLoading(false)
            }
        })()
        return () => { cancelled = true }
    }, [supported])

    const run = useCallback(async (action: () => Promise<void>, failure: string) => {
        setBusy(true)
        setError(null)
        try {
            await action()
        } catch (cause) {
            setError(cause instanceof Error ? cause.message : failure)
            throw cause
        } finally {
            setBusy(false)
        }
    }, [])

    const enable = useCallback(() => run(async () => {
        setSubscription(await enablePush(events))
        setEnabled(true)
    }, 'Could not enable push notifications'), [events, run])

    const disable = useCallback(() => run(async () => {
        if (!subscription) return
        await disablePush(subscription)
        setSubscription(null)
        setEnabled(false)
    }, 'Could not disable push notifications'), [run, subscription])

    const saveEvents = useCallback((next: string[]) => run(async () => {
        if (subscription) await savePushEvents(subscription, next)
        setEvents(next)
    }, 'Could not save push notification events'), [run, subscription])

    return {supported, loading, busy, error, enabled, events, enable, disable, saveEvents}
}

export type BrowserPush = ReturnType<typeof useBrowserPush>
