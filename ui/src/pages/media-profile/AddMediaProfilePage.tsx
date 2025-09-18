import {useCallback} from 'react'
import MediaProfileForm from '../../components/MediaProfileForm'
import {useNavigate} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import {
    MediaProfileCreate,
    MediaProfileCreateSchema,
    MediaProfileServerErrors
} from "../../types/schemas/media_profile";
import {useForm} from "react-hook-form";
import {zodResolver} from "@hookform/resolvers/zod";
import {buildServerAwareSubmit} from "../../utils/buildServerAwareSubmit";
import {WithRoot} from "../../types/form";
import {PreferredFormat} from "../../types/media_profile";

export default function AddMediaProfilePage() {
    const navigate = useNavigate()
    const qc = useQueryClient()

    const form = useForm<WithRoot<MediaProfileCreate>>({
        resolver: zodResolver(MediaProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: {
            name: "",
            outputTemplate: "/downloads/",
            preferredFormat: PreferredFormat.format1080p,
            downloadSeriesImages: false,
        },
    })

    const submitFn = async (data: MediaProfileCreate) => {
        return fetch(`${(window as any).appConfig.API_URL}/media-profiles`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data),
        })
    };

    const onSuccess = async (_result: any, {resetForm}: { resetForm: (v?: Partial<MediaProfileCreate>) => void }) => {
        await qc.invalidateQueries({queryKey: ['mediaProfiles']})
        resetForm();
        navigate('/profiles')
    };

    const onCancel = useCallback(() => navigate('/profiles'), [navigate])
    const onCreate = buildServerAwareSubmit(form, submitFn, {
        onSuccess,
        successStatuses: [201], // only accept 201 Created
        fallbackField: "name",
        mapMessage: MediaProfileServerErrors,
        fieldAlias: {slug: "name"},
    });

    const {formState: {isSubmitting}} = form;

    return (
        <section className="view" aria-labelledby="add-media-profile-title">
            <div className="view-header">
                <h1 id="add-media-profile-title">Add media profile</h1>
            </div>

            <form className="form" onSubmit={onCreate} noValidate>
                <MediaProfileForm form={form} />

                <div className="actions">
                    <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    <input type="submit" className="btn btn-primary" value="Create profile" disabled={isSubmitting} />
                </div>
            </form>
        </section>
    )
}
