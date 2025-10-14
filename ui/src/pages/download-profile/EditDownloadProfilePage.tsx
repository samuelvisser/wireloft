import {useCallback} from 'react'
import {Controller, useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {useNavigate, useParams} from 'react-router-dom'
import {useLocalMediaProfiles, useShowSeasons} from '../../lib/queries'
import DownloadProfileForm, {DownloadProfileMode} from '../../components/DownloadProfile/DownloadProfileForm'
import {
    PodcastDownloadProfileUpdateIn,
    PodcastDownloadProfileUpdateSchema
} from '../../types/schemas/podcast_download_profile'
import {
    SeriesDownloadProfileUpdateIn,
    SeriesDownloadProfileUpdateSchema
} from '../../types/schemas/series_download_profile'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {LocalMediaProfileRead} from '../../types/schemas/local_media_profile'
import Select from 'react-select'
import {useLocalMediaProfileSelectRegistry} from "../../types/local_media_profile";
import {DownloadProfileReadView} from "../../types/schemas/download_profile_base";
import {useQuery, useQueryClient} from "@tanstack/react-query";


type RouteParams = { type?: DownloadProfileMode; id?: string }

type AnyUpdate = PodcastDownloadProfileUpdateIn | SeriesDownloadProfileUpdateIn

export default function EditDownloadProfilePage() {
    const navigate = useNavigate()
    const {type, id} = useParams<RouteParams>()
    const qc = useQueryClient()

    const mode: DownloadProfileMode | undefined = (type === 'podcast' || type === 'series') ? type : undefined
    const profileId = id ? Number(id) : undefined

    // Fetch the latest profile by id
    const {data: downloadProfile, isLoading, error} = useQuery<DownloadProfileReadView | undefined>({
        queryKey: ['downloadProfile', id],
        enabled: !!id,
        refetchOnMount: 'always',
        queryFn: async ({signal}) => {
            const res = await fetch(`${(window as any).appConfig.API_URL}/download-profiles/as-view/${profileId}`, { signal, credentials: 'include' })
            if (!res.ok) throw new Error(`Failed to load profile (${res.status})`)
            return await res.json() as Promise<DownloadProfileReadView>
        },
    })
    const showTitle: string | undefined = downloadProfile?.showTitle

    const {data: mediaProfiles} = useLocalMediaProfiles()
    const {data: seasonsData} = useShowSeasons(downloadProfile?.showSlug)

    const formPodcast = useForm<PodcastDownloadProfileUpdateIn>({
        resolver: zodResolver(PodcastDownloadProfileUpdateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: {
            localMediaProfileId: (mediaProfiles?.[0] as LocalMediaProfileRead | undefined)?.id ?? 0,
            enableProfile: true,
            downloadWithCountdown: false,
            redownloadFinal: true,
            downloadDaysInPast: 180,
            deleteOlderEpisodes: true,
        },
    })

    const formSeries = useForm<SeriesDownloadProfileUpdateIn>({
        resolver: zodResolver(SeriesDownloadProfileUpdateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: {
            localMediaProfileId: (mediaProfiles?.[0] as LocalMediaProfileRead | undefined)?.id ?? 0,
            enableProfile: true,
            seasons: [],
            includeUpcomingSeasons: true,
        },
    })

    const form = (mode === 'podcast' ? formPodcast : formSeries) as any
    const {formState: {errors}} = form

    const mediaProfileReg = useLocalMediaProfileSelectRegistry(mediaProfiles)

    const onCancel = useCallback(() => navigate('/download-profiles'), [navigate])

    const submitFn = async (data: AnyUpdate) => {
        if (!mode || !profileId) return undefined as any
        const base = (window as any).appConfig.API_URL
        const endpoint = mode === 'podcast' ? 'podcast-download-profiles' : 'series-download-profiles'
        return fetch(`${base}/${endpoint}/${profileId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        })
    }

    const onSuccess = async () => {
        await qc.invalidateQueries({queryKey: ['podcastDownloadProfiles']})
        await qc.invalidateQueries({queryKey: ['seriesDownloadProfiles']})
        await qc.invalidateQueries({queryKey: ['downloadProfilesView']})

        navigate('/download-profiles')
    }

    const onSubmit = buildServerAwareSubmit(form as any, async (dataOut: AnyUpdate) => {
        const res = await submitFn(dataOut)
        if (res?.ok) await onSuccess()
        return res
    })

    const {formState: {isSubmitting}} = form

    if (!mode || !profileId) {
        return (
            <section className="view" aria-labelledby="edit-download-profile-title">
                <div className="view-header">
                    <h1 id="edit-download-profile-title">Edit download profile</h1>
                </div>
                <p>Profile not found.</p>
                <div className="actions" style={{marginTop: 12}}>
                    <button type="button" className="btn" onClick={() => navigate('/download-profiles')}>Back</button>
                </div>
            </section>
        )
    }

    return (
        <section className="view" aria-labelledby="edit-download-profile-title">
            <div className="view-header">
                <h1 id="edit-download-profile-title">Edit download profile</h1>
            </div>

            {isLoading ? (
                <p>Loading…</p>
            ) : error ? (
                <p>{error.message}</p>
            ) : (
                <form className="form" onSubmit={onSubmit} noValidate>
                    <div className="form-row">
                        <label>Profile type</label>
                        <div style={{padding: '6px 0'}}>{mode === 'podcast' ? 'Podcast' : 'Series'}</div>
                    </div>

                    <div className="form-row">
                        <label>Show</label>
                        <div style={{padding: '6px 0'}}>{showTitle}</div>
                    </div>


                    {errors.root && (
                        <div className="form-error-card" role="alert" aria-live="polite">
                            {String(errors.root.message)}
                        </div>
                    )}

                    <div className="form-row">
                        <label htmlFor="local-media-profile">Local Media Profile</label>
                        <Controller
                            control={(form as any).control}
                            name={"localMediaProfileId" as any}
                            render={({field}) => (
                                <Select
                                    inputId="local-media-profile"
                                    classNamePrefix="select"
                                    options={mediaProfileReg.options}
                                    value={mediaProfileReg.options.find(o => Number(o.value) === field.value) ?? null}
                                    onChange={(opt) => field.onChange((opt as any) ? Number((opt as any).value) : null)}
                                    onBlur={field.onBlur}
                                    isDisabled={mediaProfileReg.options.length === 0}
                                    placeholder={!mediaProfiles ? 'Loading profiles...' : mediaProfileReg.options.length === 0 ? 'No profiles found' : undefined}
                                    aria-invalid={!!errors.localMediaProfileId}
                                    aria-describedby={errors.localMediaProfileId ? 'local-media-profile-errors' : undefined}
                                />
                            )}
                        />
                        {errors.localMediaProfileId && (
                            <div id="local-media-profile-errors" className="error" role="alert" aria-live="polite">
                                {errors.localMediaProfileId.message as string}
                            </div>
                        )}
                    </div>

                    <DownloadProfileForm form={form as any} mode={mode} seasons={seasonsData} showRoot={false}/>

                    <div className="actions">
                        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                        <input type="submit" className="btn btn-primary" value="Save changes" disabled={isSubmitting}/>
                    </div>
                </form>
            )}
        </section>
    )
}
