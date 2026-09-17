import {useEffect, useId, useMemo, useRef, useState} from 'react'
import {zodResolver} from '@hookform/resolvers/zod'
import {useFieldArray, useForm} from 'react-hook-form'
import {useQueryClient, type QueryKey} from '@tanstack/react-query'
import toast from 'react-hot-toast'

import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'
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

type PendingRemoval = {
    fieldId: string
    key: string
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
    const [pendingRemovedFields, setPendingRemovedFields] = useState<Set<string>>(() => new Set())
    const [confirmRemoval, setConfirmRemoval] = useState<PendingRemoval | null>(null)
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
    const persistedFields = useMemo(() => new Set(metadataFields), [metadataFields])

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
        if (justOpened) {
            setPendingRemovedFields(new Set())
            setConfirmRemoval(null)
        }
        if (!open || (!justOpened && isDirty)) return
        form.reset({entries: customMetadataToEntries(metadata, metadataFields)})
    }, [form, isDirty, metadata, metadataFields, open])

    const submit = buildServerAwareSubmit<CustomMetadataFormValues>(
        form,
        async ({entries}) => {
            const activeFields = new Set(entries.map(({key}) => key))
            const removedFields = [...pendingRemovedFields]
                .filter((key) => !activeFields.has(key))
                .sort()
            return fetch(`${(window as any).appConfig.API_URL}${endpoint}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({
                    customMetadata: entriesToCustomMetadata(entries),
                    removedFields,
                }),
            })
        },
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

    const confirmFieldRemoval = () => {
        if (!confirmRemoval) return
        const index = fields.findIndex(({id}) => id === confirmRemoval.fieldId)
        if (index >= 0) remove(index)
        setPendingRemovedFields((current) => {
            const next = new Set(current)
            next.add(confirmRemoval.key)
            return next
        })
        setConfirmRemoval(null)
    }

    return (
        <>
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
                            <p className="custom-metadata-intro">
                                Add custom metadata fields to a {scopeLabel.singular} here.
                            </p>
                            <p id={descriptionId} className="custom-metadata-description">
                                Metadata fields can be used in output templates as{' '}
                                <code>{`{{ ${variablePrefix}<field_name> }}`}</code>. This makes it possible to add arbitrary metadata to the output path of downloaded files for this {scopeLabel.singular}.
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
                                        const isPersistedField = persistedFields.has(key) && !pendingRemovedFields.has(key)
                                        return (
                                            <div className="custom-metadata-row" key={field.id}>
                                                <div className="custom-metadata-field">
                                                    <label htmlFor={`custom-metadata-key-${field.id}`}>Field</label>
                                                    <input
                                                        id={`custom-metadata-key-${field.id}`}
                                                        className="input"
                                                        placeholder="year"
                                                        autoComplete="off"
                                                        readOnly={isPersistedField}
                                                        title={isPersistedField ? `This field is shared by all ${scopeLabel.plural}` : undefined}
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
                                                        if (isPersistedField) {
                                                            setConfirmRemoval({fieldId: field.id, key})
                                                        } else {
                                                            remove(index)
                                                        }
                                                    }}
                                                    disabled={isSubmitting}
                                                >
                                                    Remove
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

            <ConfirmDialog
                open={confirmRemoval !== null}
                title="Remove metadata field?"
                onDismiss={() => setConfirmRemoval(null)}
                icon={['fas', 'triangle-exclamation']}
                iconTone="danger"
                confirmButton={{
                    label: 'Remove field',
                    className: 'btn btn-danger',
                    onClick: confirmFieldRemoval,
                }}
            >
                <p>
                    <strong>{confirmRemoval?.key}</strong> is a shared metadata field for all {scopeLabel.plural}. Removing it will remove the field and its saved value from every {scopeLabel.singular}. Are you sure?
                </p>
            </ConfirmDialog>
        </>
    )
}
