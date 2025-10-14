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
}

export default function StreamProfileForm({form, mode, showRoot}: Props) {
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
                    <ReadMore summary={<span>Whether to allow streaming for this show</span>}>
                        If you disable the stream profile, the show will still be indexed and playable for downloaded media when available.
                    </ReadMore>
                </div>
            </div>

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
                                <ReadMore summary={<span>Stream downloaded media when available</span>}>
                                    When enabled, downloaded media within WireLoft will be used when streaming.

                                </ReadMore>
                            ),
                        },
                        {
                            value: 'dw',
                            label: 'Use DailyWire stream',
                            description: (
                                <ReadMore summary={<span>Stream directly from The Daily Wire</span>}>
                                    If enabled, streamed media will come directly from The Daily Wire's own servers.<br/><br/>
                                    If Use Downloads is enabled too, WireLoft will always prefer downloaded media,
                                    but stream directly when no downloaded media exists.
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
                                aria-describedby={errors.preferredFormat ? 'sp-pref-format-error' : undefined}
                                isClearable
                            />
                        )}
                    />
                    {errors.preferredFormat && (
                        <div id="sp-pref-format-error" className="error" role="alert" aria-live="polite">
                            {String(errors.preferredFormat.message)}
                        </div>
                    )}
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
                                aria-describedby={errors.preferredFormat ? 'sp-pref-format-error' : undefined}
                                isClearable
                            />
                        )}
                    />
                    {errors.preferredFormat && (
                        <div id="sp-pref-format-error" className="error" role="alert" aria-live="polite">
                            {String(errors.preferredFormat.message)}
                        </div>
                    )}
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
                        <ReadMore summary={<span>Match episodes using strict rules</span>}>
                            If this setting is enabled, if say, you have a 720p version downloaded but your preferred format is 1080p, it tries to
                            instead stream from DW directly (in whatever format it happens to provide). If the setting is disabled, it tries to match
                            your preferred format but will stream other video formats from your downloaded files
                            if they are the only ones available.<br/><br/>

                            No matter what this setting is set to, as long as your Preferred Format is any video type WireLoft will always ignore
                            audio downloads.
                        </ReadMore>
                    </div>
                </div>
            )}

            {/* Variant-specific fields */}
            {mode === 'rss' ? (
                <RssStreamProfileForm form={form}/>
            ) : undefined}
        </>
    )
}
