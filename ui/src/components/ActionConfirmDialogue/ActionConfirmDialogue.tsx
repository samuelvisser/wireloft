import {useEffect, useId, useState, type ReactNode} from 'react'
import {Controller, useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {z} from 'zod'
import type {IconProp} from '@fortawesome/fontawesome-svg-core'
import toast from 'react-hot-toast'

import type {FrontendOperationDefinition} from '../../lib/operationDefinitions'
import {OperationStartError, useStartOperation} from '../../lib/operations'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'
import SimpleSelect from '../common/SimpleSelect'
import {createSelectRegistry} from '../../utils/selectRegistry'
import {getZodDefaults} from '../../utils/defaultZod'

const DeleteOlderThanReg = createSelectRegistry('BulkDeleteOlderThan', {
    all: {label: 'Delete all'},
    days: {label: 'Delete older than days'},
    latest_downloads: {label: 'Delete older than latest downloads'},
})

const DeleteOlderThanSchema = z.object({
    deleteOlderThan: z.enum(['all', 'days', 'latest_downloads']).default('all'),
    deleteOlderThanDays: z.number().int().positive().nullable().default(null),
    deleteOlderThanLatestDownloads: z.number().int().positive().nullable().default(null),
}).superRefine((value, ctx) => {
    if (value.deleteOlderThan === 'days' && value.deleteOlderThanDays === null) {
        ctx.addIssue({code: 'custom', path: ['deleteOlderThanDays'], message: 'Enter a positive number of days.'})
    }
    if (value.deleteOlderThan === 'latest_downloads' && value.deleteOlderThanLatestDownloads === null) {
        ctx.addIssue({
            code: 'custom',
            path: ['deleteOlderThanLatestDownloads'],
            message: 'Enter a positive number of downloads.',
        })
    }
})
type DeleteOlderThanInput = z.input<typeof DeleteOlderThanSchema>
type DeleteOlderThanForm = z.output<typeof DeleteOlderThanSchema>
const deleteOlderThanDefaults = getZodDefaults(DeleteOlderThanSchema)

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
    showDeleteOlderThan?: boolean
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
    showDeleteOlderThan = false,
    localMediaProfiles = [],
}: ActionConfirmDialogueProps) {
    const startOperation = useStartOperation()
    const selectorId = `action-confirm-dialogue-local-media-profile-${useId()}`
    const [starting, setStarting] = useState(false)
    const [localMediaProfileId, setLocalMediaProfileId] = useState('')
    const olderThanId = useId()
    const {control, handleSubmit, reset, setValue, watch, formState: {errors}} = useForm<
        DeleteOlderThanInput, unknown, DeleteOlderThanForm
    >({
        resolver: zodResolver(DeleteOlderThanSchema),
        defaultValues: deleteOlderThanDefaults,
    })
    const deleteOlderThan = watch('deleteOlderThan')
    const localMediaProfileKey = localMediaProfiles.map((profile) => profile.id).join(',')
    const localMediaProfileOptions: Record<string, {label: string}> = {}
    const localMediaProfileValues: string[] = []
    if (localMediaProfiles.length > 1) {
        localMediaProfileOptions.all = {label: 'All Local Media Profiles'}
        localMediaProfileValues.push('all')
    }
    for (const profile of localMediaProfiles) {
        const value = String(profile.id)
        localMediaProfileOptions[value] = {label: profile.label}
        localMediaProfileValues.push(value)
    }
    const localMediaProfileReg = createSelectRegistry(
        'ActionConfirmLocalMediaProfile',
        localMediaProfileOptions,
        localMediaProfileValues,
    )

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

    useEffect(() => {
        if (open && showDeleteOlderThan) reset(deleteOlderThanDefaults)
    }, [open, showDeleteOlderThan, reset])

    const dismiss = () => {
        if (!starting) onDismiss()
    }

    const submit = async (ageFilter?: DeleteOlderThanForm) => {
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
                    ...(showDeleteOlderThan && ageFilter ? (
                        ageFilter.deleteOlderThan === 'days'
                            ? {
                                deleteOlderThan: 'days',
                                deleteOlderThanDays: ageFilter.deleteOlderThanDays,
                            }
                            : ageFilter.deleteOlderThan === 'latest_downloads'
                                ? {
                                    deleteOlderThan: 'latest_downloads',
                                    deleteOlderThanLatestDownloads: ageFilter.deleteOlderThanLatestDownloads,
                                }
                                : {deleteOlderThan: 'all'}
                    ) : {}),
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
                onClick: () => showDeleteOlderThan
                    ? handleSubmit(submit)()
                    : submit(),
                className: confirmClassName ?? (iconTone === 'danger' ? 'btn btn-danger' : 'btn btn-primary'),
                disabled: starting
                    || disabled
                    || (scope_by_local_media_profile && !localMediaProfileId),
            }}
        >
            {children}
            {showDeleteOlderThan && (
                <>
                    <div className="form-row">
                        <label htmlFor={`${olderThanId}-mode`}>Delete older than</label>
                        <Controller
                            control={control}
                            name="deleteOlderThan"
                            render={({field}) => (
                                <SimpleSelect
                                    inputId={`${olderThanId}-mode`}
                                    registry={DeleteOlderThanReg}
                                    value={field.value}
                                    isDisabled={starting}
                                    onBlur={field.onBlur}
                                    onChange={(value) => {
                                        field.onChange(value)
                                        setValue('deleteOlderThanDays', value === 'days' ? 30 : null, {shouldValidate: true})
                                        setValue('deleteOlderThanLatestDownloads', value === 'latest_downloads' ? 10 : null, {shouldValidate: true})
                                    }}
                                />
                            )}
                        />
                    </div>
                    {deleteOlderThan === 'days' && (
                        <div className="form-row">
                            <label htmlFor={`${olderThanId}-days`}>Days</label>
                            <Controller
                                control={control}
                                name="deleteOlderThanDays"
                                render={({field}) => (
                                    <input
                                        id={`${olderThanId}-days`}
                                        className="input"
                                        type="number"
                                        min={1}
                                        step={1}
                                        inputMode="numeric"
                                        value={field.value ?? ''}
                                        onChange={(event) => field.onChange(
                                            event.currentTarget.value === '' ? null : Number(event.currentTarget.value)
                                        )}
                                        onBlur={field.onBlur}
                                        ref={field.ref}
                                        disabled={starting}
                                        aria-invalid={!!errors.deleteOlderThanDays}
                                    />
                                )}
                            />
                            {errors.deleteOlderThanDays && (
                                <div className="error" role="alert">{errors.deleteOlderThanDays.message}</div>
                            )}
                            <div className="help">Only episodes published more than this many days ago are selected.</div>
                        </div>
                    )}
                    {deleteOlderThan === 'latest_downloads' && (
                        <div className="form-row">
                            <label htmlFor={`${olderThanId}-count`}>Latest downloads to keep</label>
                            <Controller
                                control={control}
                                name="deleteOlderThanLatestDownloads"
                                render={({field}) => (
                                    <input
                                        id={`${olderThanId}-count`}
                                        className="input"
                                        type="number"
                                        min={1}
                                        step={1}
                                        inputMode="numeric"
                                        value={field.value ?? ''}
                                        onChange={(event) => field.onChange(
                                            event.currentTarget.value === '' ? null : Number(event.currentTarget.value)
                                        )}
                                        onBlur={field.onBlur}
                                        ref={field.ref}
                                        disabled={starting}
                                        aria-invalid={!!errors.deleteOlderThanLatestDownloads}
                                    />
                                )}
                            />
                            {errors.deleteOlderThanLatestDownloads && (
                                <div className="error" role="alert">{errors.deleteOlderThanLatestDownloads.message}</div>
                            )}
                            <div className="help">Keep the latest downloads in the selected Local Media Profile scope. Episodes without downloads do not count.</div>
                        </div>
                    )}
                </>
            )}
            {scope_by_local_media_profile && (
                <div className="form-row">
                    <label htmlFor={selectorId}>Local Media Profile</label>
                    <SimpleSelect
                        inputId={selectorId}
                        registry={localMediaProfileReg}
                        value={localMediaProfileId}
                        isDisabled={starting}
                        onChange={setLocalMediaProfileId}
                    />
                </div>
            )}
        </ConfirmDialog>
    )
}
