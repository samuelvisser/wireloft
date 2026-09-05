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

function splitValue(value: number, backendUnit: TimeUnit): TimeUnitValues {
    const parts: TimeUnitValues = {
        days: 0,
        hours: 0,
        minutes: 0,
        seconds: 0,
        milliseconds: 0,
    }
    let remaining = Number.isFinite(value) && value > 0 ? value : 0

    for (const unit of unitsForBackendUnit(backendUnit)) {
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
    const availableUnits = useMemo(() => unitsForBackendUnit(backendUnit), [backendUnit])
    const automaticallyVisibleUnits = useMemo(
        () => visibleUnitsForValue(value, backendUnit),
        [backendUnit, value],
    )
    const [firstVisibleUnit, setFirstVisibleUnit] = useState<TimeUnit>(automaticallyVisibleUnits[0])
    const [draftParts, setDraftParts] = useState<TimeUnitDraft>(() => toDraft(splitValue(value, backendUnit)))

    useEffect(() => {
        if (previousBackendUnit.current !== backendUnit) {
            previousBackendUnit.current = backendUnit
            setFirstVisibleUnit(automaticallyVisibleUnits[0])
            setDraftParts(toDraft(splitValue(value, backendUnit)))
            return
        }

        const automaticFirstUnit = automaticallyVisibleUnits[0]
        setFirstVisibleUnit((currentFirstUnit) => {
            const currentIndex = availableUnits.indexOf(currentFirstUnit)
            const automaticIndex = availableUnits.indexOf(automaticFirstUnit)
            if (currentIndex < 0 || automaticIndex < currentIndex) return automaticFirstUnit
            return currentFirstUnit
        })

        // NaN is the form's temporary incomplete state. Keep the user's raw input
        // intact until every visible field has a value again.
        if (Number.isFinite(value)) {
            setDraftParts(toDraft(splitValue(value, backendUnit)))
        }
    }, [automaticallyVisibleUnits, availableUnits, backendUnit, value])

    const firstVisibleIndex = Math.max(0, availableUnits.indexOf(firstVisibleUnit))
    const visibleUnits = availableUnits.slice(firstVisibleIndex)
    const nextLargerUnit = firstVisibleIndex > 0 ? availableUnits[firstVisibleIndex - 1] : null

    const emitDraft = (nextDraft: TimeUnitDraft) => {
        let total = 0

        for (const unit of availableUnits) {
            const rawValue = nextDraft[unit].trim()
            if (rawValue === '') {
                onChange(Number.NaN)
                return
            }

            const parsed = Number(rawValue)
            if (!Number.isFinite(parsed) || parsed < 0) {
                onChange(Number.NaN)
                return
            }

            total += parsed * backendUnitsPerDisplayUnit(unit, backendUnit)
        }

        onChange(roundValue(total))
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
        const nextDraft = {...draftParts, [unit]: event.currentTarget.value}
        setDraftParts(nextDraft)
        emitDraft(nextDraft)
    }

    const addLargerUnit = () => {
        if (!nextLargerUnit) return
        setFirstVisibleUnit(nextLargerUnit)
    }

    return (
        <div className={['time-interval', className].filter(Boolean).join(' ')} style={style}>
            {visibleUnits.map((unit, index) => (
                <div key={unit} style={{display: 'inline-flex', alignItems: 'center', gap: 8}}>
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
                            onChange={onUnitChange(unit)}
                            onFocus={onFocus(unit)}
                            onMouseUp={onMouseUp(unit)}
                            disabled={disabled}
                            aria-label={UNIT_LABELS[unit]}
                            aria-invalid={ariaInvalid || undefined}
                            aria-describedby={ariaDescribedBy}
                        />
                        <span className="time-interval-unit" aria-hidden="true">{UNIT_LABELS[unit]}</span>
                    </div>
                </div>
            ))}
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
