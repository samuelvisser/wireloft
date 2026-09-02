import {useEffect, useMemo, useState} from 'react'
import Select from 'react-select'

import './CronEditor.css'


type CronEditorProps = {
    id: string
    label: string
    value: string
    onChange: (value: string) => void
    environmentVariable?: string
    help?: string
    error?: string
}

type CronMode = 'minutes' | 'hourly' | 'hours' | 'daily' | 'weekly' | 'monthly' | 'custom'
type StructuredCronMode = Exclude<CronMode, 'custom'>

type ParsedCron = {
    minute: string
    hour: string
    dayOfMonth: string
    month: string
    dayOfWeek: string
}

const EMPTY_CRON_VALUE = '_'

const WEEKDAYS = [
    {value: '1', label: 'Monday'},
    {value: '2', label: 'Tuesday'},
    {value: '3', label: 'Wednesday'},
    {value: '4', label: 'Thursday'},
    {value: '5', label: 'Friday'},
    {value: '6', label: 'Saturday'},
    {value: '0', label: 'Sunday'},
] as const

type WeekdayOption = (typeof WEEKDAYS)[number]

const MODES: ReadonlyArray<{value: CronMode; label: string}> = [
    {value: 'minutes', label: 'Every X minutes'},
    {value: 'hourly', label: 'Hourly'},
    {value: 'hours', label: 'Every X hours'},
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

function isNumberOrEmpty(value: string) {
    return /^\d+$/.test(value) || value === EMPTY_CRON_VALUE
}

function isWeekdayList(value: string): boolean {
    const values = value.split(',')
    if (!values.length || new Set(values).size !== values.length) return false
    return values.every((weekday) => WEEKDAYS.some((option) => option.value === weekday))
}

function selectedWeekdays(value: string | undefined): WeekdayOption[] {
    if (!value || !isWeekdayList(value)) return []
    const selected = new Set(value.split(','))
    return WEEKDAYS.filter((weekday) => selected.has(weekday.value))
}

function describeWeekdays(value: string): string {
    const labels = selectedWeekdays(value).map((weekday) => weekday.label)
    if (!labels.length) return 'selected weekdays'
    if (labels.length === 1) return labels[0]
    if (labels.length === 2) return `${labels[0]} and ${labels[1]}`
    return `${labels.slice(0, -1).join(', ')} and ${labels[labels.length - 1]}`
}

function inferMode(value: string): CronMode {
    const parsed = parseCron(value)
    if (!parsed) return 'custom'
    const {minute, hour, dayOfMonth, month, dayOfWeek} = parsed

    if (/^\*\/(?:\d+|_)$/.test(minute) && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
        return 'minutes'
    }
    if (isNumberOrEmpty(minute) && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
        return 'hourly'
    }
    if (
        isNumberOrEmpty(minute)
        && /^\*\/(?:\d+|_)$/.test(hour)
        && dayOfMonth === '*'
        && month === '*'
        && dayOfWeek === '*'
    ) {
        return 'hours'
    }
    if (isNumberOrEmpty(minute) && isNumberOrEmpty(hour) && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
        return 'daily'
    }
    if (
        isNumberOrEmpty(minute)
        && isNumberOrEmpty(hour)
        && dayOfMonth === '*'
        && month === '*'
        && (dayOfWeek === EMPTY_CRON_VALUE || isWeekdayList(dayOfWeek))
    ) {
        return 'weekly'
    }
    if (isNumberOrEmpty(minute) && isNumberOrEmpty(hour) && isNumberOrEmpty(dayOfMonth) && month === '*' && dayOfWeek === '*') {
        return 'monthly'
    }
    return 'custom'
}

function clamp(value: number, min: number, max: number) {
    return Math.min(max, Math.max(min, value))
}

function numberOrEmpty(value: string | undefined, min: number, max: number): number | '' {
    if (!value || !/^\d+$/.test(value)) return ''
    return clamp(Number(value), min, max)
}

function CronNumberInput({
    value,
    min,
    max,
    disabled,
    onChange,
}: {
    value: number | ''
    min: number
    max: number
    disabled: boolean
    onChange: (value: number | null) => void
}) {
    return (
        <input
            className="input settings-input"
            type="number"
            min={min}
            max={max}
            disabled={disabled}
            value={value}
            onChange={(event) => {
                if (event.currentTarget.value === '') {
                    onChange(null)
                    return
                }

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
        case 'hours': {
            const every = parsed?.hour.match(/^\*\/(\d+)$/)?.[1] ?? '6'
            return `${minute} */${clamp(Number(every) || 6, 1, 23)} * * *`
        }
        case 'daily':
            return `${minute} ${hour} * * *`
        case 'weekly': {
            const weekdays = parsed && isWeekdayList(parsed.dayOfWeek) ? parsed.dayOfWeek : '1'
            return `${minute} ${hour} * * ${weekdays}`
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
    if (Object.values(parsed).some((part) => part.includes(EMPTY_CRON_VALUE))) {
        return 'Complete the schedule before saving.'
    }

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
        case 'hours': {
            const every = parsed.hour.match(/^\*\/(\d+)$/)?.[1]
            if (!every) return 'Recurring hour interval schedule.'
            return Number(every) === 1
                ? `Every hour at minute ${parsed.minute}.`
                : `Every ${every} hours at minute ${parsed.minute}.`
        }
        case 'daily':
            return `Every day at ${time}.`
        case 'weekly':
            return `Every ${describeWeekdays(parsed.dayOfWeek)} at ${time}.`
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
    error,
}: CronEditorProps) {
    const [mode, setMode] = useState<CronMode>(() => inferMode(value))
    const parsed = useMemo(() => parseCron(value), [value])
    const weekdayValues = useMemo(() => selectedWeekdays(parsed?.dayOfWeek), [parsed?.dayOfWeek])
    const disabled = Boolean(environmentVariable)
    const errorId = `${id}-errors`

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

    const hour = numberOrEmpty(parsed?.hour, 0, 23)
    const minute = numberOrEmpty(parsed?.minute, 0, 59)
    const timeValue = hour === '' || minute === ''
        ? ''
        : `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`

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
                                        value={numberOrEmpty(parsed?.minute.match(/^\*\/(\d+|_)$/)?.[1], 1, 59)}
                                        min={1}
                                        max={59}
                                        disabled={disabled}
                                        onChange={(every) => onChange(`*/${every ?? EMPTY_CRON_VALUE} * * * *`)}
                                    />
                                    <span>minutes</span>
                                </div>
                            </label>
                        ) : null}

                        {mode === 'hours' ? (
                            <label>
                                <span>Interval</span>
                                <div className="cron-editor__inline-input">
                                    <CronNumberInput
                                        value={numberOrEmpty(parsed?.hour.match(/^\*\/(\d+|_)$/)?.[1], 1, 23)}
                                        min={1}
                                        max={23}
                                        disabled={disabled}
                                        onChange={(every) => updateParts({
                                            hour: `*/${every ?? EMPTY_CRON_VALUE}`,
                                        })}
                                    />
                                    <span>hours</span>
                                </div>
                            </label>
                        ) : null}

                        {mode === 'hourly' || mode === 'hours' ? (
                            <label>
                                <span>Minute past the hour</span>
                                <CronNumberInput
                                    value={minute}
                                    min={0}
                                    max={59}
                                    disabled={disabled}
                                    onChange={(nextMinute) => updateParts({minute: nextMinute === null ? EMPTY_CRON_VALUE : String(nextMinute)})}
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
                                    value={timeValue}
                                    onChange={(event) => {
                                        if (event.currentTarget.value === '') {
                                            updateParts({hour: EMPTY_CRON_VALUE, minute: EMPTY_CRON_VALUE})
                                            return
                                        }
                                        const [nextHour, nextMinute] = event.currentTarget.value.split(':')
                                        updateParts({hour: String(Number(nextHour)), minute: String(Number(nextMinute))})
                                    }}
                                />
                            </label>
                        ) : null}

                        {mode === 'weekly' ? (
                            <label>
                                <span>Days</span>
                                <Select<WeekdayOption, true>
                                    inputId={`${id}-weekdays`}
                                    className="cron-editor__weekday-select"
                                    classNamePrefix="select"
                                    isMulti
                                    isDisabled={disabled}
                                    closeMenuOnSelect={false}
                                    hideSelectedOptions={false}
                                    options={WEEKDAYS}
                                    value={weekdayValues}
                                    placeholder="Select one or more days"
                                    getOptionValue={(option) => option.value}
                                    getOptionLabel={(option) => option.label}
                                    styles={{menu: (base) => ({...base, zIndex: 20})}}
                                    onChange={(days) => updateParts({
                                        dayOfWeek: days.length
                                            ? days.map((day) => day.value).join(',')
                                            : EMPTY_CRON_VALUE,
                                    })}
                                />
                            </label>
                        ) : null}

                        {mode === 'monthly' ? (
                            <label>
                                <span>Day of month</span>
                                <CronNumberInput
                                    value={numberOrEmpty(parsed?.dayOfMonth, 1, 31)}
                                    min={1}
                                    max={31}
                                    disabled={disabled}
                                    onChange={(dayOfMonth) => updateParts({
                                        dayOfMonth: dayOfMonth === null ? EMPTY_CRON_VALUE : String(dayOfMonth),
                                    })}
                                />
                            </label>
                        ) : null}
                    </div>
                ) : null}

                <div className={`cron-editor__expression${error ? ' is-invalid' : ''}`}>
                    <label htmlFor={`${id}-expression`}>Cron expression</label>
                    <input
                        id={`${id}-expression`}
                        className="input settings-input cron-editor__code"
                        value={value}
                        disabled={disabled}
                        spellCheck={false}
                        aria-invalid={Boolean(error)}
                        aria-describedby={error ? errorId : undefined}
                        onChange={(event) => {
                            const nextValue = event.currentTarget.value
                            onChange(nextValue)
                            setMode(inferMode(nextValue))
                        }}
                    />
                    <div className="cron-editor__description">{describeCron(value)}</div>
                    {error ? (
                        <div id={errorId} className="error" role="alert" aria-live="polite">
                            {error}
                        </div>
                    ) : null}
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
