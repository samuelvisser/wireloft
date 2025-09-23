import {useCallback, useEffect} from 'react'
import {useNavigate, useParams} from 'react-router-dom'
import MediaProfileForm from '../../components/MediaProfile/MediaProfileForm'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {MediaProfileUpdateIn, MediaProfileUpdateOut, MediaProfileUpdateSchema} from '../../types/schemas/media_profile'
import {WithRoot} from '../../types/form'
import {buildMediaProfileOnSubmit} from '../../components/MediaProfile/MediaProfileForm'

export default function EditMediaProfilePage() {
    const navigate = useNavigate()
    const {slug} = useParams<{ slug: string }>()
    const qc = useQueryClient()

    // Fetch the latest profile by slug
    const {data: profile, isLoading, error} = useQuery<MediaProfileUpdateIn | undefined>({
        queryKey: ['mediaProfile', slug],
        enabled: !!slug,
        refetchOnMount: 'always',
        queryFn: async ({signal}) => {
            const res = await fetch(`${(window as any).appConfig.API_URL}/media-profiles/${slug}`, {signal})
            if (!res.ok) throw new Error(`Failed to load profile (${res.status})`)
            return await res.json() as Promise<MediaProfileUpdateIn>
        },
    })

    // Initialize form unconditionally to keep hooks order consistent
    const form = useForm<WithRoot<MediaProfileUpdateIn>>({
        resolver: zodResolver(MediaProfileUpdateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: profile,
    })

    // When the profile loads, reset the form with fetched values
    useEffect(() => {
        if (profile) {
            form.reset(profile)
        }
    }, [profile, form])

    const onCancel = useCallback(() => navigate('/profiles'), [navigate])

    if (isLoading) {
        return (
            <section className="view" aria-labelledby="edit-media-profile-title">
                <div className="view-header">
                    <h1 id="edit-media-profile-title">Edit media profile</h1>
                </div>
                <p>Loading…</p>
            </section>
        )
    }

    if (!slug || !profile || error) {
        return (
            <section className="view" aria-labelledby="edit-media-profile-title">
                <div className="view-header">
                    <h1 id="edit-media-profile-title">Edit media profile</h1>
                </div>
                <p>Profile not found.</p>
                <div className="actions" style={{marginTop: 12}}>
                    <button type="button" className="btn" onClick={onCancel}>Back</button>
                </div>
            </section>
        )
    }

    const submitFn = async (data: MediaProfileUpdateOut) => {
        return fetch(`${(window as any).appConfig.API_URL}/media-profiles/${data.slug}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data),
        })
    }

    const onSuccess = async () => {
        await qc.invalidateQueries({queryKey: ['mediaProfiles']})
        await qc.invalidateQueries({queryKey: ['mediaProfile', slug]})
        navigate('/profiles')
    }

    const onUpdate = buildMediaProfileOnSubmit(form, submitFn, {
        onSuccess,
        mode: 'update',
    })

    const {formState: {isSubmitting}} = form

    return (
        <section className="view" aria-labelledby="edit-media-profile-title">
            <div className="view-header">
                <h1 id="edit-media-profile-title">Edit media profile</h1>
            </div>

            <form className="form" onSubmit={onUpdate} noValidate>
                <MediaProfileForm form={form}/>

                <div className="actions">
                    <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    <input type="submit" className="btn btn-primary" value="Save changes" disabled={isSubmitting}/>
                </div>
            </form>
        </section>
    )
}
