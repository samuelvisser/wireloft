import {useEffect, useId} from 'react'
import {zodResolver} from '@hookform/resolvers/zod'
import {useFieldArray, useForm} from 'react-hook-form'
import {useQueryClient, type QueryKey} from '@tanstack/react-query'
import toast from 'react-hot-toast'

import {
    CustomMetadataFormSchema,
    customMetadataToEntries,
    entriesToCustomMetadata,
    type CustomMetadataFormValues,
} from '../../types/schemas/custom_metadata'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import './CustomMetadataEditor.css'

export type CustomMetadataScope = 'show' | 'movie' | 'download'

type Props = {
    open: boolean
    title: string
    scope: CustomMetadataScope
    metadata: Record<string, string>
    endpoint: string
    invalidateQueryKeys?: QueryKey[]
    onDismiss: () => void
}

const VARIABLE_PREFIX: Record<CustomMetadataScope, string> = {
    show: 'meta_show_',
    movie: 'meta_movie_',
    download: 'meta_download_',
}

const SCOPE_LABEL: Record<CustomMetadataScope, string> = {
    show: 'show',
    movie: 'movie',
    download: 'Download Profile',
}

export default function CustomMetadataEditor({
    open,
    title,
    scope,
    metadata,
    endpoint,
    invalidateQueryKeys = [],
    onDismiss,
}: Props) {
    const queryClient = useQueryClient()
    const titleId = `custom-metadata-title-${useId()}`
    const descriptionId = `custom-metadata-description-${useId()}`
    const form = useForm<CustomMetadataFormValues>({
        resolver: zodResolver(CustomMetadataFormSchema),
        defaultValues: {entries: customMetadataToEntries(metadata)},
        mode: 'onBlur',
        shouldFocusError: true,
    })
    const {fields, append, remove} = useFieldArray({control: form.control, name: 'entries'})
    const {errors, isSubmitting} = form.formState
    const variablePrefix = VARIABLE_PREFIX[scope]

    useEffect(() => {
        if (!open) return
        form.reset({entries: customMetadataToEntries(metadata)})
    }, [form, metadata, open])

    const submit = buildServerAwareSubmit<CustomMetadataFormValues>(
        form,
        async ({entries}) => fetch(`${(window as any).appConfig.API_URL}${endpoint}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({customMetadata: entriesToCustomMetadata(entries)}),
        }),
        {
            successStatuses: [200],
            genericMessage: 'Could not save custom metadata',
            onSuccess: async () => {
                await Promise.all([
                    ...invalidateQueryKeys.map((queryKey) => queryClient.invalidateQueries({queryKey})),
                    queryClient.invalidateQueries({queryKey: ['localMediaProfileTemplateSources']}),
                ])
                toast.success('Custom metadata saved')
                onDismiss()
            },
        },
    )

    if (!open) return null

    return (
        <div className="modal-overlay" role="presentation" onClick={() => !isSubmitting && onDismiss()}>
            <div
                className="modal custom-metadata-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                aria-describedby={descriptionId}
                onClick={(event) => event.stopPropagation()}
            >
                <div className="modal-header">
                    <h2 id={titleId} className="modal-title">{title}</h2>
                </div>

                <form onSubmit={submit} noValidate>
                    <div className="custom-metadata-content">
                        <p id={descriptionId} className="custom-metadata-description">
                            Add values that WireLoft does not know automatically. A key such as <code>year</code> is available in output templates as{' '}
                            <code>{`{{ ${variablePrefix}year }}`}</code>.
                        </p>
                        <p className="custom-metadata-note">
                            Keys use lowercase letters, numbers, and underscores. Existing downloaded files are not moved automatically when metadata changes.
                        </p>

                        {errors.root && (
                            <div className="form-error-card" role="alert" aria-live="polite">
                                {String(errors.root.message)}
                            </div>
                        )}

                        <div className="custom-metadata-rows">
                            {fields.length === 0 && (
                                <p className="custom-metadata-empty">No custom metadata has been added to this {SCOPE_LABEL[scope]} yet.</p>
                            )}
                            {fields.map((field, index) => {
                                const key = form.watch(`entries.${index}.key`)
                                return (
                                    <div className="custom-metadata-row" key={field.id}>
                                        <div className="custom-metadata-field">
                                            <label htmlFor={`custom-metadata-key-${field.id}`}>Key</label>
                                            <input
                                                id={`custom-metadata-key-${field.id}`}
                                                className="input"
                                                placeholder="year"
                                                autoComplete="off"
                                                aria-invalid={!!errors.entries?.[index]?.key}
                                                {...form.register(`entries.${index}.key`)}
                                            />
                                            {errors.entries?.[index]?.key && (
                                                <div className="error">{String(errors.entries[index]?.key?.message)}</div>
                                            )}
                                        </div>
                                        <div className="custom-metadata-field custom-metadata-value">
                                            <label htmlFor={`custom-metadata-value-${field.id}`}>Value</label>
                                            <input
                                                id={`custom-metadata-value-${field.id}`}
                                                className="input"
                                                placeholder="2026"
                                                aria-invalid={!!errors.entries?.[index]?.value}
                                                {...form.register(`entries.${index}.value`)}
                                            />
                                            {errors.entries?.[index]?.value && (
                                                <div className="error">{String(errors.entries[index]?.value?.message)}</div>
                                            )}
                                        </div>
                                        <button
                                            type="button"
                                            className="btn custom-metadata-remove"
                                            onClick={() => remove(index)}
                                            disabled={isSubmitting}
                                        >
                                            Remove
                                        </button>
                                        <code className="custom-metadata-variable">
                                            {`{{ ${variablePrefix}${key || '<key>'} }}`}
                                        </code>
                                    </div>
                                )
                            })}
                        </div>

                        <button
                            type="button"
                            className="btn custom-metadata-add"
                            onClick={() => append({key: '', value: ''})}
                            disabled={isSubmitting || fields.length >= 100}
                        >
                            Add metadata
                        </button>
                    </div>

                    <div className="modal-actions">
                        <button type="button" className="btn" onClick={onDismiss} disabled={isSubmitting}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                            {isSubmitting ? 'Saving…' : 'Save metadata'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    )
}
