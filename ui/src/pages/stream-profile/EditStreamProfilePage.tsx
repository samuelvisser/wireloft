import {useCallback, useEffect, useMemo, useState} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {useNavigate, useParams} from 'react-router-dom'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {useDownloadProfilesView} from '../../lib/queries'
import {StreamProfileReadView} from '../../types/schemas/stream_profile_base'
import StreamProfileForm from '../../components/StreamProfile/StreamProfileForm'
import ConfirmDialog from '../../components/ConfirmDialog/ConfirmDialog'
import {RssStreamProfileUpdateIn, RssStreamProfileUpdateSchema} from '../../types/schemas/rss_stream_profile'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'


type RouteParams = { type?: 'rss'; id?: string }

export default function EditStreamProfilePage() {
    const navigate = useNavigate()
    const {type, id} = useParams<RouteParams>()
    const qc = useQueryClient()

    const profileId = id ? Number(id) : undefined
    const {data: downloadProfiles} = useDownloadProfilesView()

    const {data: streamProfile, isLoading, error} = useQuery<StreamProfileReadView | undefined>({
        queryKey: ['streamProfile', id],
        enabled: !!id,
        refetchOnMount: 'always',
        queryFn: async ({signal}) => {
            const res = await fetch(`${(window as any).appConfig.API_URL}/stream-profiles/as-view/${profileId}`, { signal, credentials: 'include' })
            if (!res.ok) throw new Error(`Failed to load profile (${res.status})`)
            return await res.json() as Promise<StreamProfileReadView>
        },
    })

    const downloadProfileDefaults = useMemo(() => {
        if (!downloadProfiles) return undefined
        if (!streamProfile) return []
        return downloadProfiles
            .filter((profile) => profile.showSlug === streamProfile.showSlug)
            .map((profile) => ({
                id: profile.id,
                type: profile.type,
                preferredFormat: profile.localMediaProfilePreferredFormat,
                episodeTypes: profile.downloadProfileImpl.epIdTypeList,
                enabled: profile.enableProfile,
            }))
    }, [downloadProfiles, streamProfile?.showSlug])

    const form = useForm<RssStreamProfileUpdateIn>({
        resolver: zodResolver(RssStreamProfileUpdateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
    })
    const {formState: {errors, isSubmitting}} = form

    useEffect(() => {
        if (!streamProfile) return
        form.reset(RssStreamProfileUpdateSchema.parse(streamProfile.streamProfileImpl))
    }, [streamProfile, form])

    const onCancel = useCallback(() => navigate('/stream-profiles'), [navigate])

    const [regenerating, setRegenerating] = useState(false)
    const [regenerateConfirmOpen, setRegenerateConfirmOpen] = useState(false)
    const onRegenerateToken = useCallback(() => setRegenerateConfirmOpen(true), [])
    const regenerateToken = useCallback(async () => {
        if (!profileId || regenerating) return
        setRegenerateConfirmOpen(false)
        setRegenerating(true)
        try {
            const res = await fetch(`${(window as any).appConfig.API_URL}/rss-stream-profiles/${profileId}/regenerate-token`, {
                method: 'POST',
                credentials: 'include',
            })
            if (res.ok) {
                const updated = await res.json()
                form.setValue('feedUrl', updated.feedUrl, {shouldDirty: false})
                await qc.invalidateQueries({queryKey: ['streamProfile', id]})
                await qc.invalidateQueries({queryKey: ['streamProfilesView']})
            }
        } finally {
            setRegenerating(false)
        }
    }, [profileId, regenerating, id, qc, form])

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
                        <div style={{padding: '6px 0'}}>{streamProfile?.showTitle}</div>
                    </div>

                    {errors.root && (
                        <div className="form-error-card" role="alert" aria-live="polite">
                            {String(errors.root.message)}
                        </div>
                    )}

                    <StreamProfileForm
                        form={form as any}
                        mode="rss"
                        showRoot={false}
                        onRegenerateToken={onRegenerateToken}
                        regeneratingToken={regenerating}
                        downloadProfileDefaults={downloadProfileDefaults}
                        showSlug={streamProfile?.showSlug}
                    />

                    <div className="actions">
                        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                        <input type="submit" className="btn btn-primary" value="Save changes" disabled={isSubmitting} />
                    </div>
                </form>
            )}

            <ConfirmDialog
                open={regenerateConfirmOpen}
                title="Regenerate RSS feed URL"
                onDismiss={() => setRegenerateConfirmOpen(false)}
                icon={['fas', 'rotate']}
                iconTone="danger"
                confirmButton={{
                    label: 'Regenerate URL',
                    onClick: regenerateToken,
                    icon: ['fas', 'rotate'],
                    className: 'btn btn-danger',
                }}
            >
                <p>Regenerating will immediately invalidate the current feed URL.</p>
                <p>Any podcast app already subscribed to it will need the new URL.</p>
            </ConfirmDialog>
        </section>
    )
}
