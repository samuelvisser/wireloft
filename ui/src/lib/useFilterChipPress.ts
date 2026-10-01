import {useCallback, useRef} from 'react'

const FILTER_DOUBLE_PRESS_WINDOW_MS = 500

type LastPress = {
    value: string
    timestamp: number
}

/**
 * Gives multi-select filter chips the same shortcut everywhere: pressing the
 * same chip twice in quick succession makes it the only active filter.
 *
 * We intentionally track consecutive click events rather than relying on the
 * browser's dblclick event so touch-generated clicks behave the same way.
 */
export function useFilterChipPress() {
    const lastPressRef = useRef<LastPress | null>(null)

    const press = useCallback((
        value: string,
        toggle: () => void,
        selectOnly: () => void,
    ) => {
        const now = Date.now()
        const previousPress = lastPressRef.current

        if (
            previousPress?.value === value
            && now - previousPress.timestamp <= FILTER_DOUBLE_PRESS_WINDOW_MS
        ) {
            lastPressRef.current = null
            selectOnly()
            return
        }

        lastPressRef.current = {value, timestamp: now}
        toggle()
    }, [])

    const reset = useCallback(() => {
        lastPressRef.current = null
    }, [])

    return {press, reset}
}
