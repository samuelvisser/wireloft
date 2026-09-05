import {useCallback, useEffect, useMemo, useState} from 'react'
import LocalMediaProfileForm, {LocalMediaProfileMode} from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import {useNavigate, useSearchParams} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import {
    LocalMediaProfileCreateIn, LocalMediaProfileCreateOut,
    LocalMediaProfileCreateSchema,
    MovieLocalMediaProfileCreateSchema,
    ShowLocalMediaProfileCreateSchema,
} from "../../types/schemas/local_media_profile";
import {useForm} from "react-hook-form";
import {zodResolver} from "@hookform/resolvers/zod";
import {WithRoot} from "../../types/form";
import {buildLocalMediaProfileOnSubmit} from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import SegmentedOptions from '../../components/SegmentedOptions/SegmentedOptions'
import {
    addLocalMediaProfileDraftKey,
    clearLocalMediaProfileDraft,
    loadLocalMediaProfileDraft,
    saveLocalMediaProfileDraft,
} from '../../components/LocalMediaProfile/localMediaProfileDraft'
import {getZodDefaults} from '../../utils/defaultZod'

const SHOW_DEFAULT_TEMPLATE = '/downloads/shows/{{ show }}/{{ episode_title }}.ext'
const MOVIE_DEFAULT_TEMPLATE = "/downloads/movies/{{ movie_title }}/{{ title }}{% if media_type != 'movie' %}-{{ media_type }}{% endif %}.ext"

function defaultsForMode(mode: LocalMediaProfileMode): LocalMediaProfileCreateIn {
    if (mode === 'movie') {
        return {
            ...getZodDefaults(MovieLocalMediaProfileCreateSchema),
            type: 'movie',
            name: '',
            outputTemplate: MOVIE_DEFAULT_TEMPLATE,
        }
    }

    return {
        ...getZodDefaults(ShowLocalMediaProfileCreateSchema),
        type: 'show',
        name: '',
        outputTemplate: SHOW_DEFAULT_TEMPLATE,
    }
}

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
    const defaultValues = {
        ...defaultsForMode(initialMode),
        ...(restoredDraft?.mode === initialMode ? restoredDraft.values : {}),
        type: initialMode,
    } as LocalMediaProfileCreateIn

    const form = useForm<WithRoot<LocalMediaProfileCreateIn>>({
        resolver: zodResolver(LocalMediaProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues,
    })

    useEffect(() => {
        const subscription = form.watch((values) => {
            const draftMode: LocalMediaProfileMode = values.type === 'movie' ? 'movie' : 'show'
            saveLocalMediaProfileDraft<LocalMediaProfileCreateIn>(draftKey, {
                mode: draftMode,
                values: values as Partial<LocalMediaProfileCreateIn>,
            })
        })
        return () => subscription.unsubscribe()
    }, [draftKey, form])

    const submitFn = async (data: LocalMediaProfileCreateOut) => {
        return fetch(`${(window as any).appConfig.API_URL}/local-media-profiles`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        })
    };

    const onSuccess = async (_result: any, {resetForm}: { resetForm: (v?: Partial<LocalMediaProfileCreateIn>) => void }) => {
        await qc.invalidateQueries({queryKey: ['localMediaProfiles']})
        resetForm();
        clearLocalMediaProfileDraft(draftKey)
        navigate('/local-media-profiles')
    };

    const onCancel = useCallback(() => {
        clearLocalMediaProfileDraft(draftKey)
        navigate('/local-media-profiles')
    }, [draftKey, navigate])
    const onCreate = buildLocalMediaProfileOnSubmit(form as any, submitFn, {
        onSuccess,
        mode: 'create',
    });

    const {formState: {isSubmitting}} = form;

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
                        onChange={(value) => {
                            const nextMode = value as LocalMediaProfileMode
                            setMode(nextMode)
                            form.setValue('type', nextMode, {shouldDirty: true, shouldValidate: true})
                            form.setValue(
                                'outputTemplate',
                                nextMode === 'movie'
                                    ? MOVIE_DEFAULT_TEMPLATE
                                    : SHOW_DEFAULT_TEMPLATE,
                                {shouldDirty: true, shouldValidate: true},
                            )
                            if (nextMode === 'movie' && form.getValues('preferredFormat') === 'format_audio_only') {
                                form.setValue('preferredFormat', 'format_1080p', {shouldDirty: true, shouldValidate: true})
                            }
                        }}
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
                    <input type="submit" className="btn btn-primary" value="Create profile" disabled={isSubmitting} />
                </div>
            </form>
        </section>
    )
}
