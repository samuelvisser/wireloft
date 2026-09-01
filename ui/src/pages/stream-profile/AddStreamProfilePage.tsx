import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {Controller, useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {useNavigate, useSearchParams} from 'react-router-dom'
import {useDownloadProfilesView, useShows} from '../../lib/queries'
import {buildShowSelectRegistry} from '../../types/show'
import {SelectRegistry} from '../../utils/selectRegistry'
import Select from 'react-select'
import {getZodDefaults} from '../../utils/defaultZod'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import StreamProfileForm, {StreamProfileMode} from '../../components/StreamProfile/StreamProfileForm'
import SegmentedOptions from '../../components/SegmentedOptions/SegmentedOptions'
import {RssStreamProfileCreateIn, RssStreamProfileCreateOut, RssStreamProfileCreateSchema} from '../../types/schemas/rss_stream_profile'
import {useQueryClient} from '@tanstack/react-query'
import ReadMore from "../../utils/ReadMore";

export default function AddStreamProfilePage() {
    const navigate = useNavigate()
    const [searchParams] = useSearchParams()
    const qc = useQueryClient()

    const [mode, setMode] = useState<StreamProfileMode>('rss')

    const {data: shows} = useShows()
    const {data: downloadProfiles} = useDownloadProfilesView()
    const showReg: SelectRegistry = buildShowSelectRegistry(shows)

    const form = useForm<RssStreamProfileCreateIn>({
        resolver: zodResolver(RssStreamProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: getZodDefaults(RssStreamProfileCreateSchema),
    })
    const {watch, formState: {errors, isSubmitting}} = form
    const prefillApplied = useRef(false)
    const requestedShowSlug = searchParams.get('show')
    const selectedShowId = watch('showId')
    const useDownloads = watch('useDownloads')
    const selectedShow = shows?.find((show) => show.id === selectedShowId)

    const downloadProfileDefaults = useMemo(() => {
        if (!downloadProfiles) return undefined
        if (!selectedShow) return []
        return downloadProfiles
            .filter((profile) => profile.showSlug === selectedShow.slug)
            .map((profile) => ({
                preferredFormat: profile.localMediaProfilePreferredFormat,
                episodeTypes: profile.downloadProfileImpl.epIdTypeList,
                enabled: profile.enableProfile,
            }))
    }, [downloadProfiles, selectedShow?.slug])

    useEffect(() => {
        if (prefillApplied.current || !requestedShowSlug || !Array.isArray(shows)) return
        const requestedShow = shows.find((show) => show.slug === requestedShowSlug)
        if (!requestedShow) return

        form.setValue('showId', requestedShow.id, {shouldDirty: false, shouldValidate: true})
        prefillApplied.current = true
    }, [form, requestedShowSlug, shows])

    const onCancel = useCallback(() => navigate('/stream-profiles'), [navigate])

    const submitFn = async (data: RssStreamProfileCreateOut) => {
        return fetch(`${(window as any).appConfig.API_URL}/rss-stream-profiles`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        })
    }

    const onSuccess = async (result: {id: number}) => {
        await qc.invalidateQueries({queryKey: ['rssStreamProfiles']})
        await qc.invalidateQueries({queryKey: ['streamProfilesView']})
        navigate(`/edit-stream-profile/rss/${result.id}`)
    }

    const onSubmit = buildServerAwareSubmit(form as any, submitFn, {
        onSuccess,
        successStatuses: [201],
    })
    const waitingForDownloadProfileDefaults = !!selectedShowId && useDownloads && downloadProfiles === undefined

    return (
        <section className="view" aria-labelledby="add-stream-profile-title">
            <div className="view-header">
                <h1 id="add-stream-profile-title">Add Stream Profile</h1>
            </div>

            <form className="form" onSubmit={onSubmit} noValidate>
                {errors.root && (
                    <div className="form-error-card" role="alert" aria-live="polite">
                        {String(errors.root.message)}
                    </div>
                )}

                <div className="form-row">
                    <label htmlFor="show-id">Show</label>
                    <Controller
                        control={form.control}
                        name={"showId"}
                        render={({field}) => (
                            <Select
                                inputId="show-id"
                                classNamePrefix="select"
                                options={showReg.options}
                                value={showReg.options.find(o => Number(o.value) === field.value) ?? null}
                                onChange={(opt) => field.onChange((opt as any) ? Number((opt as any).value) : undefined)}
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
                            {String(errors.showId.message)}
                        </div>
                    )}
                </div>

                <div className="form-row">
                    <label>Profile type</label>
                    <SegmentedOptions
                        name="stream-profile-mode"
                        value={mode}
                        onChange={(v) => setMode(v as StreamProfileMode)}
                        options={[
                            {
                                value: 'rss',
                                label: 'RSS',
                                description: (
                                    <ReadMore summary={<span>Open RSS feed for the show.</span>}>
                                        <p>RSS is the technology used to distribute podcast feeds.</p>
                                        <p>With an RSS Stream Profile in WireLoft, you can effectively create your very own podcast from
                                        Daily Wire content. This is great when you want to listen to premium versions of Daily Wire shows
                                        using your favorite podcast app.</p>
                                    </ReadMore>
                                ),
                            }
                        ]}
                    />
                </div>

                <StreamProfileForm
                    form={form as any}
                    mode={mode}
                    showRoot={false}
                    isCreating
                    downloadProfileDefaults={downloadProfileDefaults}
                />

                <div className="actions">
                    <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    <input
                        type="submit"
                        className="btn btn-primary"
                        value="Create profile"
                        disabled={isSubmitting || !selectedShowId || waitingForDownloadProfileDefaults}
                    />
                </div>
            </form>
        </section>
    )
}
