import {type FormEvent, useId, useState} from 'react'
import {createPortal} from 'react-dom'
import {zodResolver} from '@hookform/resolvers/zod'
import {useFieldArray, useForm, type UseFormReturn} from 'react-hook-form'
import {z} from 'zod'

import type {IndexingValueEntry} from '../../types/schemas/custom_metadata'
import {
    SHOW_LOCAL_MEDIA_PROFILE_INDEXING_VALUES_MAX_ITEMS,
    ShowLocalMediaProfileIndexingValuesSchema,
} from '../../types/schemas/show_local_media_profile'
import '../CustomMetadataEditor/CustomMetadataEditor.css'


const IndexingValuesDialogSchema = z.object({
    indexingValues: ShowLocalMediaProfileIndexingValuesSchema,
})
type IndexingValuesDialogValues = z.infer<typeof IndexingValuesDialogSchema>


function cloneIndexingValues(values: IndexingValueEntry[] | undefined): IndexingValueEntry[] {
    return (values ?? []).map(({key, name}) => ({key, name}))
}


export default function IndexingValuesEditorButton({
    form,
    className = 'btn',
}: {
    form: UseFormReturn<any>
    className?: string
}) {
    const [open, setOpen] = useState(false)
    const titleId = `indexing-values-title-${useId()}`
    const descriptionId = `indexing-values-description-${useId()}`

    const editorForm = useForm<IndexingValuesDialogValues>({
        resolver: zodResolver(IndexingValuesDialogSchema),
        defaultValues: {indexingValues: []},
        mode: 'onBlur',
        shouldFocusError: true,
    })
    const {fields, append, remove} = useFieldArray({
        control: editorForm.control,
        name: 'indexingValues',
    })

    const openEditor = () => {
        editorForm.reset({
            indexingValues: cloneIndexingValues(
                form.getValues('indexingValues') as IndexingValueEntry[] | undefined,
            ),
        })
        setOpen(true)
    }

    const applyChanges = editorForm.handleSubmit(({indexingValues}) => {
        form.setValue('indexingValues', cloneIndexingValues(indexingValues), {
            shouldDirty: true,
            shouldTouch: true,
            shouldValidate: true,
        })
        setOpen(false)
    })

    const onEditorSubmit = (event: FormEvent<HTMLFormElement>) => {
        event.stopPropagation()
        void applyChanges(event)
    }

    const dialog = open ? (
        <div className="modal-overlay" role="presentation" onClick={() => setOpen(false)}>
            <div
                className="modal custom-metadata-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                aria-describedby={descriptionId}
                onClick={(event) => event.stopPropagation()}
            >
                <div className="modal-header">
                    <h2 id={titleId} className="modal-title">Indexing values</h2>
                </div>

                <form onSubmit={onEditorSubmit} noValidate>
                    <div className="custom-metadata-content">
                        <p id={descriptionId} className="custom-metadata-description">
                            Define named number sequences for this Local Media Profile. Each Show gets its own
                            Episode ordering. Use <code>{"{{ 'featurettes' | custom_index }}"}</code> in the
                            output template.
                        </p>
                        <p className="custom-metadata-note">
                            Applying changes here only updates the Local Media Profile form. Nothing is saved to
                            WireLoft until the Local Media Profile itself is saved.
                        </p>

                        <div className="custom-metadata-rows">
                            {fields.length === 0 && (
                                <p className="custom-metadata-empty">No indexing values have been defined.</p>
                            )}

                            {fields.map((field, index) => {
                                const namePath = `indexingValues.${index}.name` as const
                                const keyPath = `indexingValues.${index}.key` as const
                                const nameError = editorForm.getFieldState(namePath).error
                                const keyError = editorForm.getFieldState(keyPath).error
                                const key = editorForm.watch(keyPath)

                                return (
                                    <div className="custom-metadata-row" key={field.id}>
                                        <div className="custom-metadata-field custom-metadata-value">
                                            <label htmlFor={`index-name-${field.id}`}>Name</label>
                                            <input
                                                id={`index-name-${field.id}`}
                                                className="input"
                                                placeholder="Featurettes"
                                                autoComplete="off"
                                                aria-invalid={!!nameError}
                                                {...editorForm.register(namePath)}
                                            />
                                            {nameError && (
                                                <div className="error">{String(nameError.message)}</div>
                                            )}
                                        </div>

                                        <div className="custom-metadata-field">
                                            <label htmlFor={`index-key-${field.id}`}>Key</label>
                                            <input
                                                id={`index-key-${field.id}`}
                                                className="input"
                                                placeholder="featurettes"
                                                autoComplete="off"
                                                aria-invalid={!!keyError}
                                                {...editorForm.register(keyPath)}
                                            />
                                            {keyError && (
                                                <div className="error">{String(keyError.message)}</div>
                                            )}
                                        </div>

                                        <button
                                            className="btn custom-metadata-remove"
                                            type="button"
                                            onClick={() => remove(index)}
                                        >
                                            Remove
                                        </button>

                                        <code className="custom-metadata-variable">
                                            {key
                                                ? `{{ '${key}' | custom_index }}`
                                                : "{{ '<key>' | custom_index }}"}
                                        </code>
                                    </div>
                                )
                            })}
                        </div>

                        <button
                            className="btn custom-metadata-add"
                            type="button"
                            onClick={() => append({key: '', name: ''})}
                            disabled={fields.length >= SHOW_LOCAL_MEDIA_PROFILE_INDEXING_VALUES_MAX_ITEMS}
                        >
                            Add indexing value
                        </button>
                    </div>

                    <div className="modal-actions">
                        <button type="button" className="btn" onClick={() => setOpen(false)}>Cancel</button>
                        <button type="submit" className="btn btn-primary">Apply changes</button>
                    </div>
                </form>
            </div>
        </div>
    ) : null

    return (
        <>
            <button type="button" className={className} onClick={openEditor}>
                Indexing values
            </button>
            {dialog ? createPortal(dialog, document.body) : null}
        </>
    )
}
