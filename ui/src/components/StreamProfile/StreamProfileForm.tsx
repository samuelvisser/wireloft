import {Controller, UseFormReturn} from 'react-hook-form'
import Switch from 'react-switch'
import Select from 'react-select'
import ReadMore from '../../utils/ReadMore'
import {PreferredFormatReg} from '../../types/local_media_profile'
import RssStreamProfileForm from './RssStreamProfileForm'
import SegmentedOptions from '../SegmentedOptions/SegmentedOptions'
import {MediaTypeReg} from "../../types/stream_profile";

export type StreamProfileMode = 'rss' | 'base'

type Props = {
    form: UseFormReturn<any>
    mode: StreamProfileMode
    showRoot?: boolean
    // Passed through to RssStreamProfileForm; see its own props for details.
    isCreating?: boolean
    onRegenerateToken?: () => void | Promise<void>
    regeneratingToken?: boolean
}

export default function StreamProfileForm({form, mode, showRoot, isCreating, onRegenerateToken, regeneratingToken}: Props) {
    const {control, formState: {errors}, setValue, watch} = form
    showRoot ??= true

    // Map booleans to/from segmented multi-select
    const useDownloads = watch('useDownloads')
    const useDwStream = watch('useDwStream')
    const selectedSources = [
        ...(useDownloads ? ['downloads'] as const : []),
        ...(useDwStream ? ['dw'] as const : []),
    ]

    return (
        <>
            {showRoot && errors.root && (
                <div className="form-error-card" role="alert" aria-live="polite">
                    {String(errors.root.message)}
                </div>
            )}

            {/* Streaming sources */}
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
                                    <p>When enabled, downloaded media within WireLoft will be used when streaming.</p>
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
                                    <p>If enabled, streamed media will come directly from The Daily Wire's own servers.</p>
                                    <p>If Use Downloads is enabled too, WireLoft will prefer downloaded media,
                                        but stream directly when no downloaded media exists.</p>
                                </ReadMore>
                            ),
                        },
                    ]}
                    value={selectedSources}
                    onChange={(vals) => {
                        const arr = Array.isArray(vals) ? vals : [vals]
                        const nextUseDownloads = arr.includes('downloads')
                        const nextUseDwStream = arr.includes('dw')
                        // Update both booleans; enforce at least one remains selected already handled by component
                        setValue('useDownloads', nextUseDownloads, {shouldDirty: true, shouldValidate: true})
                        setValue('useDwStream', nextUseDwStream, {shouldDirty: true, shouldValidate: true})
                    }}
                />
            </div>

            {/* Enable streaming */}
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

            {/* Preferred format */}
            {watch("useDownloads") && (
                <div className="form-row">
                    <label htmlFor="sp-preferred-format">Preferred format</label>
                    <Controller
                        control={control}
                        name="preferredFormat"
                        render={({field}) => (
                            <Select
                                inputId="sp-preferred-format"
                                classNamePrefix="select"
                                options={PreferredFormatReg.options}
                                value={PreferredFormatReg.options.find(o => o.value === field.value) ?? null}
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
            ) || (
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

            {/* Require exact match */}
            {watch("useDownloads") && watch("useDwStream") && watch("preferredFormat") !== 'format_audio_only' && (
                <div className="form-row">
                    <label htmlFor="require-exact-match">Require Exact Match for Video Downloads</label>
                    <Controller
                        control={control}
                        name="requireExactMatch"
                        render={({field}) => (
                            <Switch
                                id="require-exact-match"
                                checked={!!field.value}
                                onChange={(checked) => field.onChange(checked)}
                                onColor="#0ea5e9"
                                offColor="#d1d5db"
                                uncheckedIcon={false}
                                checkedIcon={false}
                                aria-invalid={!!errors.requireExactMatch}
                            />
                        )}
                    />
                    <div className="help">
                        <ReadMore summary={<span>Match downloaded episodes using strict rules.</span>}>
                            <p>
                                When this setting is <strong>enabled</strong>, if say, you have a 720p version downloaded but your preferred format is
                                1080p, instead of
                                using the 720p version, WireLoft will stream from DW directly (in whatever format it happens to provide).<br/>
                                When the setting is <strong>disabled</strong>, it tries to match your preferred format but will stream other video
                                formats from your
                                downloaded files if they are the only ones available locally.
                            </p>
                            <p>
                                No matter what this setting is set to, as long as your Preferred Format is any video type WireLoft will always ignore
                                audio downloads for the stream.
                            </p>
                            <p>
                                <strong>Note:</strong> WireLoft cannot control what DW provides. Enabling this setting therefore in no way guarantees
                                the stream will be in the exact format you want. This setting is meant more for cases where you downloaded a lower
                                quality version of the show but want to stream the higher quality version that DW provides.
                            </p>
                        </ReadMore>
                    </div>
                </div>
            )}

            {/* Variant-specific fields */}
            {mode === 'rss' ? (
                <RssStreamProfileForm
                    form={form}
                    isCreating={isCreating}
                    onRegenerateToken={onRegenerateToken}
                    regeneratingToken={regeneratingToken}
                />
            ) : undefined}
        </>
    )
}
