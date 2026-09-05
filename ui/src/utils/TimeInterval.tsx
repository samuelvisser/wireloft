import {useEffect, useId, useMemo, useRef, useState} from 'react'
import type {CSSProperties, ChangeEventHandler, FocusEventHandler, MouseEventHandler} from 'react'


export const TIME_UNITS = ['days', 'hours', 'minutes', 'seconds', 'milliseconds'] as const
export type TimeUnit = typeof TIME_UNITS[number]

type TimeUnitValues = Record<TimeUnit, number>
type TimeUnitDraft = Record<TimeUnit, string>

export type TimeIntervalProps = {
    value: number
    onChange: (value: number) => void
    backendUnit: TimeUnit
    idPrefix?: string
    disabled?: boolean
    className?: string
    style?: CSSProperties
    step?: number
    ariaInvalid?: boolean
    ariaDescribedBy?: string
}

const UNIT_SIZE_IN_MILLISECONDS: Record<TimeUnit, number> = {
    days: 86_400_000,
    hours: 3_600_000,
    minutes: 60_000,
    seconds: 1_000,
    milliseconds: 1,
}

const UNIT_LABELS: Record<TimeUnit, string> = {
    days: 'days',
    hours: 'hours',
    minutes: 'minutes',
    seconds: 'seconds',
    milliseconds: 'ms',
}

function roundValue(value: number): number {
    return Math.round(value * 1_000_000_000) / 1_000_000_000
}

function unitsForBackendUnit(backendUnit: TimeUnit): TimeUnit[] {
    const backendIndex = TIME_UNITS.indexOf(backendUnit)
    return TIME_UNITS.slice(0, backendIndex + 1)
}

function backendUnitsPerDisplayUnit(displayUnit: TimeUnit, backendUnit: TimeUnit): number {
    return UNIT_SIZE_IN_MILLISECONDS[displayUnit] / UNIT_SIZE_IN_MILLISECONDS[backendUnit]
}

function splitValue(value: number, backendUnit: TimeUnit, firstUnit?: TimeUnit): TimeUnitValues {
    const parts: TimeUnitValues = {
        days: 0,
        hours: 0,
        minutes: 0,
        seconds: 0,
        milliseconds: 0,
    }
    let remaining = Number.isFinite(value) && value > 0 ? value : 0
    const availableUnits = unitsForBackendUnit(backendUnit)
    const requestedFirstIndex = firstUnit ? availableUnits.indexOf(firstUnit) : 0
    const firstIndex = requestedFirstIndex >= 0 ? requestedFirstIndex : 0

    for (const unit of availableUnits.slice(firstIndex)) {
        const factor = backendUnitsPerDisplayUnit(unit, backendUnit)
        if (unit === backendUnit) {
            parts[unit] = roundValue(remaining)
            break
        }

        const count = Math.floor(remaining / factor)
        parts[unit] = count
        remaining = roundValue(remaining - count * factor)
    }

    return parts
}

function toDraft(parts: TimeUnitValues): TimeUnitDraft {
    return {
        days: String(parts.days),
        hours: String(parts.hours),
        minutes: String(parts.minutes),
        seconds: String(parts.seconds),
        milliseconds: String(parts.milliseconds),
    }
}

function visibleUnitsForValue(value: number, backendUnit: TimeUnit): TimeUnit[] {
    const availableUnits = unitsForBackendUnit(backendUnit)
    if (!Number.isFinite(value) || value <= 0) return [backendUnit]

    const firstVisibleIndex = availableUnits.findIndex(
        (unit) => value >= backendUnitsPerDisplayUnit(unit, backendUnit),
    )
    if (firstVisibleIndex < 0) return [backendUnit]
    return availableUnits.slice(firstVisibleIndex)
}

export default function TimeInterval({
    value,
    onChange,
    backendUnit,
    idPrefix,
    disabled,
    className,
    style,
    step = 1,
    ariaInvalid,
    ariaDescribedBy,
}: TimeIntervalProps) {
    const autoId = useId()
    const baseId = idPrefix ?? `ti-${autoId}`
    const justFocusedUnit = useRef<TimeUnit | null>(null)
    const previousBackendUnit = useRef(backendUnit)
    const lastEmittedValue = useRef<number | null>(null)
    const availableUnits = useMemo(() => unitsForBackendUnit(backendUnit), [backendUnit])
    const automaticallyVisibleUnits = useMemo(
        () => visibleUnitsForValue(value, backendUnit),
        [backendUnit, value],
    )
    const [firstVisibleUnit, setFirstVisibleUnit] = useState<TimeUnit>(automaticallyVisibleUnits[0])
    const [collapsedBeforeUnit, setCollapsedBeforeUnit] = useState<TimeUnit | null>(null)
    const [draftParts, setDraftParts] = useState<TimeUnitDraft>(() => toDraft(splitValue(value, backendUnit)))
    const [removeControlVisible, setRemoveControlVisible] = useState(false)

    useEffect(() => {
        if (previousBackendUnit.current !== backendUnit) {
            previousBackendUnit.current = backendUnit
            lastEmittedValue.current = null
            setCollapsedBeforeUnit(null)
            setFirstVisibleUnit(automaticallyVisibleUnits[0])
            setDraftParts(toDraft(splitValue(value, backendUnit)))
            return
        }

        // Local edits already decide whether a coarser unit should be revealed.
        // Keeping that decision here also preserves an explicitly collapsed unit.
        if (lastEmittedValue.current !== null && Object.is(value, lastEmittedValue.current)) {
            lastEmittedValue.current = null
            return
        }

        // An external form reset/value replacement restores the canonical automatic view.
        setCollapsedBeforeUnit(null)
        setFirstVisibleUnit(automaticallyVisibleUnits[0])
        if (Number.isFinite(value)) {
            setDraftParts(toDraft(splitValue(value, backendUnit)))
        }
    }, [automaticallyVisibleUnits, backendUnit, value])

    const firstVisibleIndex = Math.max(0, availableUnits.indexOf(firstVisibleUnit))
    const visibleUnits = availableUnits.slice(firstVisibleIndex)
    const nextLargerUnit = firstVisibleIndex > 0 ? availableUnits[firstVisibleIndex - 1] : null
    const canRemoveCoarsestUnit = !disabled && visibleUnits.length > 1

    const valueFromDraft = (nextDraft: TimeUnitDraft): number => {
        if (visibleUnits.every((unit) => nextDraft[unit].trim() === '')) {
            return Number.NaN
        }

        let total = 0
        for (const unit of visibleUnits) {
            const rawValue = nextDraft[unit].trim()
            if (rawValue === '') continue

            const parsed = Number(rawValue)
            if (!Number.isFinite(parsed) || parsed < 0) return Number.NaN
            total += parsed * backendUnitsPerDisplayUnit(unit, backendUnit)
        }

        return roundValue(total)
    }

    const normalizeDraft = (
        nextDraft: TimeUnitDraft,
        total: number,
        normalizedFirstUnit: TimeUnit,
        editedUnit?: TimeUnit,
    ): TimeUnitDraft => {
        const normalized = toDraft(splitValue(total, backendUnit, normalizedFirstUnit))
        const normalizedFirstIndex = availableUnits.indexOf(normalizedFirstUnit)

        // A blank unit is a valid representation of zero. Preserve those blanks
        // unless normalization actually needs that unit to carry a value.
        for (const unit of availableUnits.slice(normalizedFirstIndex)) {
            if (unit !== editedUnit && nextDraft[unit].trim() === '' && normalized[unit] === '0') {
                normalized[unit] = ''
            }
        }

        return normalized
    }

    const firstUnitForTotal = (total: number): TimeUnit => {
        if (!Number.isFinite(total)) return firstVisibleUnit

        const automaticFirstUnit = visibleUnitsForValue(total, backendUnit)[0]
        const automaticIndex = availableUnits.indexOf(automaticFirstUnit)
        const currentIndex = availableUnits.indexOf(firstVisibleUnit)
        const collapsedIndex = collapsedBeforeUnit ? availableUnits.indexOf(collapsedBeforeUnit) : 0
        const allowedAutomaticIndex = Math.max(automaticIndex, Math.max(0, collapsedIndex))
        return availableUnits[Math.min(currentIndex, allowedAutomaticIndex)]
    }

    const onFocus = (unit: TimeUnit): FocusEventHandler<HTMLInputElement> => (event) => {
        event.currentTarget.select()
        justFocusedUnit.current = unit
    }

    const onMouseUp = (unit: TimeUnit): MouseEventHandler<HTMLInputElement> => (event) => {
        if (justFocusedUnit.current !== unit) return
        event.preventDefault()
        justFocusedUnit.current = null
    }

    const onUnitChange = (unit: TimeUnit): ChangeEventHandler<HTMLInputElement> => (event) => {
        const rawValue = event.currentTarget.value
        const nextDraft = {...draftParts, [unit]: rawValue}
        const total = valueFromDraft(nextDraft)
        const normalizedFirstUnit = firstUnitForTotal(total)

        setFirstVisibleUnit(normalizedFirstUnit)
        if (rawValue.trim() !== '' && Number.isFinite(total)) {
            setDraftParts(normalizeDraft(nextDraft, total, normalizedFirstUnit, unit))
        } else {
            setDraftParts(nextDraft)
        }

        lastEmittedValue.current = total
        onChange(total)
    }

    const addLargerUnit = () => {
        if (!nextLargerUnit) return

        const total = valueFromDraft(draftParts)
        setFirstVisibleUnit(nextLargerUnit)
        if (collapsedBeforeUnit) {
            const addedIndex = availableUnits.indexOf(nextLargerUnit)
            setCollapsedBeforeUnit(addedIndex === 0 ? null : nextLargerUnit)
        }
        if (Number.isFinite(total)) {
            setDraftParts(normalizeDraft(draftParts, total, nextLargerUnit))
        }
    }

    const removeCoarsestUnit = () => {
        if (!canRemoveCoarsestUnit) return

        const nextFirstUnit = visibleUnits[1]
        const total = valueFromDraft(draftParts)
        setRemoveControlVisible(false)
        setCollapsedBeforeUnit(nextFirstUnit)
        setFirstVisibleUnit(nextFirstUnit)

        if (Number.isFinite(total)) {
            setDraftParts(normalizeDraft(draftParts, total, nextFirstUnit))
            lastEmittedValue.current = total
            onChange(total)
        }
    }

    return (
        <div className={['time-interval', className].filter(Boolean).join(' ')} style={style}>
            {visibleUnits.map((unit, index) => {
                const isCoarsestUnit = index === 0
                return (
                    <div
                        key={unit}
                        style={{display: 'inline-flex', alignItems: 'center', gap: 8}}
                        onMouseEnter={() => {
                            if (isCoarsestUnit && canRemoveCoarsestUnit) setRemoveControlVisible(true)
                        }}
                        onMouseLeave={() => {
                            if (isCoarsestUnit) setRemoveControlVisible(false)
                        }}
                    >
                        {index > 0 ? <span className="time-interval-sep" aria-hidden="true">:</span> : null}
                        <div className="time-interval-field">
                            <input
                                id={`${baseId}-${unit}`}
                                className="input"
                                type="number"
                                inputMode={unit === backendUnit && !Number.isInteger(step) ? 'decimal' : 'numeric'}
                                min={0}
                                step={unit === backendUnit ? step : 1}
                                value={draftParts[unit]}
                                style={unit === 'minutes' || unit === 'seconds' ? {textAlign: 'left'} : undefined}
                                onChange={onUnitChange(unit)}
                                onFocus={onFocus(unit)}
                                onMouseUp={onMouseUp(unit)}
                                disabled={disabled}
                                aria-label={UNIT_LABELS[unit]}
                                aria-invalid={ariaInvalid || undefined}
                                aria-describedby={ariaDescribedBy}
                            />
                            <span className="time-interval-unit" aria-hidden="true">{UNIT_LABELS[unit]}</span>
                            {isCoarsestUnit && canRemoveCoarsestUnit ? (
                                <button
                                    type="button"
                                    onClick={removeCoarsestUnit}
                                    onFocus={() => setRemoveControlVisible(true)}
                                    onBlur={() => setRemoveControlVisible(false)}
                                    aria-label={`Remove ${UNIT_LABELS[unit]} input`}
                                    title={`Remove ${UNIT_LABELS[unit]}`}
                                    style={{
                                        position: 'absolute',
                                        top: 3,
                                        right: 3,
                                        zIndex: 1,
                                        display: 'grid',
                                        width: 16,
                                        height: 16,
                                        padding: 0,
                                        placeItems: 'center',
                                        border: 0,
                                        borderRadius: 4,
                                        background: 'var(--bg)',
                                        color: 'var(--muted)',
                                        font: 'inherit',
                                        fontSize: 13,
                                        lineHeight: 1,
                                        cursor: 'pointer',
                                        opacity: removeControlVisible ? 1 : 0,
                                        pointerEvents: removeControlVisible ? 'auto' : 'none',
                                    }}
                                >
                                    ×
                                </button>
                            ) : null}
                        </div>
                    </div>
                )
            })}
            {nextLargerUnit ? (
                <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={addLargerUnit}
                    disabled={disabled}
                    aria-label={`Add ${UNIT_LABELS[nextLargerUnit]} input`}
                    title={`Add ${UNIT_LABELS[nextLargerUnit]}`}
                >
                    + {UNIT_LABELS[nextLargerUnit]}
                </button>
            ) : null}
        </div>
    )
}

export {TimeInterval}
