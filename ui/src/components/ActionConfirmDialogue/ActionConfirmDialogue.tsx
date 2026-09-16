import {useEffect, useId, useState, type ReactNode} from 'react'
import type {IconProp} from '@fortawesome/fontawesome-svg-core'
import toast from 'react-hot-toast'

import type {FrontendOperationDefinition} from '../../lib/operationDefinitions'
import {OperationStartError, useStartOperation} from '../../lib/operations'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'

export type ActionConfirmDialogueLocalMediaProfile = {
    id: number
    label: string
}

type ActionConfirmDialogueProps = {
    open: boolean
    operationDefinition: FrontendOperationDefinition
    requestPath: string
    resourceLabel: string
    title: ReactNode
    children: ReactNode
    onDismiss: () => void
    icon?: IconProp
    iconTone?: 'default' | 'danger'
    confirmLabel?: ReactNode
    confirmClassName?: string
    disabled?: boolean
    method?: string
    scope_by_local_media_profile?: boolean
    localMediaProfiles?: readonly ActionConfirmDialogueLocalMediaProfile[]
}

export default function ActionConfirmDialogue({
    open,
    operationDefinition,
    requestPath,
    resourceLabel,
    title,
    children,
    onDismiss,
    icon,
    iconTone = 'default',
    confirmLabel,
    confirmClassName,
    disabled = false,
    method = 'POST',
    scope_by_local_media_profile = false,
    localMediaProfiles = [],
}: ActionConfirmDialogueProps) {
    const startOperation = useStartOperation()
    const selectorId = `action-confirm-dialogue-local-media-profile-${useId()}`
    const [starting, setStarting] = useState(false)
    const [localMediaProfileId, setLocalMediaProfileId] = useState('')
    const localMediaProfileKey = localMediaProfiles.map((profile) => profile.id).join(',')

    useEffect(() => {
        if (!open || !scope_by_local_media_profile) return
        setLocalMediaProfileId(
            localMediaProfiles.length > 1
                ? 'all'
                : localMediaProfiles[0]
                    ? String(localMediaProfiles[0].id)
                    : '',
        )
    }, [open, scope_by_local_media_profile, localMediaProfileKey])

    const dismiss = () => {
        if (!starting) onDismiss()
    }

    const submit = async () => {
        if (
            starting
            || disabled
            || (scope_by_local_media_profile && !localMediaProfileId)
        ) {
            return
        }

        setStarting(true)
        try {
            const base = (window as any).appConfig?.API_URL || '/api'
            const request: RequestInit = {method}
            if (scope_by_local_media_profile) {
                request.headers = {'Content-Type': 'application/json'}
                request.body = JSON.stringify({
                    localMediaProfileId: localMediaProfileId === 'all'
                        ? null
                        : Number(localMediaProfileId),
                })
            }

            await startOperation(`${base}${requestPath}`, request)
            onDismiss()
            toast.success(`${operationDefinition.label} started for ${resourceLabel}`)
        } catch (error) {
            const detail = error instanceof OperationStartError ? error.message : undefined
            toast.error(
                `Could not start ${operationDefinition.label.toLowerCase()} for ${resourceLabel}${detail ? `: ${detail}` : ''}`,
            )
        } finally {
            setStarting(false)
        }
    }

    return (
        <ConfirmDialog
            open={open}
            title={title}
            onDismiss={dismiss}
            icon={icon}
            iconTone={iconTone}
            dismissOnOverlayClick={!starting}
            cancelButton={{disabled: starting}}
            confirmButton={{
                label: starting ? 'Starting…' : (confirmLabel ?? operationDefinition.label),
                onClick: submit,
                className: confirmClassName ?? (iconTone === 'danger' ? 'btn btn-danger' : 'btn btn-primary'),
                disabled: starting
                    || disabled
                    || (scope_by_local_media_profile && !localMediaProfileId),
            }}
        >
            {children}
            {scope_by_local_media_profile && (
                <div className="form-row">
                    <label htmlFor={selectorId}>Local Media Profile</label>
                    <select
                        id={selectorId}
                        className="input"
                        value={localMediaProfileId}
                        disabled={starting}
                        onChange={(event) => setLocalMediaProfileId(event.target.value)}
                    >
                        {localMediaProfiles.length > 1 && (
                            <option value="all">All Local Media Profiles</option>
                        )}
                        {localMediaProfiles.map((profile) => (
                            <option key={profile.id} value={String(profile.id)}>
                                {profile.label}
                            </option>
                        ))}
                    </select>
                </div>
            )}
        </ConfirmDialog>
    )
}
