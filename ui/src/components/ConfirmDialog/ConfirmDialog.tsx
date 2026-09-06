import type {ReactNode} from 'react'
import {useId} from 'react'
import type {IconProp} from '@fortawesome/fontawesome-svg-core'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'

import './ConfirmDialog.css'

export type ConfirmDialogButton = {
    label: ReactNode
    onClick: () => void | Promise<void>
    icon?: IconProp
    iconSpin?: boolean
    className?: string
    disabled?: boolean
}

export type ConfirmDialogCancelButton = Omit<Partial<ConfirmDialogButton>, 'label'> & {
    label?: ReactNode
}

type ConfirmDialogProps = {
    open: boolean
    title: ReactNode
    children: ReactNode
    onDismiss: () => void
    icon?: IconProp
    iconTone?: 'default' | 'danger'
    confirmButton: ConfirmDialogButton
    showCancelButton?: boolean
    cancelButton?: ConfirmDialogCancelButton
    dismissOnOverlayClick?: boolean
    className?: string
}

export default function ConfirmDialog({
    open,
    title,
    children,
    onDismiss,
    icon,
    iconTone = 'default',
    confirmButton,
    showCancelButton = true,
    cancelButton,
    dismissOnOverlayClick = true,
    className,
}: ConfirmDialogProps) {
    const autoId = useId()
    const titleId = `confirm-dialog-title-${autoId}`
    const descriptionId = `confirm-dialog-description-${autoId}`

    if (!open) return null

    const onOverlayClick = () => {
        if (dismissOnOverlayClick) onDismiss()
    }
    const onCancel = cancelButton?.onClick ?? onDismiss

    return (
        <div className="modal-overlay" role="presentation" onClick={onOverlayClick}>
            <div
                className={['modal', className].filter(Boolean).join(' ')}
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                aria-describedby={descriptionId}
                onClick={(event) => event.stopPropagation()}
            >
                <div className="modal-header">
                    {icon && (
                        <div className={`modal-icon${iconTone === 'danger' ? ' danger' : ''}`} aria-hidden>
                            <FontAwesomeIcon icon={icon}/>
                        </div>
                    )}
                    <h2 id={titleId} className="modal-title">{title}</h2>
                </div>

                <div id={descriptionId} className="confirm-dialog-content">
                    {children}
                </div>

                <div className="modal-actions">
                    {showCancelButton && (
                        <button
                            type="button"
                            className={cancelButton?.className ?? 'btn'}
                            disabled={cancelButton?.disabled}
                            onClick={() => void onCancel()}
                        >
                            {cancelButton?.icon && (
                                <FontAwesomeIcon
                                    icon={cancelButton.icon}
                                    spin={cancelButton.iconSpin}
                                    aria-hidden="true"
                                />
                            )}
                            {cancelButton?.label ?? 'Cancel'}
                        </button>
                    )}
                    <button
                        type="button"
                        className={confirmButton.className ?? 'btn btn-primary'}
                        disabled={confirmButton.disabled}
                        onClick={() => void confirmButton.onClick()}
                    >
                        {confirmButton.icon && (
                            <FontAwesomeIcon
                                icon={confirmButton.icon}
                                spin={confirmButton.iconSpin}
                                aria-hidden="true"
                            />
                        )}
                        {confirmButton.label}
                    </button>
                </div>
            </div>
        </div>
    )
}
