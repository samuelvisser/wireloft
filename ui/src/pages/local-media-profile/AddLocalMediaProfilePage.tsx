import {useCallback, useState} from 'react'
import LocalMediaProfileForm, {LocalMediaProfileMode} from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import {useNavigate, useSearchParams} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import {
    LocalMediaProfileCreateIn, LocalMediaProfileCreateOut,
    LocalMediaProfileCreateSchema,
} from "../../types/schemas/local_media_profile";
import {useForm} from "react-hook-form";
import {zodResolver} from "@hookform/resolvers/zod";
import {WithRoot} from "../../types/form";
import {buildLocalMediaProfileOnSubmit} from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import SegmentedOptions from '../../components/SegmentedOptions/SegmentedOptions'
import ReadMore from '../../utils/ReadMore'

export default function AddLocalMediaProfilePage() {
    const navigate = useNavigate()
    const [searchParams] = useSearchParams()
    const qc = useQueryClient()
    const initialMode: LocalMediaProfileMode = searchParams.get('type') === 'movie' ? 'movie' : 'show'
    const [mode, setMode] = useState<LocalMediaProfileMode>(initialMode)
    const defaultValues: LocalMediaProfileCreateIn = initialMode === 'movie'
        ? {
            type: 'movie',
            name: '',
            outputTemplate: '/downloads/movies/{movie_title}/{title}.ext',
            preferredFormat: 'format_1080p',
            appendMediaTypeToFilename: true,
        }
        : {
            type: 'show',
            name: '',
            outputTemplate: '/downloads/shows/{show}/{episode_title}.ext',
            preferredFormat: 'format_audio_only',
            appendMediaTypeToFilename: true,
        }

    const form = useForm<WithRoot<LocalMediaProfileCreateIn>>({
        resolver: zodResolver(LocalMediaProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues,
    })

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
        navigate('/local-media-profiles')
    };

    const onCancel = useCallback(() => navigate('/local-media-profiles'), [navigate])
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
                                    ? '/downloads/movies/{movie_title}/{title}.ext'
                                    : '/downloads/shows/{show}/{episode_title}.ext',
                                {shouldDirty: true, shouldValidate: true},
                            )
                            form.setValue('appendMediaTypeToFilename', true, {shouldDirty: true, shouldValidate: true})
                            if (nextMode === 'movie' && form.getValues('preferredFormat') === 'format_audio_only') {
                                form.setValue('preferredFormat', 'format_1080p', {shouldDirty: true, shouldValidate: true})
                            }
                        }}
                        options={[
                            {
                                value: 'show',
                                label: 'Show',
                                description: (
                                    <ReadMore summary={<span>Store downloaded show episodes.</span>}>
                                        <p>Show profiles support episode, season, show, and publication-date placeholders.</p>
                                        <p>They can use either video formats or audio-only output.</p>
                                    </ReadMore>
                                ),
                            },
                            {
                                value: 'movie',
                                label: 'Movie',
                                description: (
                                    <ReadMore summary={<span>Store manually downloaded movies and trailers.</span>}>
                                        <p>Movie profiles can keep movie metadata for folders while using trailer metadata for trailer filenames.</p>
                                        <p>Movies and trailers are always downloaded as video.</p>
                                    </ReadMore>
                                ),
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
