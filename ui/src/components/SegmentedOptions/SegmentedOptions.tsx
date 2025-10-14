import {CSSProperties, ReactNode, useId} from 'react'

export type SegmentedOptionValue = string | number

export type SegmentedOption<T extends SegmentedOptionValue = SegmentedOptionValue> = {
  value: T
  label: ReactNode
  /** Optional explanation text shown below the label. Can include <ReadMore> blocks. */
  description?: ReactNode
  disabled?: boolean
}

export type SegmentedOptionsProps<T extends SegmentedOptionValue = SegmentedOptionValue> = {
  /** Name for the underlying radios */
  name: string
  /** Controlled value */
  value: T | null | undefined
  /** Change handler returns the selected value */
  onChange: (value: T) => void
  /** Available options */
  options: SegmentedOption<T>[]
  /** Optional aria-label for the radiogroup */
  ariaLabel?: string
  /** Optional aria-labelledby id for the radiogroup */
  ariaLabelledBy?: string
  /** Disable the entire group */
  disabled?: boolean
  /** Optional className for the root */
  className?: string
  /** Optional style for the root */
  style?: CSSProperties
}

/**
 * SegmentedOptions — a modern, accessible radio-like segmented control.
 * - Renders equal-width horizontal segments with separators
 * - Smooth animated background slides to the selected option
 * - Supports an optional description under each label (can include <ReadMore>)
 *
 * Accessibility:
 * - Uses native input type="radio" elements for correct semantics
 * - Group is wrapped with role="radiogroup"
 */
export default function SegmentedOptions<T extends SegmentedOptionValue = SegmentedOptionValue>({
  name,
  value,
  onChange,
  options,
  ariaLabel,
  ariaLabelledBy,
  disabled,
  className,
  style,
}: SegmentedOptionsProps<T>) {
  const autoId = useId()
  const groupId = `${name}-seg-${autoId}`
  const count = options.length

  const selectedIndex = value == null ? -1 : options.findIndex(o => o.value === value)
  const indicatorWidth = count > 0 ? `${100 / count}%` : '0%'
  const translateX = selectedIndex <= -1 ? -1 : selectedIndex

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      aria-labelledby={ariaLabel ? undefined : ariaLabelledBy}
      aria-disabled={disabled || undefined}
      className={`segmented-options ${className ?? ''}`.trim()}
      style={style}
      data-disabled={disabled ? '' : undefined}
      data-count={count}
    >
      {/* Sliding selection background */}
      {count > 0 && (
        <div
          className="segmented-selection"
          style={{
            width: indicatorWidth,
            transform: `translateX(${translateX * 100}%)`,
            opacity: selectedIndex === -1 ? 0 : 1,
          }}
          aria-hidden
        />
      )}

      {/* Grid items */}
      {options.map((opt, idx) => {
        const checked = value === opt.value
        const optDisabled = disabled || opt.disabled
        const inputId = `${groupId}-${idx}`
        return (
          <label
            key={String(opt.value)}
            className={`segmented-option${checked ? ' is-checked' : ''}`}
            data-checked={checked ? '' : undefined}
            data-disabled={optDisabled ? '' : undefined}
          >
            <input
              type="radio"
              name={name}
              id={inputId}
              value={String(opt.value)}
              checked={checked}
              onChange={() => !optDisabled && onChange(opt.value)}
              disabled={optDisabled}
            />
            <div className="segmented-content">
              <div className="segmented-label">{opt.label}</div>
              {opt.description && (
                <div className="segmented-desc">
                  {opt.description}
                </div>
              )}
            </div>
          </label>
        )
      })}
    </div>
  )
}

export { SegmentedOptions }

/** Helper to quickly build options from key–value pairs */
export function toSegmentedOptions<T extends SegmentedOptionValue>(
  input: ReadonlyArray<[T, ReactNode]> | Record<string, ReactNode>
): SegmentedOption<T>[] {
  if (Array.isArray(input)) {
    return input.map(([value, label]) => ({ value, label })) as SegmentedOption<T>[]
  }
  return Object.entries(input).map(([key, label]) => ({ value: key as T, label }))
}
