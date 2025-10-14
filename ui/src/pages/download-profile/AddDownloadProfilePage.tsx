import {useCallback, useMemo, useState} from 'react'
import {Controller, useForm, UseFormReturn} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {useNavigate} from 'react-router-dom'
import {useLocalMediaProfiles, useShows} from '../../lib/queries'
import DownloadProfileForm, {DownloadProfileMode} from '../../components/DownloadProfile/DownloadProfileForm'
import {
    PodcastDownloadProfileCreateIn, PodcastDownloadProfileCreateOut,
    PodcastDownloadProfileCreateSchema
} from '../../types/schemas/podcast_download_profile'
import {
    SeriesDownloadProfileCreateIn, SeriesDownloadProfileCreateOut,
    SeriesDownloadProfileCreateSchema
} from '../../types/schemas/series_download_profile'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import Select from 'react-select'
import {useLocalMediaProfileSelectRegistry} from "../../types/local_media_profile";
import {SelectRegistry} from "../../utils/selectRegistry";
import {buildShowSelectRegistry} from "../../types/show";
import {useQueryClient} from "@tanstack/react-query";
import { SegmentedOptions } from '../../components/SegmentedOptions'
import {getZodDefaults} from "../../utils/defaultZod";

type AnyOut = PodcastDownloadProfileCreateOut | SeriesDownloadProfileCreateOut
type AnyForm = UseFormReturn<PodcastDownloadProfileCreateIn> | UseFormReturn<SeriesDownloadProfileCreateIn>

export default function AddDownloadProfilePage() {
    const navigate = useNavigate()

    const [mode, setMode] = useState<DownloadProfileMode>('podcast')

    const {data: shows} = useShows()
    const {data: mediaProfiles} = useLocalMediaProfiles()

    const qc = useQueryClient()

    // Filter shows by selected mode (podcast/series); if neither, show none
    const filteredShows = useMemo(() => {
        if (!Array.isArray(shows)) return []
        if (mode === 'podcast') return shows.filter(s => s.type === 'podcast')
        if (mode === 'series') return shows.filter(s => s.type === 'series')
        return []
    }, [shows, mode])

    const showReg: SelectRegistry = useMemo(() => buildShowSelectRegistry(filteredShows), [filteredShows])
    const mediaProfileReg: SelectRegistry = useLocalMediaProfileSelectRegistry(mediaProfiles)

    const formPodcast = useForm<PodcastDownloadProfileCreateIn>({
        resolver: zodResolver(PodcastDownloadProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: getZodDefaults(PodcastDownloadProfileCreateSchema)
    })

    const formSeries = useForm<SeriesDownloadProfileCreateIn>({
        resolver: zodResolver(SeriesDownloadProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: getZodDefaults(SeriesDownloadProfileCreateSchema),
    })
    const form: AnyForm = mode === 'podcast' ? formPodcast : formSeries

    const onCancel = useCallback(() => navigate('/download-profiles'), [navigate])

    const submitFn = async (data: AnyOut) => {
        const endpoint = mode === 'podcast' ? 'podcast-download-profiles' : 'series-download-profiles'
        return fetch(`${(window as any).appConfig.API_URL}/${endpoint}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        })
    }

    const onSuccess = async () => {
        await qc.invalidateQueries({queryKey: ['podcastDownloadProfiles']})
        await qc.invalidateQueries({queryKey: ['seriesDownloadProfiles']})

        navigate('/download-profiles')
    }

    const onSubmit = buildServerAwareSubmit(form, submitFn, {
        onSuccess: onSuccess,
        successStatuses: [201],
    })
    const {formState: {isSubmitting}} = form

    return (
        <section className="view" aria-labelledby="add-download-profile-title">
            <div className="view-header">
                <h1 id="add-download-profile-title">Add download profile</h1>
            </div>

            <form className="form" onSubmit={onSubmit} noValidate>
                <div className="form-row">
                    <SegmentedOptions
                        name="dp-type"
                        value={mode}
                        onChange={(v: DownloadProfileMode) => setMode(v)}
                        options={[
                            {
                                value: 'podcast',
                                label: 'Podcast',
                            },
                            {
                                value: 'series',
                                label: 'Series',
                            },
                        ]}
                    />
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
