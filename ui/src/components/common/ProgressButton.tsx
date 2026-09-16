import type {IconProp} from '@fortawesome/fontawesome-svg-core'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import type {ReactNode} from 'react'

import {useActiveOperation} from '../OperationNotifier/OperationNotifier'
import type {FrontendOperationDefinition} from '../../lib/operationDefinitions'
import './ProgressButton.css'

export type ProgressButtonRetryAction = {
    onClick: () => void
    disabled?: boolean
    label?: string
}

type ProgressButtonProps = {
    definition: FrontendOperationDefinition
    resourceId?: number | null
    label: ReactNode
    icon?: IconProp
    onClick: () => void
    disabled?: boolean
    primary?: boolean
    className?: string
    starting?: boolean
    active?: boolean
    progress?: number
    activeLabel?: string
    ariaLabel?: string
    onCancel?: () => void
    cancelDisabled?: boolean
    cancelLabel?: string
    retry?: ProgressButtonRetryAction
}

function clampProgress(value: number | null | undefined): number {
    if (value == null || !Number.isFinite(value)) return 0
    return Math.max(0, Math.min(100, Math.round(value)))
}

export default function ProgressButton({
    definition,
    resourceId,
    label,
    icon,
    onClick,
    disabled = false,
    primary = true,
    className = '',
    starting = false,
    active = false,
    progress,
    activeLabel,
    ariaLabel,
    onCancel,
    cancelDisabled = false,
    cancelLabel,
    retry,
}: ProgressButtonProps) {
    // A missing resource ID means this button is managing its own aggregate state
    // instead of binding to an arbitrary active operation of the same kind.
    const operation = useActiveOperation(
        definition.kind,
        definition.resourceType,
        resourceId ?? null,
    )
    const isActive = starting || active || operation !== undefined
    const resolvedProgress = clampProgress(progress ?? operation?.progress)
    const resolvedActiveLabel = activeLabel
        ?? (starting && operation === undefined
            ? 'Starting…'
            : operation?.status === 'QUEUED'
                ? 'Queued…'
                : operation?.status === 'WAITING'
                    ? operation.message || 'Waiting…'
                    : `${resolvedProgress}%`)
    const showCancel = isActive && onCancel !== undefined
    const controls = Number(Boolean(retry)) + Number(showCancel)
    const rootClassName = [
        'progress-button-root',
        primary ? 'is-primary' : '',
        isActive ? 'is-progress' : '',
        controls > 0 ? 'has-controls' : '',
        controls > 1 ? 'has-multiple-controls' : '',
        className,
    ].filter(Boolean).join(' ')
    const surfaceClassName = `btn${primary ? ' btn-primary' : ''} progress-button`
    const accessibleLabel = ariaLabel || definition.label

    return (
        <span className={rootClassName}>
            {isActive ? (
                <span
                    className={surfaceClassName}
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={resolvedProgress}
                    aria-label={`${accessibleLabel}: ${resolvedActiveLabel}`}
                >
                    <span
                        className="progress-button-fill"
                        style={{width: `${resolvedProgress}%`}}
                        aria-hidden="true"
                    />
                    <span className="progress-button-label">{resolvedActiveLabel}</span>
                </span>
            ) : (
                <button
                    type="button"
                    className={surfaceClassName}
                    onClick={onClick}
                    disabled={disabled}
                    aria-label={ariaLabel}
                >
                    {icon && <FontAwesomeIcon icon={icon}/>} 
                    {label}
                </button>
            )}

            {controls > 0 && (
                <span className="progress-button-controls">
                    {retry && (
                        <button
                            type="button"
                            className="progress-button-control"
                            onClick={retry.onClick}
                            disabled={retry.disabled}
                            title={retry.label || `Retry ${definition.label.toLocaleLowerCase()}`}
                            aria-label={retry.label || `Retry ${definition.label.toLocaleLowerCase()}`}
                        >
                            <FontAwesomeIcon icon={['fas', 'rotate-right']}/>
                        </button>
                    )}
                    {showCancel && (
                        <button
                            type="button"
                            className="progress-button-control is-cancel"
                            onClick={onCancel}
                            disabled={cancelDisabled}
                            title={cancelLabel || `Cancel ${definition.label.toLocaleLowerCase()}`}
                            aria-label={cancelLabel || `Cancel ${definition.label.toLocaleLowerCase()}`}
                        >
                            <FontAwesomeIcon icon={['fas', 'xmark']}/>
                        </button>
                    )}
                </span>
            )}
        </span>
    )
}
