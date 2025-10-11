import {useCallback} from 'react'
import LocalMediaProfileForm from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import {useNavigate} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import {
    LocalMediaProfileCreateIn, LocalMediaProfileCreateOut,
    LocalMediaProfileCreateSchema,
} from "../../types/schemas/local_media_profile";
import {useForm} from "react-hook-form";
import {zodResolver} from "@hookform/resolvers/zod";
import {WithRoot} from "../../types/form";
import {buildLocalMediaProfileOnSubmit} from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import {PreferredFormatReg} from "../../types/local_media_profile";

export default function AddLocalMediaProfilePage() {
    const navigate = useNavigate()
    const qc = useQueryClient()

    const form = useForm<WithRoot<LocalMediaProfileCreateIn>>({
        resolver: zodResolver(LocalMediaProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: {
            name: "",
            outputTemplate: "/downloads/",
            preferredFormat: PreferredFormatReg.Enum.format_audio_only,
            downloadSeriesImages: false,
        },
    })

    const submitFn = async (data: LocalMediaProfileCreateOut) => {
        return fetch(`${(window as any).appConfig.API_URL}/local-media-profiles`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        })
    };

    const onSuccess = async (_result: any, {resetForm}: { resetForm: (v?: Partial<LocalMediaProfileCreateOut>) => void }) => {
        await qc.invalidateQueries({queryKey: ['localMediaProfiles']})
        resetForm();
        navigate('/local-media-profiles')
    };

    const onCancel = useCallback(() => navigate('/local-media-profiles'), [navigate])
    const onCreate = buildLocalMediaProfileOnSubmit(form, submitFn, {
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
                <LocalMediaProfileForm form={form} />

                <div className="actions">
                    <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    <input type="submit" className="btn btn-primary" value="Create profile" disabled={isSubmitting} />
                </div>
            </form>
        </section>
    )
}
