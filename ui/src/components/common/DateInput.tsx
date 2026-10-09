import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {forwardRef, useCallback, useRef, useState, type ComponentPropsWithoutRef} from 'react'
import {faIcon} from '../../icons/faIcon'
import './DateInput.css'

export type DateInputProps = Omit<ComponentPropsWithoutRef<'input'>, 'type' | 'value' | 'onChange'> & {
    value?: string | null
    onChange: (value: string | null) => void
    /** Overrides the default onChange(null) when the clear button is clicked. */
    onClear?: () => void
    clearButtonLabel?: string
}

/** Clearable native date input; keeps incomplete edits visible until explicitly cleared. */
const DateInput = forwardRef<HTMLInputElement, DateInputProps>(function DateInput({
    value,
    onChange,
    onClear,
    clearButtonLabel = 'Clear date',
    className,
    disabled,
    readOnly,
    onBlur,
    onInput,
    onKeyUp,
    'aria-invalid': ariaInvalid,
    ...inputProps
}, forwardedRef) {
    const [hasIncompleteInput, setHasIncompleteInput] = useState(false)
    const inputRef = useRef<HTMLInputElement | null>(null)

    const setRef = useCallback((node: HTMLInputElement | null) => {
        inputRef.current = node
        if (typeof forwardedRef === 'function') {
            forwardedRef(node)
        } else if (forwardedRef) {
            forwardedRef.current = node
        }
    }, [forwardedRef])

    const updateIncompleteInput = (input: HTMLInputElement) => {
        // A partially entered date can display edited segments even when input.value is empty.
        // Chromium does not always fire input/change events for those edits.
        setHasIncompleteInput(input.validity.badInput)
    }

    const clearDate = () => {
        // Also clear the native control: controlled React values cannot reset incomplete segments.
        if (inputRef.current) inputRef.current.value = ''
        setHasIncompleteInput(false)
        if (onClear) onClear()
        else onChange(null)
    }

    const invalid = ariaInvalid === true || ariaInvalid === 'true' ||
        ariaInvalid === 'grammar' || ariaInvalid === 'spelling'

    return (
        <div className={['input', 'date-input', className].filter(Boolean).join(' ')}
             data-invalid={invalid ? 'true' : undefined}>
            <input
                {...inputProps}
                ref={setRef}
                type="date"
                className="date-input__input"
                name={inputProps.name}
                value={value ?? ''}
                disabled={disabled}
                readOnly={readOnly}
                aria-invalid={ariaInvalid}
                onChange={(event) => {
                    updateIncompleteInput(event.currentTarget)
                    onChange(event.currentTarget.value || null)
                }}
                onInput={(event) => {
                    updateIncompleteInput(event.currentTarget)
                    onInput?.(event)
                }}
                onKeyUp={(event) => {
                    updateIncompleteInput(event.currentTarget)
                    onKeyUp?.(event)
                }}
                onBlur={(event) => {
                    updateIncompleteInput(event.currentTarget)
                    onBlur?.(event)
                }}
            />
            {!disabled && !readOnly && (Boolean(value) || hasIncompleteInput) && (
                <button
                    type="button"
                    className="date-input__clear"
                    onClick={clearDate}
                    aria-label={clearButtonLabel}
                    title={clearButtonLabel}
                >
                    <FontAwesomeIcon icon={faIcon('fas', 'xmark')}/>
                </button>
            )}
        </div>
    )
})

export default DateInput
