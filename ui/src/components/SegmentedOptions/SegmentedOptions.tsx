import {CSSProperties, ReactNode, useId, useLayoutEffect, useRef, useState} from 'react'

export type SegmentedOptionValue = string | number

export type SegmentedOption<T extends SegmentedOptionValue = SegmentedOptionValue> = {
  value: T
  label: ReactNode
  /** Optional explanation text shown below the label. Can include <ReadMore> blocks. */
  description?: ReactNode
  disabled?: boolean
}

export type SegmentedOptionsProps<T extends SegmentedOptionValue = SegmentedOptionValue> = {
  /** Name for the underlying radios/checkboxes */
  name: string
  /** Controlled value: single value for radio mode, array for multi-select mode */
  value: T | T[] | null | undefined
  /** Change handler returns the selected value(s) */
  onChange: (value: T | T[]) => void
  /** Available options */
  options: SegmentedOption<T>[]
  /** Enable multi-select. When true, at least one option must remain selected. */
  multiple?: boolean
  /** Optional aria-label for the group */
  ariaLabel?: string
  /** Optional aria-labelledby id for the group */
  ariaLabelledBy?: string
  /** Disable the entire group */
  disabled?: boolean
  /** Optional className for the root */
  className?: string
  /** Optional style for the root */
  style?: CSSProperties
}

/**
 * SegmentedOptions — a modern, accessible segmented control.
 * - Single-select radio mode (default)
 * - Multi-select checkbox mode (set multiple=true). Enforces at least one selected.
 * - Supports an optional description under each label (can include <ReadMore>)
 *
 * Accessibility:
 * - Uses native input elements for correct semantics
 * - Group uses role="radiogroup" for single-select, and role="group" for multi-select
 */
export default function SegmentedOptions<T extends SegmentedOptionValue = SegmentedOptionValue>({
  name,
  value,
  onChange,
  options,
  multiple,
  ariaLabel,
  ariaLabelledBy,
  disabled,
  className,
  style,
}: SegmentedOptionsProps<T>) {
  const autoId = useId()
  const groupId = `${name}-seg-${autoId}`
  const count = options.length

  const isMulti = !!multiple
  const valuesArray: T[] = Array.isArray(value) ? (value as T[]) : (value == null ? [] : [value as T])

  const selectedIndex = !isMulti && value != null ? options.findIndex(o => o.value === value) : -1
  const indicatorWidth = count > 0 ? `${100 / count}%` : '0%'
  const translateX = selectedIndex <= -1 ? -1 : selectedIndex

  // Options share the width equally only while every label fits; a longer label makes its
  // option wider. So the selection follows the selected option's measured box.
  const rootRef = useRef<HTMLDivElement>(null)
  const optionRefs = useRef<(HTMLLabelElement | null)[]>([])
  const [measured, setMeasured] = useState<{left: number; width: number} | null>(null)
  useLayoutEffect(() => {
    if (isMulti || selectedIndex < 0) return
    const measure = () => {
      const option = optionRefs.current[selectedIndex]
      if (!option) return
      setMeasured((previous) => (
        previous && previous.left === option.offsetLeft && previous.width === option.offsetWidth
          ? previous
          : {left: option.offsetLeft, width: option.offsetWidth}
      ))
    }
    measure()
    if (typeof ResizeObserver === 'undefined' || !rootRef.current) return
    const observer = new ResizeObserver(measure)
    observer.observe(rootRef.current)
    return () => observer.disconnect()
  }, [isMulti, selectedIndex, count])

  return (
    <div
      role={isMulti ? 'group' : 'radiogroup'}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabel ? undefined : ariaLabelledBy}
      aria-disabled={disabled || undefined}
      ref={rootRef}
      className={`segmented-options ${className ?? ''}`.trim()}
      style={style}
      data-disabled={disabled ? '' : undefined}
      data-count={count}
      data-multi={isMulti ? '' : undefined}
    >
      {/* Sliding selection background for single-select only */}
      {!isMulti && count > 0 && (
        <div
          className="segmented-selection"
          style={{
            width: measured ? `${measured.width}px` : indicatorWidth,
            transform: measured ? `translateX(${measured.left}px)` : `translateX(${translateX * 100}%)`,
            opacity: selectedIndex === -1 ? 0 : 1,
          }}
          aria-hidden
        />
      )}

      {/* Grid items */}
      {options.map((opt, idx) => {
        const checked = isMulti ? valuesArray.includes(opt.value) : value === opt.value
        const optDisabled = disabled || opt.disabled
        const inputId = `${groupId}-${idx}`
        return (
          <label
            key={String(opt.value)}
            ref={(element) => { optionRefs.current[idx] = element }}
            className={`segmented-option${checked ? ' is-checked' : ''}`}
            data-checked={checked ? '' : undefined}
            data-disabled={optDisabled ? '' : undefined}
          >
            <input
              type={isMulti ? 'checkbox' : 'radio'}
              name={name}
              id={inputId}
              value={String(opt.value)}
              checked={checked}
              onChange={() => {
                if (optDisabled) return
                if (!isMulti) {
                  onChange(opt.value)
                  return
                }
                // Multi-select toggle logic with at least one selected
                const isSelected = valuesArray.includes(opt.value)
                if (isSelected) {
                  if (valuesArray.length <= 1) {
                    // Enforce at least one remains selected
                    return
                  }
                  const next = valuesArray.filter(v => v !== opt.value)
                  onChange(next as T[])
                } else {
                  const next = [...valuesArray, opt.value]
                  onChange(next as T[])
                }
              }}
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
