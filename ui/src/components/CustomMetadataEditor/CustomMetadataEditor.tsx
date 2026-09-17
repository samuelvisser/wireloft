import {useEffect, useId, useMemo, useRef} from 'react'
import {zodResolver} from '@hookform/resolvers/zod'
import {useFieldArray, useForm} from 'react-hook-form'
import {useQueryClient, type QueryKey} from '@tanstack/react-query'
import toast from 'react-hot-toast'

import {useLocalMediaProfileTemplateSources} from '../../lib/localMediaProfileTemplateSources'
import {
    CustomMetadataFormSchema,
    customMetadataToEntries,
    entriesToCustomMetadata,
    type CustomMetadataFormValues,
} from '../../types/schemas/custom_metadata'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import './CustomMetadataEditor.css'

export type CustomMetadataScope = 'show' | 'movie'

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
}

const SCOPE_LABEL: Record<CustomMetadataScope, {singular: string; plural: string}> = {
    show: {singular: 'show', plural: 'shows'},
    movie: {singular: 'movie', plural: 'movies'},
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
    const variablePrefix = VARIABLE_PREFIX[scope]
    const scopeLabel = SCOPE_LABEL[scope]
    const {
        data: templateSources,
        isLoading: fieldsLoading,
        isError: fieldsFailed,
    } = useLocalMediaProfileTemplateSources(scope, open)

    const metadataFields = useMemo(() => {
        const discovered = (templateSources?.variables ?? [])
            .map(({name}) => name.startsWith(variablePrefix) ? name.slice(variablePrefix.length) : null)
            .filter((key): key is string => Boolean(key))
        return [...new Set([...discovered, ...Object.keys(metadata)])]
            .sort((left, right) => left.localeCompare(right))
    }, [metadata, templateSources?.variables, variablePrefix])
    const knownFields = useMemo(() => new Set(metadataFields), [metadataFields])

    const form = useForm<CustomMetadataFormValues>({
        resolver: zodResolver(CustomMetadataFormSchema),
        defaultValues: {entries: customMetadataToEntries(metadata, metadataFields)},
        mode: 'onBlur',
        shouldFocusError: true,
    })
    const {fields, append, remove} = useFieldArray({control: form.control, name: 'entries'})
    const {errors, isDirty, isSubmitting} = form.formState
    const wasOpen = useRef(false)

    useEffect(() => {
        const justOpened = open && !wasOpen.current
        wasOpen.current = open
        if (!open || (!justOpened && isDirty)) return
        form.reset({entries: customMetadataToEntries(metadata, metadataFields)})
    }, [form, isDirty, metadata, metadataFields, open])

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
                            Metadata fields are shared by all {scopeLabel.plural}, while each {scopeLabel.singular} has its own value. A field such as <code>year</code> is available in output templates as{' '}
                            <code>{`{{ ${variablePrefix}year }}`}</code>.
                        </p>
                        <p className="custom-metadata-note">
                            Adding a field here makes it available to every {scopeLabel.singular}; leave its value empty where it does not apply. Field names use lowercase letters, numbers, and underscores. Existing downloaded files are not moved automatically when metadata changes.
                        </p>

                        {errors.root && (
                            <div className="form-error-card" role="alert" aria-live="polite">
                                {String(errors.root.message)}
                            </div>
                        )}
                        {fieldsFailed && (
                            <div className="form-error-card" role="alert" aria-live="polite">
                                WireLoft could not load metadata fields used by other {scopeLabel.plural}. Existing values can still be edited.
                            </div>
                        )}

                        {fieldsLoading ? (
                            <p className="custom-metadata-empty">Loading metadata fields…</p>
                        ) : (
                            <div className="custom-metadata-rows">
                                {fields.length === 0 && (
                                    <p className="custom-metadata-empty">No custom metadata fields have been added to any {scopeLabel.plural} yet.</p>
                                )}
                                {fields.map((field, index) => {
                                    const key = form.watch(`entries.${index}.key`)
                                    const value = form.watch(`entries.${index}.value`)
                                    const firstIndexForKey = form.getValues('entries').findIndex((entry) => entry.key === key)
                                    const knownField = knownFields.has(key) && firstIndexForKey === index
                                    return (
                                        <div className="custom-metadata-row" key={field.id}>
                                            <div className="custom-metadata-field">
                                                <label htmlFor={`custom-metadata-key-${field.id}`}>Field</label>
                                                <input
                                                    id={`custom-metadata-key-${field.id}`}
                                                    className="input"
                                                    placeholder="year"
                                                    autoComplete="off"
                                                    readOnly={knownField}
                                                    title={knownField ? `This field is shared by all ${scopeLabel.plural}` : undefined}
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
                                                onClick={() => {
                                                    if (knownField) {
                                                        form.setValue(`entries.${index}.value`, '', {
                                                            shouldDirty: true,
                                                            shouldValidate: true,
                                                        })
                                                    } else {
                                                        remove(index)
                                                    }
                                                }}
                                                disabled={isSubmitting || (knownField && !value)}
                                            >
                                                {knownField ? 'Clear' : 'Remove'}
                                            </button>
                                            <code className="custom-metadata-variable">
                                                {`{{ ${variablePrefix}${key || '<field>'} }}`}
                                            </code>
                                        </div>
                                    )
                                })}
                            </div>
                        )}

                        <button
                            type="button"
                            className="btn custom-metadata-add"
                            onClick={() => append({key: '', value: ''})}
                            disabled={isSubmitting || fieldsLoading || fields.length >= 100}
                        >
                            Add field
                        </button>
                    </div>

                    <div className="modal-actions">
                        <button type="button" className="btn" onClick={onDismiss} disabled={isSubmitting}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={isSubmitting || fieldsLoading}>
                            {isSubmitting ? 'Saving…' : 'Save metadata'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    )
}
