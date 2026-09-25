import {type FieldValues, UseFormReturn} from 'react-hook-form'

import {LocalMediaProfileServerErrors} from '../../types/schemas/local_media_profile'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import LocalMediaProfileCommonFields from './LocalMediaProfileCommonFields'
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
    return (
        <>
            <LocalMediaProfileCommonFields form={form}/>
            {mode === 'movie'
                ? <MovieLocalMediaProfileForm form={form}/>
                : <ShowLocalMediaProfileForm form={form}/>
            }
        </>
    )
}
