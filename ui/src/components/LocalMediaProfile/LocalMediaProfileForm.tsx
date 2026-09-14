import {Controller, type FieldValues, UseFormReturn} from 'react-hook-form'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {LocalMediaProfileServerErrors} from '../../types/schemas/local_media_profile'
import {useSettings} from '../../lib/settings'
import ReadMore from '../../utils/ReadMore'
import MovieLocalMediaProfileForm from './MovieLocalMediaProfileForm'
import ShowLocalMediaProfileForm from './ShowLocalMediaProfileForm'

type Props = {
    mode: LocalMediaProfileMode
    form: UseFormReturn<any>
}

export type LocalMediaProfileMode = 'show' | 'movie'

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

export default function LocalMediaProfileForm({form, mode}: Props) {
    const {control, register, formState: {errors}} = form
    const {data: settings} = useSettings()
    const systemDownloadModeLabel = !settings
        ? 'Loading system setting…'
        : settings.values.downloadSettings.downloadMode === 'temporary'
            ? 'Save to temporary folder first'
            : 'Save directly to downloads'

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
            <input type="hidden" {...register('type')} />

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
                <label htmlFor="local-media-download-mode">Download behavior</label>
                <Controller
                    control={control}
                    name="downloadMode"
                    render={({field}) => (
                        <select
                            id="local-media-download-mode"
                            className="input"
                            value={field.value ?? 'system'}
                            onChange={field.onChange}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.downloadMode}
                            aria-describedby={errors.downloadMode ? 'local-media-download-mode-errors' : 'local-media-download-mode-help'}
                        >
                            <option value="system">System ({systemDownloadModeLabel})</option>
                            <option value="direct">Save directly to downloads</option>
                            <option value="temporary">Save to temporary folder first</option>
                        </select>
                    )}
                />
                {errors.downloadMode && (
                    <div id="local-media-download-mode-errors" className="error" role="alert" aria-live="polite">
                        {errors.downloadMode.message as string}
                    </div>
                )}
                <div className="help" id="local-media-download-mode-help">
                    <ReadMore summary="Choose whether downloads using this Local Media Profile inherit or override the system behavior.">
                        <p>
                            <strong>System</strong> follows the current system-wide default shown in parentheses.
                        </p>
                        <p>
                            <strong>Save directly to downloads</strong> writes download temporary files beside the final media destination and reserves the final filename while downloading.
                        </p>
                        <p>
                            <strong>Save to temporary folder first</strong> keeps download and processing files in the configured temporary folder and only publishes the completed media file at the end. This applies to automatic downloads, manual episode downloads, movies, and movie extras that use this profile.
                        </p>
                        <p>
                            Temporary mode is particularly useful when the destination is watched by a media server and you do not want it to pick up partly downloaded or empty media files.
                        </p>
                    </ReadMore>
                </div>
            </div>

            {mode === 'movie'
                ? <MovieLocalMediaProfileForm form={form}/>
                : <ShowLocalMediaProfileForm form={form}/>
            }
        </>
    )
}