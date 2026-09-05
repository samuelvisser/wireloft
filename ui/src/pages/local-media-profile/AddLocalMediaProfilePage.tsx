import {useCallback, useEffect, useMemo, useState} from 'react'
import LocalMediaProfileForm, {LocalMediaProfileMode} from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import {useNavigate, useSearchParams} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import {
    LocalMediaProfileCreateIn,
    LocalMediaProfileCreateOut,
} from '../../types/schemas/local_media_profile'
import {
    MovieLocalMediaProfileCreateIn,
    MovieLocalMediaProfileCreateSchema,
} from '../../types/schemas/movie_local_media_profile'
import {
    ShowLocalMediaProfileCreateIn,
    ShowLocalMediaProfileCreateSchema,
} from '../../types/schemas/show_local_media_profile'
import {useForm, UseFormReturn} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {WithRoot} from '../../types/form'
import {buildLocalMediaProfileOnSubmit} from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import SegmentedOptions from '../../components/SegmentedOptions/SegmentedOptions'
import {
    addLocalMediaProfileDraftKey,
    clearLocalMediaProfileDraft,
    loadLocalMediaProfileDraft,
    saveLocalMediaProfileDraft,
} from '../../components/LocalMediaProfile/localMediaProfileDraft'
import {getZodDefaults} from '../../utils/defaultZod'


export default function AddLocalMediaProfilePage() {
    const navigate = useNavigate()
    const [searchParams] = useSearchParams()
    const qc = useQueryClient()
    const draftKey = addLocalMediaProfileDraftKey()
    const restoredDraft = useMemo(
        () => loadLocalMediaProfileDraft<LocalMediaProfileCreateIn>(draftKey),
        [draftKey],
    )
    const requestedMode = searchParams.get('type')
    const explicitMode = requestedMode === 'movie' || requestedMode === 'show' ? requestedMode : undefined
    const initialMode: LocalMediaProfileMode = explicitMode ?? restoredDraft?.mode ?? 'show'
    const [mode, setMode] = useState<LocalMediaProfileMode>(initialMode)

    const formShow = useForm<WithRoot<ShowLocalMediaProfileCreateIn>>({
        resolver: zodResolver(ShowLocalMediaProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: {
            ...getZodDefaults(ShowLocalMediaProfileCreateSchema),
            ...(restoredDraft?.mode === 'show'
                ? restoredDraft.values as Partial<ShowLocalMediaProfileCreateIn>
                : {}),
        },
    })

    const formMovie = useForm<WithRoot<MovieLocalMediaProfileCreateIn>>({
        resolver: zodResolver(MovieLocalMediaProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: {
            ...getZodDefaults(MovieLocalMediaProfileCreateSchema),
            ...(restoredDraft?.mode === 'movie'
                ? restoredDraft.values as Partial<MovieLocalMediaProfileCreateIn>
                : {}),
        },
    })

    const form = (mode === 'movie' ? formMovie : formShow) as UseFormReturn<any>

    useEffect(() => {
        const saveDraft = (values: Partial<LocalMediaProfileCreateIn>) => {
            saveLocalMediaProfileDraft<LocalMediaProfileCreateIn>(draftKey, {
                mode,
                values,
            })
        }

        saveDraft(form.getValues() as Partial<LocalMediaProfileCreateIn>)
        const subscription = form.watch((values) => {
            saveDraft(values as Partial<LocalMediaProfileCreateIn>)
        })
        return () => subscription.unsubscribe()
    }, [draftKey, form, mode])

    const submitFn = async (data: LocalMediaProfileCreateOut) => {
        return fetch(`${(window as any).appConfig.API_URL}/local-media-profiles`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        })
    }

    const onSuccess = async () => {
        await qc.invalidateQueries({queryKey: ['localMediaProfiles']})
        clearLocalMediaProfileDraft(draftKey)
        navigate('/local-media-profiles')
    }

    const onCancel = useCallback(() => {
        clearLocalMediaProfileDraft(draftKey)
        navigate('/local-media-profiles')
    }, [draftKey, navigate])

    const onCreate = buildLocalMediaProfileOnSubmit(form, submitFn, {
        onSuccess,
        mode: 'create',
    })

    const {formState: {isSubmitting}} = form

    return (
        <section className="view" aria-labelledby="add-media-profile-title">
            <div className="view-header">
                <h1 id="add-media-profile-title">Add local media profile</h1>
            </div>

            <form className="form" onSubmit={onCreate} noValidate>
                <div className="form-row">
                    <label>Profile type</label>
                    <SegmentedOptions
                        name="local-media-profile-mode"
                        value={mode}
                        onChange={(value) => setMode(value as LocalMediaProfileMode)}
                        options={[
                            {
                                value: 'show',
                                label: 'Show',
                                description: 'Store downloaded show episodes',
                            },
                            {
                                value: 'movie',
                                label: 'Movie',
                                description: 'Store manually downloaded movies and their extras',
                            },
                        ]}
                    />
                </div>

                <LocalMediaProfileForm form={form} mode={mode}/>

                <div className="actions">
                    <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    <input type="submit" className="btn btn-primary" value="Create profile" disabled={isSubmitting}/>
                </div>
            </form>
        </section>
    )
}
