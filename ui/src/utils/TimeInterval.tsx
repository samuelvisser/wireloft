import { useEffect, useId, useMemo, useState } from 'react'

export type TimeIntervalProps = {
  value: string // total minutes as string (can be empty)
  onChange: (totalMinutes: string) => void
  idPrefix?: string
  disabled?: boolean
  className?: string
  style?: React.CSSProperties
  hoursLabel?: string
  minutesLabel?: string
}

function splitMinutes(totalStr: string): { hours: number; minutes: number } {
  const n = parseInt(totalStr, 10)
  if (!isFinite(n) || isNaN(n) || n < 0) return { hours: 0, minutes: 0 }
  const hours = Math.floor(n / 60)
  const minutes = n % 60
  return { hours, minutes }
}

function clampNonNegative(n: number) { return isFinite(n) && !isNaN(n) && n > 0 ? Math.floor(n) : 0 }

export default function TimeInterval({
  value,
  onChange,
  idPrefix,
  disabled,
  className,
  style,
  hoursLabel = 'hours',
  minutesLabel = 'minutes',
}: TimeIntervalProps) {
  const autoId = useId()
  const baseId = idPrefix ?? `ti-${autoId}`

  const initial = useMemo(() => splitMinutes(value), [value])
  const [hours, setHours] = useState<number>(initial.hours)
  const [minutes, setMinutes] = useState<number>(initial.minutes)

  // Keep local state in sync if parent value changes externally
  useEffect(() => {
    setHours(initial.hours)
    setMinutes(initial.minutes)
  }, [initial.hours, initial.minutes])

  const emit = (h: number, m: number) => {
    // Normalize overflow minutes into hours
    if (m >= 60) {
      h += Math.floor(m / 60)
      m = m % 60
    }
    if (h < 0) h = 0
    if (m < 0) m = 0

    const total = h * 60 + m
    if (total === 0) {
      if (value.trim() === '') {
        onChange('')
      } else {
        onChange('0')
      }
    } else {
      onChange(String(total))
    }
  }

  const onHoursChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const v = e.target.value
    if (v.trim() === '') {
      setHours(0)
      emit(0, minutes)
      return
    }
    const n = clampNonNegative(parseInt(v, 10))
    setHours(n)
    emit(n, minutes)
  }

  const onMinutesChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const v = e.target.value
    if (v.trim() === '') {
      setMinutes(0)
      emit(hours, 0)
      return
    }
    const n = clampNonNegative(parseInt(v, 10))
    setMinutes(n)
    emit(hours, n)
  }

  const onMinutesBlur: React.FocusEventHandler<HTMLInputElement> = () => {
    // Normalize minutes overflow on blur for visual consistency
    if (minutes >= 60) {
      const h = hours + Math.floor(minutes / 60)
      const m = minutes % 60
      setHours(h)
      setMinutes(m)
      emit(h, m)
    }
  }

  return (
    <div className={["time-interval", className].filter(Boolean).join(' ')} style={style}>
      <div className="time-interval-field">
        <input
          id={`${baseId}-h`}
          className="input"
          type="number"
          inputMode="numeric"
          min={0}
          step={1}
          value={hours}
          onChange={onHoursChange}
          onFocus={(e) => { e.target.select() }}
          onMouseUp={(e) => { e.preventDefault(); }}
          disabled={disabled}
          aria-label={hoursLabel}
        />
        <span className="time-interval-unit" aria-hidden="true">{hoursLabel}</span>
      </div>
      <span className="time-interval-sep" aria-hidden="true">:</span>
      <div className="time-interval-field">
        <input
          id={`${baseId}-m`}
          className="input"
          type="number"
          inputMode="numeric"
          min={0}
          step={1}
          value={minutes}
          onChange={onMinutesChange}
          onBlur={onMinutesBlur}
          onFocus={(e) => { e.target.select() }}
          onMouseUp={(e) => { e.preventDefault(); }}
          disabled={disabled}
          aria-label={minutesLabel}
        />
        <span className="time-interval-unit" aria-hidden="true">{minutesLabel}</span>
      </div>
    </div>
  )
}

export { TimeInterval }