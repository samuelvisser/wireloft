import {Controller, type FieldValues, UseFormReturn} from 'react-hook-form'
import Select from 'react-select'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {LocalMediaProfileServerErrors} from '../../types/schemas/local_media_profile'
import {PreferredFormatReg} from "../../types/local_media_profile";
import ReadMore from "../../utils/ReadMore";

type Props = {
    mode?: 'create' | 'update'
    form: UseFormReturn<any>
}

export function buildLocalMediaProfileOnSubmit<TIn extends FieldValues, TOut extends FieldValues = TIn>(
    form: UseFormReturn<TIn>,
    submitFn: (data: TOut) => Promise<Response>,
    opts?: { mode?: 'create' | 'update'; onSuccess?: (result: any, ctx: any) => void }
) {
    const mode = opts?.mode ?? 'update'
    return buildServerAwareSubmit(form, submitFn, {
        onSuccess: opts?.onSuccess,
        successStatuses: mode === 'create' ? [201] : undefined,
        fallbackField: 'name' as any,
        mapMessage: LocalMediaProfileServerErrors,
        fieldAlias: {slug: 'name'},
    })
}

export default function LocalMediaProfileForm({form}: Props) {

    const {register, control, formState: {errors}} = form;

    return (
        <>
            {errors.root && (
                <div className="form-error-card" role="alert" aria-live="polite">
                    {String(errors.root.message)}
                </div>
            )}

            {/* Hidden fields for id and slug to include them in submit when present */}
            <input type="hidden" {...register('id', {setValueAs: (v) => (v === '' || v == null ? undefined : Number(v))})} />
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
                    aria-describedby={errors.outputTemplate ? 'mp-path-error' : 'mp-path-help'}
                />
                {errors.outputTemplate && (
                    <div id="mp-path-error" className="error" role="alert" aria-live="polite">
                        {String(errors.outputTemplate.message)}
                    </div>
                )}

                <div className="help" id="mp-path-help">
                    <ReadMore summary={<span>Output path where Wireloft will download media to</span>}>
                        <p>This path can be dynamically generated based on placeholders. Supported placeholders:</p>
                        <ul>
                            <li><b>{'{show}'}</b>: The slug of the show (the show's name in the URL)</li>
                            <li><b>{'{show_title}'}</b>: The title of the show</li>
                            <li><b>{'{season}'}</b>: The slug of the season (the season's name in the URL)</li>
                            <li><b>{'{season_name}'}</b>: The name of the season</li>
                            <li><b>{'{episode}'}</b>: The slug of the episode (the episode's name in the URL)</li>
                            <li><b>{'{episode_title}'}</b> or <b>{'{title}'}</b>: The title of the episode</li>
                            <li><b>{'{episode_type}'}</b>: The episode type as categorized by Wireloft<br />
                            Supported types are: 'ep', 'ep-extra', 'auxiliary', 'trailer'</li>
                            <li><b>{'{episode_number}'}</b>: The episode number</li>
                            <li><b>{'{episode_published_date}'}</b> or <b>{'{date}'}</b>: The published date of the episode (Y-m-d)</li>
                            <li><b>{'{episode_published_time}'}</b> or <b>{'{time}'}</b>: The published time of the episode (H:M:S)</li>
                            <li><b>{'{episode_published_datetime}'}</b> or <b>{'{datetime}'}</b>: The published date and time of the episode (Y-m-d H:M:S)</li>
                        </ul>
                    </ReadMore>
                </div>
            </div>

            <div className="form-row">
                <label htmlFor="mp-format">Preferred format</label>
                <Controller
                    control={control}
                    name="preferredFormat"
                    render={({field}) => (
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
        </>
    )
}
