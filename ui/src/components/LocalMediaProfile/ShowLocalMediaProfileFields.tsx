import {Controller, useFieldArray, UseFormReturn} from 'react-hook-form'
import Select from 'react-select'

import {PreferredFormatReg, ShowLocalMediaProfileScopeReg} from '../../types/local_media_profile'
import ReadMore from '../../utils/ReadMore'
import LocalMediaProfilePreferredFormatField from './LocalMediaProfilePreferredFormatField'
import '../CustomMetadataEditor/CustomMetadataEditor.css'

export default function ShowLocalMediaProfileFields({form}: { form: UseFormReturn<any> }) {
    const {control, formState: {errors}} = form
    const {fields, append, remove} = useFieldArray({control, name: 'indexingValues'})

    return (
        <>
            <div className="form-row">
                <label htmlFor="mp-show-scope">Available for</label>
                <Controller
                    control={control}
                    name="showScope"
                    render={({field}) => (
                        <Select
                            inputId="mp-show-scope"
                            classNamePrefix="select"
                            options={ShowLocalMediaProfileScopeReg.options}
                            value={ShowLocalMediaProfileScopeReg.options.find((option) => option.value === field.value) ?? null}
                            onChange={(option) => field.onChange((option as any)?.value ?? null)}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.showScope}
                            aria-describedby={errors.showScope ? 'mp-show-scope-error' : 'mp-show-scope-help'}
                            isClearable={false}
                        />
                    )}
                />
                {errors.showScope && (
                    <div id="mp-show-scope-error" className="error" role="alert" aria-live="polite">
                        {String(errors.showScope.message)}
                    </div>
                )}
                <div className="help" id="mp-show-scope-help">
                    <ReadMore summary={<span>Controls where this profile is offered within WireLoft</span>}>
                        <p>This will not change anything technical about this Local Media Profile, but acts as a filter where WireLoft shows this profile as an option</p>
                    </ReadMore>
                </div>
            </div>

            <div className="form-row">
                <h3>Indexing Values</h3>
                <p className="help">
                    Define number sequences for this Local Media Profile. Each Show receives its own
                    ranks based on Episode order. Use <code>{"{{ 'featurettes' | custom_index }}"}</code> in
                    the output template. An undefined key renders empty.
                </p>
                <div className="custom-metadata-rows">
                    {fields.map((field, index) => (
                        <div className="custom-metadata-row" key={field.id}>
                            <div className="custom-metadata-field custom-metadata-value">
                                <label htmlFor={`index-name-${field.id}`}>Name</label>
                                <input
                                    id={`index-name-${field.id}`}
                                    className="input"
                                    placeholder="Featurettes"
                                    {...form.register(`indexingValues.${index}.name`)}
                                    aria-invalid={!!form.getFieldState(`indexingValues.${index}.name`).error}
                                />
                                {form.getFieldState(`indexingValues.${index}.name`).error && (
                                    <div className="error">
                                        {String(form.getFieldState(`indexingValues.${index}.name`).error?.message)}
                                    </div>
                                )}
                            </div>
                            <div className="custom-metadata-field">
                                <label htmlFor={`index-key-${field.id}`}>Key</label>
                                <input
                                    id={`index-key-${field.id}`}
                                    className="input"
                                    placeholder="featurettes"
                                    {...form.register(`indexingValues.${index}.key`)}
                                    aria-invalid={!!form.getFieldState(`indexingValues.${index}.key`).error}
                                />
                                {form.getFieldState(`indexingValues.${index}.key`).error && (
                                    <div className="error">
                                        {String(form.getFieldState(`indexingValues.${index}.key`).error?.message)}
                                    </div>
                                )}
                            </div>
                            <button className="btn" type="button" onClick={() => remove(index)}>Remove</button>
                        </div>
                    ))}
                </div>
                <button
                    className="btn"
                    type="button"
                    onClick={() => append({key: '', name: ''})}
                    disabled={fields.length >= 100}
                >
                    Add indexing value
                </button>
            </div>

            <LocalMediaProfilePreferredFormatField form={form} formatRegistry={PreferredFormatReg}/>
        </>
    )
}
