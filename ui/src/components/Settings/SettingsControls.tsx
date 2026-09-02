import type {ReactNode} from 'react'
import Switch from 'react-switch'


export function humanizeSeconds(seconds: number): string {
    if (!Number.isFinite(seconds)) return ''
    if (seconds % 86_400 === 0) {
        const days = seconds / 86_400
        return `${days} day${days === 1 ? '' : 's'}`
    }
    if (seconds % 3_600 === 0) {
        const hours = seconds / 3_600
        return `${hours} hour${hours === 1 ? '' : 's'}`
    }
    if (seconds % 60 === 0) {
        const minutes = seconds / 60
        return `${minutes} minute${minutes === 1 ? '' : 's'}`
    }
    return `${seconds} seconds`
}

export function SettingsSection({
    title,
    description,
    children,
    className,
}: {
    title: string
    description?: string
    children: ReactNode
    className?: string
}) {
    return (
        <details className={`settings-disclosure${className ? ` ${className}` : ''}`} open>
            <summary>
                <span>
                    <strong>{title}</strong>
                    {description ? <small>{description}</small> : null}
                </span>
            </summary>
            <div className="settings-grid settings-disclosure__body">{children}</div>
        </details>
    )
}

export function SettingsDisclosure({
    title,
    description,
    children,
}: {
    title: string
    description: string
    children: ReactNode
}) {
    return (
        <details className="settings-disclosure">
            <summary>
                <span>
                    <strong>{title}</strong>
                    <small>{description}</small>
                </span>
            </summary>
            <div className="settings-grid settings-disclosure__body">{children}</div>
        </details>
    )
}

function EnvironmentManagedNote({variable}: {variable: string}) {
    return (
        <div className="settings-field__environment-note">
            Managed by environment variable <code>{variable}</code>. Change or remove that environment override and restart WireLoft to edit this setting here.
        </div>
    )
}

function FieldShell({
    label,
    htmlFor,
    help,
    wide,
    environmentVariable,
    children,
}: {
    label: string
    htmlFor: string
    help?: ReactNode
    wide?: boolean
    environmentVariable?: string
    children: ReactNode
}) {
    return (
        <div className={`settings-field${wide ? ' settings-field--wide' : ''}${environmentVariable ? ' is-environment-managed' : ''}`}>
            <label htmlFor={htmlFor}>{label}</label>
            {children}
            {help ? <div className="settings-field__help">{help}</div> : null}
            {environmentVariable ? <EnvironmentManagedNote variable={environmentVariable} /> : null}
        </div>
    )
}

export function TextField({
    id,
    label,
    value,
    onChange,
    help,
    error,
    placeholder,
    wide,
    environmentVariable,
    inputType = 'text',
    autoComplete,
}: {
    id: string
    label: string
    value: string
    onChange: (value: string) => void
    help?: ReactNode
    error?: string
    placeholder?: string
    wide?: boolean
    environmentVariable?: string
    inputType?: 'text' | 'password'
    autoComplete?: string
}) {
    const errorId = `${id}-errors`
    return (
        <FieldShell label={label} htmlFor={id} help={help} wide={wide} environmentVariable={environmentVariable}>
            <input
                id={id}
                className="input settings-input"
                type={inputType}
                value={value}
                placeholder={placeholder}
                autoComplete={autoComplete}
                disabled={Boolean(environmentVariable)}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? errorId : undefined}
                onChange={(event) => onChange(event.target.value)}
            />
            {error ? (
                <div id={errorId} className="error" role="alert" aria-live="polite">
                    {error}
                </div>
            ) : null}
        </FieldShell>
    )
}

export function NumberField({
    id,
    label,
    value,
    onChange,
    help,
    error,
    min = 0,
    max,
    step = 1,
    unit,
    environmentVariable,
}: {
    id: string
    label: string
    value: number
    onChange: (value: number) => void
    help?: ReactNode
    error?: string
    min?: number
    max?: number
    step?: number
    unit?: string
    environmentVariable?: string
}) {
    const isValidNumber = Number.isFinite(value)
    const errorId = `${id}-errors`

    return (
        <FieldShell label={label} htmlFor={id} help={help} environmentVariable={environmentVariable}>
            <div className="settings-number-input">
                <input
                    id={id}
                    className="input settings-input"
                    type="number"
                    value={isValidNumber ? value : ''}
                    min={min}
                    max={max}
                    step={step}
                    disabled={Boolean(environmentVariable)}
                    aria-invalid={Boolean(error)}
                    aria-describedby={error ? errorId : undefined}
                    onChange={(event) => {
                        if (event.currentTarget.value === '') {
                            onChange(Number.NaN)
                            return
                        }
                        onChange(event.currentTarget.valueAsNumber)
                    }}
                />
                {unit ? <span>{unit}</span> : null}
            </div>
            {error ? (
                <div id={errorId} className="error" role="alert" aria-live="polite">
                    {error}
                </div>
            ) : null}
        </FieldShell>
    )
}

export function SelectField({
    id,
    label,
    value,
    options,
    optionLabels,
    onChange,
    help,
    error,
    environmentVariable,
}: {
    id: string
    label: string
    value: string
    options: readonly string[]
    optionLabels?: Partial<Record<string, string>>
    onChange: (value: string) => void
    help?: ReactNode
    error?: string
    environmentVariable?: string
}) {
    const errorId = `${id}-errors`
    return (
        <FieldShell label={label} htmlFor={id} help={help} environmentVariable={environmentVariable}>
            <select
                id={id}
                className="input settings-input settings-select"
                value={value}
                disabled={Boolean(environmentVariable)}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? errorId : undefined}
                onChange={(event) => onChange(event.target.value)}
            >
                {options.map((option) => (
                    <option key={option} value={option}>{optionLabels?.[option] ?? option}</option>
                ))}
            </select>
            {error ? (
                <div id={errorId} className="error" role="alert" aria-live="polite">
                    {error}
                </div>
            ) : null}
        </FieldShell>
    )
}

export function ToggleField({
    id,
    label,
    checked,
    onChange,
    help,
    wide,
    environmentVariable,
}: {
    id: string
    label: string
    checked: boolean
    onChange: (checked: boolean) => void
    help?: ReactNode
    wide?: boolean
    environmentVariable?: string
}) {
    const labelId = `${id}-label`
    return (
        <div className={`settings-field settings-toggle-field${wide ? ' settings-field--wide' : ''}${environmentVariable ? ' is-environment-managed' : ''}`}>
            <div className="settings-toggle-field__control">
                <div>
                    <label id={labelId} htmlFor={id}>{label}</label>
                    {help ? <div className="settings-field__help">{help}</div> : null}
                    {environmentVariable ? <EnvironmentManagedNote variable={environmentVariable} /> : null}
                </div>
                <Switch
                    id={id}
                    checked={checked}
                    disabled={Boolean(environmentVariable)}
                    onChange={onChange}
                    onColor="#0ea5e9"
                    offColor="#94a3b8"
                    uncheckedIcon={false}
                    checkedIcon={false}
                    aria-labelledby={labelId}
                />
            </div>
        </div>
    )
}

export function SettingsLoading() {
    return (
        <div className="settings-loading" aria-label="Loading settings">
            <div className="settings-loading__line settings-loading__line--title" />
            <div className="settings-loading__line" />
            <div className="settings-loading__tabs" />
            <div className="settings-loading__card" />
        </div>
    )
}
