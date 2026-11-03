import {useCallback, useEffect, useState} from 'react'

import {disablePush, enablePush, existingPushSubscription, pushIsOn, sendTestPush, supportsPush} from '../../lib/pushNotifications'

/** Push on this browser: whether it is on for whoever is signed in, and turning it on or off. */
export function useBrowserPush(onChange?: () => void) {
    const supported = supportsPush()
    const [subscription, setSubscription] = useState<PushSubscription | null>(null)
    const [enabled, setEnabled] = useState(false)
    const [loading, setLoading] = useState(supported)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (!supported) return
        let cancelled = false
        void (async () => {
            try {
                const current = await existingPushSubscription()
                const on = current ? await pushIsOn(current) : false
                if (cancelled) return
                setSubscription(current)
                setEnabled(on)
            } catch (cause) {
                if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not check push on this device')
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
            onChange?.()
        } catch (cause) {
            setError(cause instanceof Error ? cause.message : failure)
        } finally {
            setBusy(false)
        }
    }, [onChange])

    const enable = useCallback(() => run(async () => {
        setSubscription(await enablePush())
        setEnabled(true)
    }, 'Could not turn on notifications'), [run])

    const disable = useCallback(() => run(async () => {
        if (subscription) await disablePush(subscription)
        setSubscription(null)
        setEnabled(false)
    }, 'Could not turn off notifications'), [run, subscription])

    const test = useCallback(() => run(async () => {
        if (subscription) await sendTestPush(subscription)
    }, 'Could not send a test notification'), [run, subscription])

    return {supported, loading, busy, error, enabled, enable, disable, test}
}
