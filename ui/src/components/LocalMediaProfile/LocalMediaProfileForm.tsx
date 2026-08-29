import {type FieldValues, UseFormReturn} from 'react-hook-form'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {LocalMediaProfileServerErrors} from '../../types/schemas/local_media_profile'
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

    const {register, formState: {errors}} = form;

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

            {mode === 'movie'
                ? <MovieLocalMediaProfileForm form={form}/>
                : <ShowLocalMediaProfileForm form={form}/>
            }
        </>
    )
}
