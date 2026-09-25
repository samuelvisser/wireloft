import {useEffect, useId, useMemo, useRef, useState} from 'react'
import {zodResolver} from '@hookform/resolvers/zod'
import {useFieldArray, useForm} from 'react-hook-form'
import {useQueryClient, type QueryKey} from '@tanstack/react-query'
import toast from 'react-hot-toast'

import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'
import {useCustomMetadataFields} from '../../lib/customMetadataFields'
import {
    CustomMetadataFormSchema,
    customMetadataToEntries,
    entriesToCustomMetadata,
    type CustomMetadataFormValues,
    type IndexingValueEntry,
} from '../../types/schemas/custom_metadata'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import './CustomMetadataEditor.css'

export type CustomMetadataScope = 'show' | 'movie'

type Props = {
    open: boolean
    title: string
    scope: CustomMetadataScope
    metadata: Record<string, string>
    indexingValues?: IndexingValueEntry[]
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

const EMPTY_INDEXING_VALUES: IndexingValueEntry[] = []

export default function CustomMetadataEditor({
    open,
    title,
    scope,
    metadata,
    indexingValues = EMPTY_INDEXING_VALUES,
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
    const [confirmIndexRemoval, setConfirmIndexRemoval] = useState<PendingRemoval | null>(null)
    const {
        data: sharedFields,
        isLoading: fieldsLoading,
        isError: fieldsFailed,
    } = useCustomMetadataFields(scope, open)

    const metadataFields = useMemo(() => (
        [...new Set([...(sharedFields ?? []), ...Object.keys(metadata)])]
            .sort((left, right) => left.localeCompare(right))
    ), [metadata, sharedFields])
    const persistedFields = useMemo(() => new Set(metadataFields), [metadataFields])
    const persistedIndexKeys = useMemo(
        () => new Set(indexingValues.map(({key}) => key)),
        [indexingValues],
    )

    const form = useForm<CustomMetadataFormValues>({
        resolver: zodResolver(CustomMetadataFormSchema),
        defaultValues: {
            entries: customMetadataToEntries(metadata, metadataFields),
            indexingValues,
        },
        mode: 'onBlur',
        shouldFocusError: true,
    })
    const {
        fields,
        append,
        remove,
    } = useFieldArray({control: form.control, name: 'entries'})
    const {
        fields: indexFields,
        append: appendIndex,
        remove: removeIndex,
    } = useFieldArray({control: form.control, name: 'indexingValues'})
    const {errors, isDirty, isSubmitting} = form.formState
    const wasOpen = useRef(false)

    useEffect(() => {
        const justOpened = open && !wasOpen.current
        wasOpen.current = open
        if (justOpened) {
            setPendingRemovedFields(new Set())
            setConfirmRemoval(null)
            setConfirmIndexRemoval(null)
        }
        if (!open || (!justOpened && isDirty)) return
        form.reset({
            entries: customMetadataToEntries(metadata, metadataFields),
            indexingValues,
        })
    }, [form, indexingValues, isDirty, metadata, metadataFields, open])

    const submit = buildServerAwareSubmit<CustomMetadataFormValues>(
        form,
        async ({entries, indexingValues: nextIndexingValues}) => {
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
                    indexingValues: scope === 'show' ? nextIndexingValues : [],
                }),
            })
        },
        {
            successStatuses: [200],
            genericMessage: 'Could not save metadata',
            onSuccess: async () => {
                await Promise.all([
                    ...invalidateQueryKeys.map((queryKey) => queryClient.invalidateQueries({queryKey})),
                    queryClient.invalidateQueries({queryKey: ['customMetadataFields']}),
                    queryClient.invalidateQueries({queryKey: ['localMediaProfileTemplateSources']}),
                ])
                toast.success('Metadata saved')
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

    const confirmIndexingValueRemoval = () => {
        if (!confirmIndexRemoval) return
        const index = indexFields.findIndex(({id}) => id === confirmIndexRemoval.fieldId)
        if (index >= 0) removeIndex(index)
        setConfirmIndexRemoval(null)
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
                                Metadata fields can be used in output templates as <code>{`{{ ${variablePrefix}field_name }}`}</code>.
                                This can therefore be a very powerful way to add any arbitrary metadata to the output path of downloaded files for this {scopeLabel.singular}.
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
                                <div className="form-error-card" role="alert">
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
                                                        placeholder="name"
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
                                                        placeholder="data"
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
                                                    {`{{ ${variablePrefix}${key || '<field>'} }}`}
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

                            {scope === 'show' && (
                                <>
                                    <div className="custom-metadata-divider"/>
                                    <h3>Indexing Values</h3>
                                    <p className="custom-metadata-description">
                                        Define independent persistent number sequences for this show. Local Media Profile Jinja can request a sequence with <code>{"{{ 'featurettes' | custom_index }}"}</code>. A MediaDownload keeps its assigned number even if its file is later deleted and downloaded again.
                                    </p>
                                    <p className="custom-metadata-note">
                                        Saved keys are immutable. You can rename the display name, or remove a key and create a new one. Removing a saved key deletes that key's stored assignments for this show and resets its sequence.
                                    </p>

                                    <div className="custom-metadata-rows">
                                        {indexFields.length === 0 && (
                                            <p className="custom-metadata-empty">No Indexing Values are defined for this show.</p>
                                        )}
                                        {indexFields.map((field, index) => {
                                            const key = form.watch(`indexingValues.${index}.key`)
                                            const isPersistedIndex = persistedIndexKeys.has(key)
                                            return (
                                                <div className="custom-metadata-row" key={field.id}>
                                                    <div className="custom-metadata-field custom-metadata-value">
                                                        <label htmlFor={`indexing-value-name-${field.id}`}>Name</label>
                                                        <input
                                                            id={`indexing-value-name-${field.id}`}
                                                            className="input"
                                                            placeholder="Featurettes"
                                                            aria-invalid={!!errors.indexingValues?.[index]?.name}
                                                            {...form.register(`indexingValues.${index}.name`)}
                                                        />
                                                        {errors.indexingValues?.[index]?.name && (
                                                            <div className="error">{String(errors.indexingValues[index]?.name?.message)}</div>
                                                        )}
                                                    </div>
                                                    <div className="custom-metadata-field">
                                                        <label htmlFor={`indexing-value-key-${field.id}`}>Key</label>
                                                        <input
                                                            id={`indexing-value-key-${field.id}`}
                                                            className="input"
                                                            placeholder="featurettes"
                                                            autoComplete="off"
                                                            readOnly={isPersistedIndex}
                                                            title={isPersistedIndex ? 'Saved Indexing Value keys are immutable' : undefined}
                                                            aria-invalid={!!errors.indexingValues?.[index]?.key}
                                                            {...form.register(`indexingValues.${index}.key`)}
                                                        />
                                                        {errors.indexingValues?.[index]?.key && (
                                                            <div className="error">{String(errors.indexingValues[index]?.key?.message)}</div>
                                                        )}
                                                    </div>
                                                    <button
                                                        type="button"
                                                        className="btn custom-metadata-remove"
                                                        onClick={() => {
                                                            if (isPersistedIndex) {
                                                                setConfirmIndexRemoval({fieldId: field.id, key})
                                                            } else {
                                                                removeIndex(index)
                                                            }
                                                        }}
                                                        disabled={isSubmitting}
                                                    >
                                                        Remove
                                                    </button>
                                                    <code className="custom-metadata-variable">
                                                        {`{{ '${key || '<key>'}' | custom_index }}`}
                                                    </code>
                                                </div>
                                            )
                                        })}
                                    </div>

                                    <button
                                        type="button"
                                        className="btn custom-metadata-add"
                                        onClick={() => appendIndex({key: '', name: ''})}
                                        disabled={isSubmitting || indexFields.length >= 100}
                                    >
                                        Add indexing value
                                    </button>
                                </>
                            )}
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

            <ConfirmDialog
                open={confirmIndexRemoval !== null}
                title="Remove Indexing Value?"
                onDismiss={() => setConfirmIndexRemoval(null)}
                icon={['fas', 'triangle-exclamation']}
                iconTone="danger"
                confirmButton={{
                    label: 'Remove indexing value',
                    className: 'btn btn-danger',
                    onClick: confirmIndexingValueRemoval,
                }}
            >
                <p>
                    Removing <strong>{confirmIndexRemoval?.key}</strong> deletes its saved MediaDownload assignments for this show and resets this sequence. Existing files are not renamed automatically. Are you sure?
                </p>
            </ConfirmDialog>
        </>
    )
}
