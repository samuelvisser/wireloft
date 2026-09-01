import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {Controller, useForm, UseFormReturn} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {useNavigate, useSearchParams} from 'react-router-dom'
import {useDownloadProfilesByShowSlug, useLocalMediaProfiles, useShowSeasons, useShows} from '../../lib/queries'
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
import {getZodDefaults} from "../../utils/defaultZod";
import ReadMore from "../../utils/ReadMore";
import {ShowRead} from "../../types/schemas/show";
import {SeasonItem} from "../../components/DownloadProfile/SeriesDownloadProfileForm";
import {SeasonRead} from "../../types/schemas/season";

type AnyOut = PodcastDownloadProfileCreateOut | SeriesDownloadProfileCreateOut
type AnyForm = UseFormReturn<PodcastDownloadProfileCreateIn> | UseFormReturn<SeriesDownloadProfileCreateIn>

export default function AddDownloadProfilePage() {
    const navigate = useNavigate()
    const [searchParams] = useSearchParams()

    const [mode, setMode] = useState<DownloadProfileMode>('base')

    const {data: shows} = useShows()
    const {data: mediaProfiles} = useLocalMediaProfiles()

    const qc = useQueryClient()

    const showReg: SelectRegistry = useMemo(() => buildShowSelectRegistry(shows), [shows])
    const mediaProfileReg: SelectRegistry = useLocalMediaProfileSelectRegistry(mediaProfiles, 'show')

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
    const form: AnyForm = mode === 'series' ? formSeries : formPodcast
    const {formState: {errors}} = form
    const prefillApplied = useRef(false)
    const limitPrefillApplied = useRef(false)
    const requestedShowSlug = searchParams.get('show')
    const requestedDownloadEpisodeCountRaw = searchParams.get('downloadEpisodeCount')
    const parsedDownloadEpisodeCount = Number(requestedDownloadEpisodeCountRaw)
    const requestedDownloadEpisodeCount = requestedDownloadEpisodeCountRaw !== null
        && Number.isInteger(parsedDownloadEpisodeCount)
        && parsedDownloadEpisodeCount > 0
        ? parsedDownloadEpisodeCount
        : undefined

    useEffect(() => {
        if (prefillApplied.current || !requestedShowSlug || !Array.isArray(shows)) return
        const requestedShow = shows.find((show) => show.slug === requestedShowSlug)
        if (!requestedShow) return

        formPodcast.setValue('showId', requestedShow.id, {shouldDirty: false, shouldValidate: true})
        formSeries.setValue('showId', requestedShow.id, {shouldDirty: false, shouldValidate: true})
        if (requestedShow.type === 'podcast') setMode('podcast')
        else if (requestedShow.type === 'series') setMode('series')
        else setMode('base')
        prefillApplied.current = true
    }, [formPodcast, formSeries, requestedShowSlug, shows])

    useEffect(() => {
        if (limitPrefillApplied.current || requestedDownloadEpisodeCount === undefined) return

        formPodcast.setValue('downloadDaysInPast', 0, {shouldDirty: false, shouldValidate: true})
        formPodcast.setValue('downloadEpisodeCount', requestedDownloadEpisodeCount, {
            shouldDirty: false,
            shouldValidate: true,
        })
        limitPrefillApplied.current = true
    }, [formPodcast, requestedDownloadEpisodeCount])

    const onCancel = useCallback(() => navigate('/download-profiles'), [navigate])

    const submitFn = async (data: AnyOut) => {
        let effectiveMode: DownloadProfileMode = mode
        const endpoint = effectiveMode === 'podcast' ? 'podcast-download-profiles' : 'series-download-profiles'

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

    const {watch, formState: {isSubmitting}} = form
    const showId = watch("showId" as any)
    const localMediaProfileId = watch("localMediaProfileId" as any)

    // Resolve selected show and slug
    const selectedShow = useMemo(() => {
        if (!Array.isArray(shows)) return undefined
        const sid = Number(showId)
        return shows.find(s => s.id === sid)
    }, [shows, showId])
    const selectedShowSlug: string | undefined = selectedShow?.slug

    // Fetch seasons and existing download profiles for the selected show
    const {data: seasonsData} = useShowSeasons(selectedShowSlug)
    const {data: showProfiles} = useDownloadProfilesByShowSlug(selectedShowSlug)

    // Prepare seasons for the SeriesDownloadProfile form (detached: name, dwId, slug)
    const seasonsForForm: SeasonItem[] = useMemo((): SeasonItem[] => (seasonsData ?? []).map((s: SeasonRead): SeasonItem => ({
        name: s.name,
        dwId: s.dwId,
        slug: s.slug,
    })), [seasonsData])

    const disabledEpisodeTypes = useMemo(() => {
        if (typeof localMediaProfileId !== 'number' || !selectedShow) return new Set<string>()
        return new Set<string>(
            (showProfiles ?? [])
                .filter((profile) => (
                    profile.showId === selectedShow.id
                    && profile.localMediaProfileId === localMediaProfileId
                ))
                .flatMap((profile) => profile.epIdTypeList)
        )
    }, [localMediaProfileId, selectedShow?.id, showProfiles])

    return (
        <section className="view" aria-labelledby="add-download-profile-title">
            <div className="view-header">
                <h1 id="add-download-profile-title">Add download profile</h1>
            </div>

            <form className="form" onSubmit={onSubmit} noValidate>

                {errors.root && (
                    <div className="form-error-card" role="alert" aria-live="polite">
                        {String(errors.root.message)}
                    </div>
                )}

                {/* Show */}
                <div className="form-row">
                    <label htmlFor="show-id">Show</label>
                    <Controller
                        control={(form as any).control}
                        name={"showId"}
                        render={({field}) => (
                            <Select
                                inputId="show-id"
                                classNamePrefix="select"
                                options={showReg.options}
                                value={showReg.options.find(o => Number(o.value) === field.value) ?? null}
                                onChange={(opt) => {
                                    const val = (opt as any) ? Number((opt as any).value) : undefined

                                    // keep both forms in sync for showId
                                    if (val) {
                                        formPodcast.setValue('showId', val)
                                        formSeries.setValue('showId', val)
                                    }
                                    field.onChange(val)

                                    if (!val) {
                                        setMode('base')
                                        return
                                    }

                                    const selectedShow: ShowRead | undefined = Array.isArray(shows) ? shows.find(s => s.id === val) : undefined
                                    if (selectedShow?.type === 'podcast') setMode('podcast')
                                    else if (selectedShow?.type === 'series') setMode('series')
                                    else setMode('base')
                                }}
                                onBlur={field.onBlur}
                                isDisabled={showReg.options.length === 0}
                                placeholder={showReg.options.length === 0 ? 'No shows found' : undefined}
                                isClearable
                                aria-invalid={!!errors.showId}
                                aria-describedby={errors.showId ? 'show-errors' : undefined}
                            />
                        )}
                    />
                    {errors.showId && (
                        <div id="show-errors" className="error" role="alert" aria-live="polite">
                            {errors.showId.message as string}
                        </div>
                    )}
                </div>

                {/* Local Media Profile */}
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
                                onChange={(opt) => {
                                    const val = (opt as any) ? Number((opt as any).value) : null
                                        // keep both forms in sync for localMediaProfileId
                                    ;(formPodcast as any).setValue('localMediaProfileId', val)
                                    ;(formSeries as any).setValue('localMediaProfileId', val)
                                    field.onChange(val)
                                }}
                                onBlur={field.onBlur}
                                isDisabled={mediaProfileReg.options.length === 0}
                                placeholder={!mediaProfiles ? 'Loading profiles...' : mediaProfileReg.options.length === 0 ? 'No profiles found' : undefined}
                                isClearable
                                aria-invalid={!!errors.localMediaProfileId}
                                aria-describedby={errors.localMediaProfileId ? 'local-media-profile-errors' : 'local-media-profile-help'}
                            />
                        )}
                    />
                    {errors.localMediaProfileId && (
                        <div id="local-media-profile-errors" className="error" role="alert" aria-live="polite">
                            {errors.localMediaProfileId.message as string}
                        </div>
                    )}
                    <div className="help" id="local-media-profile-help">
                        <ReadMore summary={<span>The Local Media Profile defines the type and output path of downloaded media.</span>}>
                            <p>Add a Local Media Profile to define the type of media to download and where to store it.</p>
                            <p>The same Local Media Profile can be used by multiple Download Profiles for a show, but each episode type can belong to only one of those profiles.</p>
                        </ReadMore>
                    </div>
                </div>

                <DownloadProfileForm
                    form={form as any}
                    mode={mode}
                    seasons={seasonsForForm}
                    showRoot={false}
                    disabledEpisodeTypes={disabledEpisodeTypes}
                />

                <div className="actions">
                    <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    <input type="submit" className="btn btn-primary" value="Create profile" disabled={isSubmitting || !showId}/>
                </div>
            </form>
        </section>
    )
}
