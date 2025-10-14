import {useCallback} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {useNavigate, useParams} from 'react-router-dom'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {StreamProfileReadView} from '../../types/schemas/stream_profile_base'
import StreamProfileForm from '../../components/StreamProfile/StreamProfileForm'
import {RssStreamProfileUpdateIn, RssStreamProfileUpdateSchema} from '../../types/schemas/rss_stream_profile'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'


type RouteParams = { type?: 'rss'; id?: string }

export default function EditStreamProfilePage() {
    const navigate = useNavigate()
    const {type, id} = useParams<RouteParams>()
    const qc = useQueryClient()

    const profileId = id ? Number(id) : undefined

    // Fetch the latest profile by id (as-view)
    const {data: profile, isLoading, error} = useQuery<StreamProfileReadView | undefined>({
        queryKey: ['streamProfile', id],
        enabled: !!id,
        refetchOnMount: 'always',
        queryFn: async ({signal}) => {
            const res = await fetch(`${(window as any).appConfig.API_URL}/stream-profiles/as-view/${profileId}`, { signal, credentials: 'include' })
            if (!res.ok) throw new Error(`Failed to load profile (${res.status})`)
            return await res.json() as Promise<StreamProfileReadView>
        },
    })

    const form = useForm<RssStreamProfileUpdateIn>({
        resolver: zodResolver(RssStreamProfileUpdateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: {
            enableProfile: true,
            useDownloads: true,
            useDwStream: true,
            preferredFormat: 'mp4',
            requireExactMatch: true,
            feedUrl: '',
        } as any,
    })
    const {formState: {errors, isSubmitting}} = form

    const onCancel = useCallback(() => navigate('/stream-profiles'), [navigate])

    const submitFn = async (data: RssStreamProfileUpdateIn) => {
        if (!profileId) return undefined as any
        return fetch(`${(window as any).appConfig.API_URL}/rss-stream-profiles/${profileId}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        })
    }

    const onSuccess = async () => {
        await qc.invalidateQueries({queryKey: ['rssStreamProfiles']})
        await qc.invalidateQueries({queryKey: ['streamProfilesView']})
        navigate('/stream-profiles')
    }

    const onSubmit = buildServerAwareSubmit(form as any, async (dataOut: RssStreamProfileUpdateIn) => {
        const res = await submitFn(dataOut)
        if (res?.ok) await onSuccess()
        return res
    })

    if (type !== 'rss' || !profileId) {
        return (
            <section className="view" aria-labelledby="edit-stream-profile-title">
                <div className="view-header">
                    <h1 id="edit-stream-profile-title">Edit stream profile</h1>
                </div>
                <p>Profile not found.</p>
                <div className="actions" style={{marginTop: 12}}>
                    <button type="button" className="btn" onClick={() => navigate('/stream-profiles')}>Back</button>
                </div>
            </section>
        )
    }

    return (
        <section className="view" aria-labelledby="edit-stream-profile-title">
            <div className="view-header">
                <h1 id="edit-stream-profile-title">Edit stream profile</h1>
            </div>

            {isLoading ? (
                <p>Loading…</p>
            ) : error ? (
                <p>{error.message}</p>
            ) : (
                <form className="form" onSubmit={onSubmit} noValidate>
                    <div className="form-row">
                        <label>Profile type</label>
                        <div style={{padding: '6px 0'}}>RSS</div>
                    </div>

                    <div className="form-row">
                        <label>Show</label>
                        <div style={{padding: '6px 0'}}>{profile?.showTitle}</div>
                    </div>

                    {errors.root && (
                        <div className="form-error-card" role="alert" aria-live="polite">
                            {String(errors.root.message)}
                        </div>
                    )}

                    {/* Stream Profile Form (common + variant-specific fields) */}
                    <StreamProfileForm form={form as any} mode="rss" showRoot={false} />

                    <div className="actions">
                        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                        <input type="submit" className="btn btn-primary" value="Save changes" disabled={isSubmitting} />
                    </div>
                </form>
            )}
        </section>
    )
}
