import Switch from 'react-switch'
import {Controller, type FieldValues, UseFormReturn} from 'react-hook-form'
import Select from 'react-select'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {MediaProfileServerErrors} from '../../types/schemas/media_profile'
import {PreferredFormatReg} from "../../types/media_profile";

 type Props = {
    mode?: 'create' | 'update'
    form: UseFormReturn<any>
}

export function buildMediaProfileOnSubmit<TIn extends FieldValues, TOut extends FieldValues = TIn>(
    form: UseFormReturn<TIn>,
    submitFn: (data: TOut) => Promise<Response>,
    opts?: { mode?: 'create' | 'update'; onSuccess?: (result: any, ctx: any) => void }
) {
    const mode = opts?.mode ?? 'update'
    return buildServerAwareSubmit(form, submitFn, {
        onSuccess: opts?.onSuccess,
        successStatuses: mode === 'create' ? [201] : undefined,
        fallbackField: 'name' as any,
        mapMessage: MediaProfileServerErrors,
        fieldAlias: {slug: 'name'},
    })
}

export default function MediaProfileForm({form}: Props) {

    const {register, control, formState: {errors}} = form;


    return (
        <>
            {errors.root && (
                <div className="form-error-card" role="alert" aria-live="polite">
                    {String(errors.root.message)}
                </div>
            )}

            {/* Hidden fields for id and slug to include them in submit when present */}
            <input type="hidden" {...register('id', { setValueAs: (v) => (v === '' || v == null ? undefined : Number(v)) })} />
            <input type="hidden" {...register('slug')} />

            <div className="form-row">
                <label htmlFor="mp-name">Name</label>
                <input
                    id="mp-name"
                    className="input"
                    type="text"
                    placeholder="My 4k Profile"
                    {...register('name')}
                    aria-invalid={!!errors.name}
                    aria-describedby={errors.name ? 'mp-name-validate' : undefined}
                />
                {(errors.name) && (
                    <div id="mp-name-validate" className="error" role="alert" aria-live="polite">
                        {String((errors.name)?.message)}
                    </div>
                )}
            </div>

            <div className="form-row">
                <label htmlFor="mp-path">Output path template</label>
                <input
                    id="mp-path"
                    className="input"
                    type="text"
                    placeholder="/downloads/podcasts/{show}/{episode_name}.ext"
                    {...register('outputTemplate')}
                    aria-invalid={!!errors.outputTemplate}
                    aria-describedby={errors.outputTemplate ? 'mp-path-error' : undefined}
                />
                {errors.outputTemplate && (
                    <div id="mp-path-error" className="error" role="alert" aria-live="polite">
                        {String(errors.outputTemplate.message)}
                    </div>
                )}
                <div className="help">Use placeholders like {`{show}`} and {`{season}`}.</div>
            </div>

            <div className="form-row">
                <label htmlFor="mp-format">Preferred format</label>
                <Controller
                    control={control}
                    name="preferredFormat"
                    render={({ field }) => (
                        <Select
                            inputId="mp-format"
                            classNamePrefix="select"
                            options={PreferredFormatReg.options}
                            value={PreferredFormatReg.options.find(o => o.value === field.value) ?? null}
                            onChange={(opt) => field.onChange((opt as any)?.value ?? null)}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.preferredFormat}
                            aria-describedby={errors.preferredFormat ? 'mp-format-error' : undefined}
                            isClearable={false}
                        />
                    )}
                />
                {errors.preferredFormat && (
                    <div id="mp-format-error" className="error" role="alert" aria-live="polite">
                        {String(errors.preferredFormat.message)}
                    </div>
                )}
            </div>

            <div className="form-row" style={{alignItems: 'center'}}>
                <label htmlFor="mp-images">Download series images</label>
                <Controller
                    control={control}
                    name="downloadSeriesImages"
                    render={({field: {value: checked, onChange: setChecked}}) => (
                        <Switch
                            id="mp-images"
                            checked={!!checked}
                            onChange={setChecked}
                            onColor="#0ea5e9"
                            offColor="#d1d5db"
                            uncheckedIcon={false}
                            checkedIcon={false}
                        />
                    )}
                />
                {errors.downloadSeriesImages && (
                    <div id="mp-download-images-error" className="error" role="alert" aria-live="polite">
                        {String(errors.downloadSeriesImages.message)}
                    </div>
                )}
            </div>
        </>
    )
}
