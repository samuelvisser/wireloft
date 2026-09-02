import {useEffect, useMemo, useState} from 'react'

import './CronEditor.css'


type CronEditorProps = {
    id: string
    label: string
    value: string
    onChange: (value: string) => void
    environmentVariable?: string
    help?: string
}

type CronMode = 'minutes' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'custom'
type StructuredCronMode = Exclude<CronMode, 'custom'>

type ParsedCron = {
    minute: string
    hour: string
    dayOfMonth: string
    month: string
    dayOfWeek: string
}

const WEEKDAYS = [
    {value: '1', label: 'Monday'},
    {value: '2', label: 'Tuesday'},
    {value: '3', label: 'Wednesday'},
    {value: '4', label: 'Thursday'},
    {value: '5', label: 'Friday'},
    {value: '6', label: 'Saturday'},
    {value: '0', label: 'Sunday'},
] as const

const MODES: ReadonlyArray<{value: CronMode; label: string}> = [
    {value: 'minutes', label: 'Every X minutes'},
    {value: 'hourly', label: 'Hourly'},
    {value: 'daily', label: 'Daily'},
    {value: 'weekly', label: 'Weekly'},
    {value: 'monthly', label: 'Monthly'},
    {value: 'custom', label: 'Custom'},
]

function parseCron(value: string): ParsedCron | null {
    const parts = value.trim().split(/\s+/)
    if (parts.length !== 5) return null
    const [minute, hour, dayOfMonth, month, dayOfWeek] = parts
    return {minute, hour, dayOfMonth, month, dayOfWeek}
}

function inferMode(value: string): CronMode {
    const parsed = parseCron(value)
    if (!parsed) return 'custom'
    const {minute, hour, dayOfMonth, month, dayOfWeek} = parsed

    if (/^\*\/\d+$/.test(minute) && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
        return 'minutes'
    }
    if (/^\d+$/.test(minute) && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
        return 'hourly'
    }
    if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
        return 'daily'
    }
    if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && dayOfMonth === '*' && month === '*' && /^\d+$/.test(dayOfWeek)) {
        return 'weekly'
    }
    if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && /^\d+$/.test(dayOfMonth) && month === '*' && dayOfWeek === '*') {
        return 'monthly'
    }
    return 'custom'
}

function clamp(value: number, min: number, max: number) {
    return Math.min(max, Math.max(min, value))
}

function CronNumberInput({
    value,
    min,
    max,
    disabled,
    onChange,
}: {
    value: number
    min: number
    max: number
    disabled: boolean
    onChange: (value: number) => void
}) {
    const [rawValue, setRawValue] = useState(String(value))

    useEffect(() => {
        setRawValue(String(value))
    }, [value])

    return (
        <input
            className="input settings-input"
            type="number"
            min={min}
            max={max}
            disabled={disabled}
            value={rawValue}
            onChange={(event) => {
                const nextRawValue = event.currentTarget.value
                setRawValue(nextRawValue)
                if (nextRawValue === '') return

                const nextValue = event.currentTarget.valueAsNumber
                if (!Number.isFinite(nextValue)) return
                onChange(clamp(nextValue, min, max))
            }}
        />
    )
}

function cronForMode(mode: StructuredCronMode, parsed: ParsedCron | null): string {
    const minute = clamp(Number(parsed?.minute) || 0, 0, 59)
    const hour = clamp(Number(parsed?.hour) || 0, 0, 23)

    switch (mode) {
        case 'minutes': {
            const every = parsed?.minute.match(/^\*\/(\d+)$/)?.[1] ?? '30'
            return `*/${clamp(Number(every) || 30, 1, 59)} * * * *`
        }
        case 'hourly':
            return `${minute} * * * *`
        case 'daily':
            return `${minute} ${hour} * * *`
        case 'weekly': {
            const weekday = /^\d+$/.test(parsed?.dayOfWeek ?? '') ? parsed!.dayOfWeek : '1'
            return `${minute} ${hour} * * ${weekday}`
        }
        case 'monthly': {
            const day = clamp(Number(parsed?.dayOfMonth) || 1, 1, 31)
            return `${minute} ${hour} ${day} * *`
        }
    }
}

function describeCron(value: string): string {
    const parsed = parseCron(value)
    if (!parsed) return 'Enter exactly five cron fields: minute, hour, day, month and weekday.'

    const mode = inferMode(value)
    const minute = Number(parsed.minute)
    const hour = Number(parsed.hour)
    const time = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`

    switch (mode) {
        case 'minutes': {
            const every = parsed.minute.match(/^\*\/(\d+)$/)?.[1]
            return every ? `Every ${every} minutes.` : 'Recurring minute schedule.'
        }
        case 'hourly':
            return `Every hour at minute ${parsed.minute}.`
        case 'daily':
            return `Every day at ${time}.`
        case 'weekly': {
            const weekday = WEEKDAYS.find((day) => day.value === parsed.dayOfWeek)?.label ?? `weekday ${parsed.dayOfWeek}`
            return `Every ${weekday} at ${time}.`
        }
        case 'monthly':
            return `Every month on day ${parsed.dayOfMonth} at ${time}.`
        case 'custom':
            return 'Custom five-part cron expression.'
    }
}

export default function CronEditor({
    id,
    label,
    value,
    onChange,
    environmentVariable,
    help = 'Schedules use WireLoft’s configured timezone.',
}: CronEditorProps) {
    const [mode, setMode] = useState<CronMode>(() => inferMode(value))
    const parsed = useMemo(() => parseCron(value), [value])
    const disabled = Boolean(environmentVariable)

    useEffect(() => {
        setMode(inferMode(value))
    }, [value])

    const setStructuredMode = (nextMode: StructuredCronMode) => {
        setMode(nextMode)
        onChange(cronForMode(nextMode, parsed))
    }

    const updateParts = (next: Partial<ParsedCron>) => {
        const fallbackMode: StructuredCronMode = mode === 'custom' ? 'daily' : mode
        const current = parseCron(value) ?? parseCron(cronForMode(fallbackMode, null))!
        onChange([
            next.minute ?? current.minute,
            next.hour ?? current.hour,
            next.dayOfMonth ?? current.dayOfMonth,
            next.month ?? current.month,
            next.dayOfWeek ?? current.dayOfWeek,
        ].join(' '))
    }

    const hour = clamp(Number(parsed?.hour) || 0, 0, 23)
    const minute = clamp(Number(parsed?.minute) || 0, 0, 59)

    return (
        <div className={`settings-field settings-field--wide cron-editor${disabled ? ' is-environment-managed' : ''}`}>
            <label htmlFor={`${id}-expression`}>{label}</label>
            <div className="cron-editor__card">
                <div className="cron-editor__presets" role="group" aria-label={`${label} schedule type`}>
                    {MODES.map((option) => (
                        <button
                            key={option.value}
                            type="button"
                            className={`cron-editor__preset${mode === option.value ? ' is-active' : ''}`}
                            disabled={disabled}
                            onClick={() => {
                                if (option.value === 'custom') {
                                    setMode('custom')
                                } else {
                                    setStructuredMode(option.value)
                                }
                            }}
                        >
                            {option.label}
                        </button>
                    ))}
                </div>

                {mode !== 'custom' ? (
                    <div className="cron-editor__structured">
                        {mode === 'minutes' ? (
                            <label>
                                <span>Interval</span>
                                <div className="cron-editor__inline-input">
                                    <CronNumberInput
                                        value={Number(parsed?.minute.match(/^\*\/(\d+)$/)?.[1] ?? 30)}
                                        min={1}
                                        max={59}
                                        disabled={disabled}
                                        onChange={(every) => onChange(`*/${every} * * * *`)}
                                    />
                                    <span>minutes</span>
                                </div>
                            </label>
                        ) : null}

                        {mode === 'hourly' ? (
                            <label>
                                <span>Minute past the hour</span>
                                <CronNumberInput
                                    value={minute}
                                    min={0}
                                    max={59}
                                    disabled={disabled}
                                    onChange={(nextMinute) => updateParts({minute: String(nextMinute)})}
                                />
                            </label>
                        ) : null}

                        {mode === 'daily' || mode === 'weekly' || mode === 'monthly' ? (
                            <label>
                                <span>Time</span>
                                <input
                                    className="input settings-input"
                                    type="time"
                                    disabled={disabled}
                                    value={`${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`}
                                    onChange={(event) => {
                                        const [nextHour, nextMinute] = event.currentTarget.value.split(':')
                                        updateParts({hour: String(Number(nextHour)), minute: String(Number(nextMinute))})
                                    }}
                                />
                            </label>
                        ) : null}

                        {mode === 'weekly' ? (
                            <label>
                                <span>Day</span>
                                <select
                                    className="input settings-input settings-select"
                                    disabled={disabled}
                                    value={parsed?.dayOfWeek ?? '1'}
                                    onChange={(event) => updateParts({dayOfWeek: event.currentTarget.value})}
                                >
                                    {WEEKDAYS.map((day) => (
                                        <option key={day.value} value={day.value}>{day.label}</option>
                                    ))}
                                </select>
                            </label>
                        ) : null}

                        {mode === 'monthly' ? (
                            <label>
                                <span>Day of month</span>
                                <CronNumberInput
                                    value={clamp(Number(parsed?.dayOfMonth) || 1, 1, 31)}
                                    min={1}
                                    max={31}
                                    disabled={disabled}
                                    onChange={(dayOfMonth) => updateParts({dayOfMonth: String(dayOfMonth)})}
                                />
                            </label>
                        ) : null}
                    </div>
                ) : null}

                <div className={`cron-editor__expression${parsed ? '' : ' is-invalid'}`}>
                    <label htmlFor={`${id}-expression`}>Cron expression</label>
                    <input
                        id={`${id}-expression`}
                        className="input settings-input cron-editor__code"
                        value={value}
                        disabled={disabled}
                        spellCheck={false}
                        aria-invalid={!parsed}
                        onChange={(event) => {
                            const nextValue = event.currentTarget.value
                            onChange(nextValue)
                            setMode(inferMode(nextValue))
                        }}
                    />
                    <div className="cron-editor__description">{describeCron(value)}</div>
                    <div className="settings-field__help">{help}</div>
                </div>
            </div>
            {environmentVariable ? (
                <div className="settings-field__environment-note">
                    Managed by environment variable <code>{environmentVariable}</code>. Change or remove that environment override and restart WireLoft to edit this setting here.
                </div>
            ) : null}
        </div>
    )
}
