import type {TimeoutCallback, TimeoutProvider} from '@tanstack/react-query'

// Browsers clamp timeouts above this value to a very short delay. The default
// QueryClient gcTime is 30 days, so long waits must be scheduled in chunks.
const MAX_NATIVE_TIMEOUT_MS = 0x7fffffff

export function createLongTimeoutProvider(): TimeoutProvider<number> {
    let nextId = 0
    const timers = new Map<number, ReturnType<typeof setTimeout>>()

    const clear = (id: number | undefined) => {
        if (id === undefined) return
        const timer = timers.get(id)
        if (timer !== undefined) clearTimeout(timer)
        timers.delete(id)
    }

    const schedule = (callback: TimeoutCallback, delay: number, recurring: boolean): number => {
        // Use distinct nonzero IDs so cancellation also works with versions of
        // TanStack Query that check timer handles for truthiness.
        const id = ++nextId
        const period = Math.max(0, delay)
        let deadline = Date.now() + period

        const arm = () => {
            const remaining = Math.max(0, deadline - Date.now())
            timers.set(id, setTimeout(tick, Math.min(remaining, MAX_NATIVE_TIMEOUT_MS)))
        }

        const tick = () => {
            if (!timers.has(id)) return

            // Recalculate against the absolute deadline after each chunk. This
            // also handles background-tab throttling and sleeping devices.
            if (Date.now() < deadline) {
                arm()
                return
            }

            if (recurring) {
                deadline = Date.now() + Math.max(1, period)
                arm()
            } else {
                timers.delete(id)
            }
            callback(undefined)
        }

        arm()
        return id
    }

    return {
        setTimeout: (callback, delay) => schedule(callback, delay, false),
        clearTimeout: clear,
        setInterval: (callback, delay) => schedule(callback, delay, true),
        clearInterval: clear,
    }
}
