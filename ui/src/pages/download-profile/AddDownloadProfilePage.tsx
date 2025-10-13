import {useCallback, useMemo, useState} from 'react'
import {Controller, useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {useNavigate} from 'react-router-dom'
import {useLocalMediaProfiles, usePodcastDownloadProfiles, useSeriesDownloadProfiles, useShows} from '../../lib/queries'
import DownloadProfileForm, {DownloadProfileMode} from '../../components/DownloadProfile/DownloadProfileForm'
import {PodcastDownloadProfileCreateIn, PodcastDownloadProfileCreateSchema} from '../../types/schemas/podcast_download_profile'
import {SeriesDownloadProfileCreateIn, SeriesDownloadProfileCreateSchema} from '../../types/schemas/series_download_profile'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import Select from 'react-select'
import {createSelectRegistry} from '../../utils/selectRegistry'
import {ShowRead} from "../../types/schemas/show";


type PodcastForm = PodcastDownloadProfileCreateIn

type SeriesForm = SeriesDownloadProfileCreateIn

type AnyForm = PodcastForm | SeriesForm


export default function AddDownloadProfilePage() {
    const navigate = useNavigate()

    const [mode, setMode] = useState<DownloadProfileMode>('podcast')

    const {data: shows} = useShows()
    const {data: mediaProfiles} = useLocalMediaProfiles()

    // Build registries for shows and local media profiles using createSelectRegistry
    const showReg = useMemo(() => {
        const spec: Record<string, { label: string }> = {}
        if (Array.isArray(shows)) {
            for (const s of shows as ShowRead[]) {
                const id = s.id
                const name = s.title
                spec[String(id)] = {label: String(name)}
            }
        }
        return createSelectRegistry('Show', spec as any)
    }, [shows])

    const mediaProfileReg = useMemo(() => {
        const spec: Record<string, { label: string }> = {}
        if (Array.isArray(mediaProfiles)) {
            for (const p of mediaProfiles as any[]) {
                const id = (p as any).id
                const name = (p as any).name ?? String(id)
                if (typeof id === 'number') spec[String(id)] = {label: String(name)}
            }
        }
        return createSelectRegistry('LocalMediaProfile', spec as any)
    }, [mediaProfiles])

    const defaultValuesPodcast: PodcastForm = useMemo(() => ({
        showId: Number((showReg.options?.[0]?.value ?? 0)),
        localMediaProfileId: Number((mediaProfileReg.options?.[0]?.value ?? 0)),
        enableProfile: true,
        downloadWithCountdown: false,
        redownloadFinal: true,
        downloadDaysInPast: 180,
        deleteOlderEpisodes: true,
    }), [showReg, mediaProfileReg])

    const defaultValuesSeries: SeriesForm = useMemo(() => ({
        showId: Number((showReg.options?.[0]?.value ?? 0)),
        localMediaProfileId: Number((mediaProfileReg.options?.[0]?.value ?? 0)),
        enableProfile: true,
        seasons: [],
        includeUpcomingSeasons: true,
    }), [showReg, mediaProfileReg])

    const formPodcast = useForm<PodcastForm>({
        resolver: zodResolver(PodcastDownloadProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: defaultValuesPodcast,
    })

    const formSeries = useForm<SeriesForm>({
        resolver: zodResolver(SeriesDownloadProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: defaultValuesSeries,
    })

    const form = mode === 'podcast' ? formPodcast : formSeries

    const onCancel = useCallback(() => navigate('/download-profiles'), [navigate])

    const {refetch: refetchPod} = usePodcastDownloadProfiles()
    const {refetch: refetchSer} = useSeriesDownloadProfiles()

    const submitFn = async (data: AnyForm) => {
        const base = (window as any).appConfig.API_URL
        const endpoint = mode === 'podcast' ? 'podcast-download-profiles' : 'series-download-profiles'
        return fetch(`${base}/${endpoint}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        })
    }

    const onSuccess = async () => {
        await Promise.all([refetchPod(), refetchSer()])
        navigate('/download-profiles')
    }

    const onSubmit = buildServerAwareSubmit(form as any, async (dataOut: AnyForm) => {
        const res = await submitFn(dataOut)
        if (res?.ok) await onSuccess()
        return res
    })

    const {formState: {isSubmitting}} = form

    return (
        <section className="view" aria-labelledby="add-download-profile-title">
            <div className="view-header">
                <h1 id="add-download-profile-title">Add download profile</h1>
            </div>

            <form className="form" onSubmit={onSubmit} noValidate>
                <div className="form-row">
                    <label>Profile type</label>
                    <div style={{display: 'flex', gap: 12}}>
                        <label><input type="radio" name="dp-type" checked={mode === 'podcast'} onChange={() => setMode('podcast')}/> Podcast</label>
                        <label><input type="radio" name="dp-type" checked={mode === 'series'} onChange={() => setMode('series')}/> Series</label>
                    </div>
                </div>

                <div className="form-row">
                    <label htmlFor="show-id">Show</label>
                    <Controller
                        control={(form as any).control}
                        name={"showId" as any}
                        render={({field}) => (
                            <Select
                                inputId="show-id"
                                classNamePrefix="select"
                                options={showReg.options}
                                value={showReg.options.find(o => Number(o.value) === field.value) ?? null}
                                onChange={(opt) => field.onChange((opt as any) ? Number((opt as any).value) : null)}
                                onBlur={field.onBlur}
                                isDisabled={showReg.options.length === 0}
                                placeholder={showReg.options.length === 0 ? 'No shows found' : undefined}
                            />
                        )}
                    />
                </div>

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
                            />
                        )}
                    />
                </div>

                <DownloadProfileForm form={form as any} mode={mode} seasons={[]}/>

                <div className="actions">
                    <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    <input type="submit" className="btn btn-primary" value="Create profile" disabled={isSubmitting}/>
                </div>
            </form>
        </section>
    )
}
