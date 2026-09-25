import {useEffect, useMemo, useRef} from 'react'
import {Controller, UseFormReturn} from 'react-hook-form'
import Switch from 'react-switch'
import Select from 'react-select'
import ReadMore from '../../utils/ReadMore'
import {EpisodeTypeReg} from '../../types/episode'
import {PreferredFormatReg} from '../../types/local_media_profile'
import RssStreamProfileForm from './RssStreamProfileForm'
import StreamProfileAdvisory, {type StreamDownloadProfileDefault} from './StreamProfileAdvisory'
import SegmentedOptions from '../SegmentedOptions/SegmentedOptions'
import {MediaTypeReg} from "../../types/stream_profile";

export type StreamProfileMode = 'rss' | 'base'

export type {StreamDownloadProfileDefault} from './StreamProfileAdvisory'

type UIOption = { value: string; label: string }

const DEFAULT_STREAM_EPISODE_TYPES = ['ep', 'aux']
const STANDARD_VIDEO_FORMATS = new Set(['format_4k', 'format_1080p', 'format_720p'])
const STREAM_PREFERRED_FORMAT_OPTIONS = PreferredFormatReg.options.filter(
    (option) => option.value !== 'format_hls'
)

function sameEpisodeTypes(a: readonly string[], b: readonly string[]) {
    return a.length === b.length && a.every((value) => b.includes(value))
}

type Props = {
    form: UseFormReturn<any>
    mode: StreamProfileMode
    showRoot?: boolean
    isCreating?: boolean
    onRegenerateToken?: () => void | Promise<void>
    regeneratingToken?: boolean
    downloadProfileDefaults?: StreamDownloadProfileDefault[]
    episodeTypesManuallyChanged?: boolean
    onEpisodeTypesManuallyChanged?: () => void
    showSlug?: string
    showTitle?: string
    canOpenDownloadProfiles?: boolean
}

export default function StreamProfileForm({
    form,
    mode,
    showRoot,
    isCreating,
    onRegenerateToken,
    regeneratingToken,
    downloadProfileDefaults,
    episodeTypesManuallyChanged,
    onEpisodeTypesManuallyChanged,
    showSlug,
    showTitle,
    canOpenDownloadProfiles = true,
}: Props) {
    const {control, formState: {errors}, getValues, register, setValue, watch} = form
    showRoot ??= true

    const useDownloads = watch('useDownloads')
    const useDwStream = watch('useDwStream')
    const preferredFormat = watch('preferredFormat')
    const videoOutputMode = watch('videoOutputMode')
    const selectedEpisodeTypes: string[] = watch('epIdTypeList') || []
    const internalEpisodeTypesManuallyChanged = useRef(false)
    const episodeTypeDefaultsInitialized = useRef(false)
    const lastSuggestedTitle = useRef<string | undefined>(undefined)

    useEffect(() => {
        if (!showTitle) return

        const currentTitle = (getValues('title') || '') as string
        const previousSuggestedTitle = lastSuggestedTitle.current
        if (!currentTitle || currentTitle === previousSuggestedTitle) {
            setValue('title', showTitle, {
                shouldDirty: false,
                shouldValidate: true,
            })
        }
        lastSuggestedTitle.current = showTitle
    }, [getValues, setValue, showTitle])

    const selectedSources = [
        ...(useDownloads ? ['downloads'] as const : []),
        ...(useDwStream ? ['dw'] as const : []),
    ]

    const episodeTypeSelectValue: UIOption[] = useMemo(() => (
        selectedEpisodeTypes.map((value) => ({
            value,
            label: EpisodeTypeReg.getLabelLoose(value),
        }))
    ), [selectedEpisodeTypes])

    const automaticEpisodeTypes = useMemo(() => {
        if (useDownloads && downloadProfileDefaults) {
            const candidates = [...downloadProfileDefaults]
                .filter((profile) => profile.enabled !== false)
                .sort((a, b) => Number(Boolean(b.enabled)) - Number(Boolean(a.enabled)))

            const matchingProfile = videoOutputMode === 'audio_hls'
                ? candidates.find((profile) => profile.preferredFormat === 'format_hls')
                : videoOutputMode === 'audio_mp4'
                    ? candidates.find((profile) => STANDARD_VIDEO_FORMATS.has(profile.preferredFormat))
                    : candidates.find((profile) => profile.preferredFormat === preferredFormat)

            if (matchingProfile) return [...matchingProfile.episodeTypes]
        }
        return [...DEFAULT_STREAM_EPISODE_TYPES]
    }, [downloadProfileDefaults, preferredFormat, useDownloads, videoOutputMode])

    const episodeTypeDefaultsReady = !useDownloads || downloadProfileDefaults !== undefined

    useEffect(() => {
        if (!episodeTypeDefaultsReady || !preferredFormat) return

        const current = (getValues('epIdTypeList') || []) as string[]
        const manuallyChanged = episodeTypesManuallyChanged === true
            || internalEpisodeTypesManuallyChanged.current

        if (!episodeTypeDefaultsInitialized.current) {
            episodeTypeDefaultsInitialized.current = true
            if (!isCreating && !manuallyChanged && !sameEpisodeTypes(current, automaticEpisodeTypes)) {
                internalEpisodeTypesManuallyChanged.current = true
                return
            }
        }

        if (
            episodeTypesManuallyChanged !== true
            && !internalEpisodeTypesManuallyChanged.current
            && !sameEpisodeTypes(current, automaticEpisodeTypes)
        ) {
            setValue('epIdTypeList', automaticEpisodeTypes, {
                shouldDirty: false,
                shouldValidate: true,
            })
        }
    }, [
        automaticEpisodeTypes,
        episodeTypeDefaultsReady,
        episodeTypesManuallyChanged,
        getValues,
        isCreating,
        preferredFormat,
        setValue,
    ])

    const markEpisodeTypesManuallyChanged = () => {
        internalEpisodeTypesManuallyChanged.current = true
        if (episodeTypesManuallyChanged !== true) {
            onEpisodeTypesManuallyChanged?.()
        }
    }

    const handleEpisodeTypeChange = (options: readonly UIOption[] | null) => {
        const values = (Array.isArray(options) ? options : []).map((option) => option.value)
        if (!sameEpisodeTypes(values, selectedEpisodeTypes)) {
            markEpisodeTypesManuallyChanged()
        }
        setValue('epIdTypeList', values, {shouldDirty: true, shouldValidate: true})
    }

    const handleSelectAllEpisodeTypes = () => {
        const values = [...EpisodeTypeReg.values]
        if (!sameEpisodeTypes(values, selectedEpisodeTypes)) {
            markEpisodeTypesManuallyChanged()
        }
        setValue('epIdTypeList', values, {shouldDirty: true, shouldValidate: true})
    }

    const streamProfileAdvisory = mode === 'rss' ? (
        <StreamProfileAdvisory
            mode={mode}
            preferredFormat={preferredFormat}
            videoOutputMode={videoOutputMode}
            useDownloads={!!useDownloads}
            useDwStream={!!useDwStream}
            selectedEpisodeTypes={selectedEpisodeTypes}
            downloadProfileDefaults={downloadProfileDefaults}
            showSlug={showSlug}
            canOpenDownloadProfiles={canOpenDownloadProfiles}
            onEnableDownloads={() => setValue('useDownloads', true, {
                shouldDirty: true,
                shouldValidate: true,
            })}
            onDisableDwStream={() => setValue('useDwStream', false, {
                shouldDirty: true,
                shouldValidate: true,
            })}
        />
    ) : null

    return (
        <>
            {showRoot && errors.root && (
                <div className="form-error-card" role="alert" aria-live="polite">
                    {String(errors.root.message)}
                </div>
            )}

            <div className="form-row">
                <label htmlFor="stream-profile-title">Title</label>
                <input
                    id="stream-profile-title"
                    className="input"
                    type="text"
                    {...register('title')}
                    aria-invalid={!!errors.title}
                    aria-describedby={errors.title ? 'stream-profile-title-error' : undefined}
                />
                {errors.title && (
                    <div id="stream-profile-title-error" className="error" role="alert" aria-live="polite">
                        {String(errors.title.message)}
                    </div>
                )}
            </div>

            <div className="form-row">
                <label id="stream-sources-label">Streaming sources</label>
                <SegmentedOptions
                    name="stream-sources"
                    multiple
                    ariaLabelledBy="stream-sources-label"
                    options={[
                        {
                            value: 'downloads',
                            label: 'Use Downloads',
                            description: (
                                <ReadMore summary={<span>Stream downloaded media when available.</span>}>
                                    <p>If enabled, downloaded media within WireLoft can be used when streaming.</p>
                                    <p>Streaming downloaded media usually improves the stability of the stream
                                        and ensures a consistent experience.</p>
                                </ReadMore>
                            ),
                        },
                        {
                            value: 'dw',
                            label: 'Use DailyWire stream',
                            description: (
                                <ReadMore summary={<span>Stream directly from The Daily Wire.</span>}>
                                    <p>If enabled, streamed media can come directly from The Daily Wire's own servers.</p>
                                    <p>If Use Downloads is enabled too, WireLoft will prefer downloaded media,
                                        but stream directly when no downloaded media exists.
                                    </p>
                                    <p>This could come in handy if you only intend to download a few of the latest episodes,
                                    but still want to retain the ability to stream many more.</p>
                                </ReadMore>
                            ),
                        },
                    ]}
                    value={selectedSources}
                    onChange={(vals) => {
                        const arr = Array.isArray(vals) ? vals : [vals]
                        const nextUseDownloads = arr.includes('downloads')
                        const nextUseDwStream = arr.includes('dw')
                        setValue('useDownloads', nextUseDownloads, {shouldDirty: true, shouldValidate: true})
                        setValue('useDwStream', nextUseDwStream, {shouldDirty: true, shouldValidate: true})
                    }}
                />
            </div>

            <div className="form-row">
                <label htmlFor="enable-profile">Enable streaming</label>
                <Controller
                    control={control}
                    name="enableProfile"
                    render={({field}) => (
                        <Switch
                            id="enable-profile"
                            checked={!!field.value}
                            onChange={(checked) => field.onChange(checked)}
                            onColor="#0ea5e9"
                            offColor="#d1d5db"
                            uncheckedIcon={false}
                            checkedIcon={false}
                            aria-invalid={!!errors.enableProfile}
                            aria-describedby={errors.enableProfile ? 'enable-profile-errors' : 'enable-profile-help'}
                        />
                    )}
                />
                {errors.enableProfile && (
                    <div id="enable-profile-errors" className="error" role="alert" aria-live="polite">
                        {String(errors.enableProfile.message)}
                    </div>
                )}
                <div className="help" id="enable-profile-help">
                    <ReadMore summary={<span>Enable streaming the content from WireLoft.</span>}>
                        <p>When enabled, this stream profile will do its job and open your chosen stream (for now, RSS).</p>
                        <p>You can disable it if you want to retain all the stream profile settings but for whatever reason do not want
                            the streaming enabled.</p>
                    </ReadMore>
                </div>
            </div>

            {useDownloads ? (
                <div className="form-row">
                    <label htmlFor="sp-preferred-format">Preferred format</label>
                    <Controller
                        control={control}
                        name="preferredFormat"
                        render={({field}) => (
                            <Select
                                inputId="sp-preferred-format"
                                classNamePrefix="select"
                                options={STREAM_PREFERRED_FORMAT_OPTIONS}
                                value={STREAM_PREFERRED_FORMAT_OPTIONS.find(o => o.value === field.value) ?? null}
                                onChange={(opt) => field.onChange((opt as any)?.value ?? null)}
                                onBlur={field.onBlur}
                                aria-invalid={!!errors.preferredFormat}
                                aria-describedby={errors.preferredFormat ? 'sp-pref-format-error' : 'sp-pref-format-help'}
                                isClearable
                            />
                        )}
                    />
                    {errors.preferredFormat && (
                        <div id="sp-pref-format-error" className="error" role="alert" aria-live="polite">
                            {String(errors.preferredFormat.message)}
                        </div>
                    )}
                    <div className="help" id="sp-pref-format-help">
                        <ReadMore summary={<span>Content type to prefer while streaming.</span>}>
                            <p>Serves the specified content type if available. If not, it will try to serve the next best option by default.</p>
                            <p>If you need audio-only content, you can set this to 'Audio Only' to stream audio only.</p>
                        </ReadMore>
                    </div>
                </div>
            ) : (
                <div className="form-row">
                    <label htmlFor="sp-preferred-format">Media Type</label>
                    <Controller
                        control={control}
                        name="preferredFormat"
                        render={({field}) => (
                            <Select
                                inputId="sp-preferred-format"
                                classNamePrefix="select"
                                options={MediaTypeReg.options}
                                value={MediaTypeReg.options.find(o => o.value === field.value) ?? null}
                                onChange={(opt) => field.onChange((opt as any)?.value ?? null)}
                                onBlur={field.onBlur}
                                aria-invalid={!!errors.preferredFormat}
                                aria-describedby={errors.preferredFormat ? 'sp-pref-format-error' : 'sp-pref-format-help'}
                                isClearable
                            />
                        )}
                    />
                    {errors.preferredFormat && (
                        <div id="sp-pref-format-error" className="error" role="alert" aria-live="polite">
                            {String(errors.preferredFormat.message)}
                        </div>
                    )}
                    <div className="help" id="sp-pref-format-help">
                        <ReadMore summary={<span>Whether to stream video or audio from DW.</span>}>
                            <p>WireLoft cannot control what format the video or audio that DW provides will be in. Therefore, when Use Downloads
                            is disabled in streaming sources, you cannot select the exact video format you prefer.</p>
                            <p>Setting this to video will set the resolution to 1080p in the background. That wont matter much as again, WireLoft
                                will just stream whatever video DW gives it.</p>
                        </ReadMore>
                    </div>
                </div>
            )}

            <div className="form-row">
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                    <label htmlFor="sp-episode-types">Episode types</label>
                    <button type="button" className="btn btn-link" onClick={handleSelectAllEpisodeTypes}>
                        Select all
                    </button>
                </div>
                <Controller
                    control={control}
                    name="epIdTypeList"
                    render={() => (
                        <Select
                            inputId="sp-episode-types"
                            isMulti
                            options={EpisodeTypeReg.options}
                            value={episodeTypeSelectValue}
                            onChange={handleEpisodeTypeChange as any}
                            closeMenuOnSelect={false}
                            getOptionValue={(option: UIOption) => option.value}
                            getOptionLabel={(option: UIOption) => option.label}
                            aria-invalid={!!errors.epIdTypeList}
                            aria-describedby={errors.epIdTypeList ? 'sp-episode-types-error' : 'sp-episode-types-help'}
                        />
                    )}
                />
                {errors.epIdTypeList && (
                    <div id="sp-episode-types-error" className="error" role="alert" aria-live="polite">
                        {String(errors.epIdTypeList.message)}
                    </div>
                )}
                <div className="help" id="sp-episode-types-help">
                    <ReadMore summary={<span>What episode types to stream</span>}>
                        <p>Select all episode types you want this profile to stream.</p>
                        <p><b>Episode</b> is a normal episode in the show.</p>
                        <p><b>Ep. Extra</b> is auxiliary content for a specific episode.</p>
                        <p><b>Trailer</b> is a trailer for the show or auxiliary content.</p>
                        <p><b>Auxiliary</b> is auxiliary content for the show.</p>
                        <p>Until you change this selection manually, WireLoft uses Episode and Auxiliary by default. When Use Downloads is enabled and a Download Profile for the same show has the selected Preferred format, its episode types are used as the default instead.</p>
                    </ReadMore>
                </div>
            </div>

            {useDownloads && useDwStream && STANDARD_VIDEO_FORMATS.has(preferredFormat) && (
                <div className="form-row">
                    <label htmlFor="prefer-exact-match">Prefer Exact Match for Video Downloads</label>
                    <Controller
                        control={control}
                        name="preferExactMatch"
                        render={({field}) => (
                            <Switch
                                id="prefer-exact-match"
                                checked={!!field.value}
                                onChange={(checked) => field.onChange(checked)}
                                onColor="#0ea5e9"
                                offColor="#d1d5db"
                                uncheckedIcon={false}
                                checkedIcon={false}
                                aria-invalid={!!errors.preferExactMatch}
                            />
                        )}
                    />
                    <div className="help">
                        <ReadMore summary={<span>Match downloaded episodes using strict rules.</span>}>
                            <p>
                                When this setting is <strong>enabled</strong>, if say, you have a 720p version downloaded but your preferred format is
                                1080p, instead of using the 720p version, WireLoft will stream from DW directly (in whatever format it happens to provide).<br/>
                                When the setting is <strong>disabled</strong>, it tries to match your preferred format but will stream other video
                                formats from your downloaded files if they are the only ones available locally.
                            </p>
                            <p>
                                Obviously, no matter what this setting is set to, WireLoft will only consider video downloads when trying to match local
                                files to your video streaming request. Audio will never be send in the place of video merely because you had it downloaded.
                            </p>
                            <p>
                                <strong>Note:</strong> WireLoft cannot control what DW provides. This preference only controls whether WireLoft accepts
                                a non-exact local video format before falling back to DW. It does not guarantee that the stream DW provides will be
                                in the exact format you prefer.
                            </p>
                        </ReadMore>
                    </div>
                </div>
            )}

            {mode === 'rss' ? (
                <RssStreamProfileForm
                    form={form}
                    isCreating={isCreating}
                    onRegenerateToken={onRegenerateToken}
                    regeneratingToken={regeneratingToken}
                    advisory={streamProfileAdvisory}
                />
            ) : undefined}
        </>
    )
}
