import {Controller, UseFormReturn} from 'react-hook-form'
import Switch from 'react-switch'
import Select from 'react-select'
import ReadMore from '../../utils/ReadMore'
import {PreferredFormatReg} from '../../types/local_media_profile'
import RssStreamProfileForm from './RssStreamProfileForm'

export type StreamProfileMode = 'rss' | 'base'

type Props = {
    form: UseFormReturn<any>
    mode: StreamProfileMode
    showRoot?: boolean
}

export default function StreamProfileForm({form, mode, showRoot}: Props) {
    const {control, formState: {errors}} = form
    showRoot ??= true

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

            {/* Use Downloads */}
            <div className="form-row">
                <label htmlFor="use-downloads">Use Downloads</label>
                <Controller
                    control={control}
                    name="useDownloads"
                    render={({field}) => (
                        <Switch
                            id="use-downloads"
                            checked={!!field.value}
                            onChange={(checked) => field.onChange(checked)}
                            onColor="#0ea5e9"
                            offColor="#d1d5db"
                            uncheckedIcon={false}
                            checkedIcon={false}
                            aria-invalid={!!errors.useDownloads}
                        />
                    )}
                />
                <div className="help">
                    <ReadMore summary={<span>Prefer downloaded media when available</span>}>
                        When enabled, the player will use locally downloaded media if present.
                    </ReadMore>
                </div>
            </div>

            {/* Use DW Stream */}
            <div className="form-row">
                <label htmlFor="use-dw-stream">Use DailyWire stream</label>
                <Controller
                    control={control}
                    name="useDwStream"
                    render={({field}) => (
                        <Switch
                            id="use-dw-stream"
                            checked={!!field.value}
                            onChange={(checked) => field.onChange(checked)}
                            onColor="#0ea5e9"
                            offColor="#d1d5db"
                            uncheckedIcon={false}
                            checkedIcon={false}
                            aria-invalid={!!errors.useDwStream}
                        />
                    )}
                />
                <div className="help">
                    <ReadMore summary={<span>Fallback to DailyWire streaming</span>}>
                        If enabled, the player can stream directly from DailyWire when downloads are unavailable.
                    </ReadMore>
                </div>
            </div>

            {/* Preferred format */}
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
                            isClearable={false}
                        />
                    )}
                />
                {errors.preferredFormat && (
                    <div id="sp-pref-format-error" className="error" role="alert" aria-live="polite">
                        {String(errors.preferredFormat.message)}
                    </div>
                )}
            </div>

            {/* Require exact match */}
            <div className="form-row">
                <label htmlFor="require-exact-match">Require exact match</label>
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
                        If this setting is enabled, if say, you have a 720p version downloaded but your preferred format is 1080p, it tries to instead
                        stream from DW directly (in whatever format it happens to provide). If the setting is disabled, it tries to match your
                        preferred format but will stream other video formats if they are the only ones available.<br/><br/>

                        No matter what this setting is set to, as long as your Preferred Format is any video type WireLoft will always ignore audio
                        downloads.
                    </ReadMore>
                </div>
            </div>

            {/* Variant-specific fields */}
            {mode === 'rss' ? (
                <RssStreamProfileForm form={form}/>
            ) : undefined}
        </>
    )
}
