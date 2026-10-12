import {strict as assert} from 'node:assert'
import {test} from 'node:test'

import {createLongTimeoutProvider} from '../src/lib/longTimeoutProvider'
import {queryClient} from '../src/lib/queryClient'

const DAY_MS = 24 * 60 * 60 * 1000
const THIRTY_DAYS_MS = 30 * DAY_MS
const MAX_NATIVE_TIMEOUT_MS = 0x7fffffff

function fakeClock() {
    let now = 0
    let nextHandle = 0
    const scheduled = new Map<number, {callback: () => void; dueAt: number; delay: number}>()

    const originalNow = Date.now
    const originalSetTimeout = globalThis.setTimeout
    const originalClearTimeout = globalThis.clearTimeout
    Date.now = () => now
    Object.defineProperty(globalThis, 'setTimeout', {
        configurable: true,
        value: (callback: () => void, delay: number) => {
            const handle = ++nextHandle
            scheduled.set(handle, {callback, dueAt: now + delay, delay})
            return handle
        },
    })
    Object.defineProperty(globalThis, 'clearTimeout', {
        configurable: true,
        value: (handle: number) => { scheduled.delete(handle) },
    })

    return {
        scheduled,
        advanceTo(target: number) {
            while (true) {
                const next = [...scheduled.entries()]
                    .filter(([, task]) => task.dueAt <= target)
                    .sort((a, b) => a[1].dueAt - b[1].dueAt)[0]
                if (!next) break
                const [handle, task] = next
                scheduled.delete(handle)
                now = task.dueAt
                task.callback()
            }
            now = target
        },
        restore() {
            Date.now = originalNow
            Object.defineProperty(globalThis, 'setTimeout', {configurable: true, value: originalSetTimeout})
            Object.defineProperty(globalThis, 'clearTimeout', {configurable: true, value: originalClearTimeout})
        },
    }
}

test('only the default cache retention changes, not query staleness or explicit gcTime overrides', () => {
    assert.equal(queryClient.getDefaultOptions().queries?.gcTime, THIRTY_DAYS_MS)
    assert.equal(queryClient.getDefaultOptions().queries?.staleTime, 5 * 60 * 1000)
    assert.equal(queryClient.defaultQueryOptions({queryKey: ['custom'], gcTime: 60_000}).gcTime, 60_000)
    assert.equal(queryClient.defaultQueryOptions({queryKey: ['catalog'], gcTime: Infinity}).gcTime, Infinity)
})

test('30-day timeouts do not overflow the native timer limit or fire prematurely', () => {
    const clock = fakeClock()
    try {
        const provider = createLongTimeoutProvider()
        let called = 0
        provider.setTimeout(() => { called++ }, THIRTY_DAYS_MS)
        assert.deepEqual([...clock.scheduled.values()].map((task) => task.delay), [MAX_NATIVE_TIMEOUT_MS])

        clock.advanceTo(THIRTY_DAYS_MS - 1)
        assert.equal(called, 0)
        assert.ok([...clock.scheduled.values()].every((task) => task.delay <= MAX_NATIVE_TIMEOUT_MS))

        clock.advanceTo(THIRTY_DAYS_MS)
        assert.equal(called, 1)
        assert.equal(clock.scheduled.size, 0)
    } finally {
        clock.restore()
    }
})

test('cancellation remains effective between timer chunks', () => {
    const clock = fakeClock()
    try {
        const provider = createLongTimeoutProvider()
        let called = false
        const id = provider.setTimeout(() => { called = true }, THIRTY_DAYS_MS)
        clock.advanceTo(MAX_NATIVE_TIMEOUT_MS)
        provider.clearTimeout(id)
        assert.equal(clock.scheduled.size, 0)
        clock.advanceTo(THIRTY_DAYS_MS + DAY_MS)
        assert.equal(called, false)
    } finally {
        clock.restore()
    }
})

test('short timeouts and recurring timers preserve normal cancellation behavior', () => {
    const clock = fakeClock()
    try {
        const provider = createLongTimeoutProvider()
        let calls = 0
        provider.setTimeout(() => { calls++ }, 100)
        let intervalId = 0
        intervalId = provider.setInterval(() => {
            calls++
            if (calls === 3) provider.clearInterval(intervalId)
        }, 200)

        clock.advanceTo(100)
        assert.equal(calls, 1)
        clock.advanceTo(400)
        assert.equal(calls, 3)
        clock.advanceTo(1000)
        assert.equal(calls, 3)
        assert.equal(clock.scheduled.size, 0)
    } finally {
        clock.restore()
    }
})
