import {useCallback, useEffect} from 'react'
import {useNavigate, useParams} from 'react-router-dom'
import LocalMediaProfileForm from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {LocalMediaProfileUpdateIn, LocalMediaProfileUpdateOut, LocalMediaProfileUpdateSchema} from '../../types/schemas/local_media_profile'
import {WithRoot} from '../../types/form'
import {buildLocalMediaProfileOnSubmit} from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import {LocalMediaProfileTypeReg} from '../../types/local_media_profile'

export default function EditLocalMediaProfilePage() {
    const navigate = useNavigate()
    const {slug} = useParams<{ slug: string }>()
    const qc = useQueryClient()

    // Fetch the latest profile by slug
    const {data: profile, isLoading, error} = useQuery<LocalMediaProfileUpdateIn | undefined>({
        queryKey: ['localMediaProfile', slug],
        enabled: !!slug,
        refetchOnMount: 'always',
        queryFn: async ({signal}) => {
            const res = await fetch(`${(window as any).appConfig.API_URL}/local-media-profiles/${slug}`, { signal, credentials: 'include' })
            if (!res.ok) throw new Error(`Failed to load profile (${res.status})`)
            return await res.json() as Promise<LocalMediaProfileUpdateIn>
        },
    })

    // Initialize form unconditionally to keep hooks order consistent
    const form = useForm<WithRoot<LocalMediaProfileUpdateIn>>({
        resolver: zodResolver(LocalMediaProfileUpdateSchema),
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

    const onCancel = useCallback(() => navigate('/local-media-profiles'), [navigate])

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

    const submitFn = async (data: LocalMediaProfileUpdateOut) => {
        return fetch(`${(window as any).appConfig.API_URL}/local-media-profiles/${data.slug}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        })
    }

    const onSuccess = async () => {
        await qc.invalidateQueries({queryKey: ['localMediaProfiles']})
        await qc.invalidateQueries({queryKey: ['localMediaProfile', slug]})
        navigate('/local-media-profiles')
    }

    const onUpdate = buildLocalMediaProfileOnSubmit(form, submitFn, {
        onSuccess,
        mode: 'update',
    })

    const {formState: {isSubmitting}} = form

    return (
        <section className="view" aria-labelledby="edit-media-profile-title">
            <div className="view-header">
                <h1 id="edit-media-profile-title">Edit local media profile</h1>
            </div>

            <form className="form" onSubmit={onUpdate} noValidate>
                <div className="form-row">
                    <label>Profile type</label>
                    <div style={{padding: '6px 0'}}>{LocalMediaProfileTypeReg.getLabelLoose(profile.type)}</div>
                </div>

                <LocalMediaProfileForm form={form} mode={profile.type}/>

                <div className="actions">
                    <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    <input type="submit" className="btn btn-primary" value="Save changes" disabled={isSubmitting}/>
                </div>
            </form>
        </section>
    )
}
