import {Controller, UseFormReturn} from 'react-hook-form'
import Switch from 'react-switch'
import Select from 'react-select'
import {PreferredFormatReg} from "../../types/local_media_profile";
import ReadMore from "../../utils/ReadMore";

export type StreamProfileMode = 'rss' | 'base'

type Props = {
    form: UseFormReturn<any>
}

export default function RssStreamProfileForm({form}: Props) {
    const {control, formState: {errors}, register} = form

    return (
        <>
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
                        If enabled, requires an exact match when resolving episodes to stream.
                    </ReadMore>
                </div>
            </div>

            {/* Feed URL */}
            <div className="form-row">
                <label htmlFor="feed-url">RSS feed URL</label>
                <input
                    id="feed-url"
                    className="input"
                    type="text"
                    placeholder="https://example.com/feed.xml"
                    {...register('feedUrl')}
                    aria-invalid={!!errors.feedUrl}
                    aria-describedby={errors.feedUrl ? 'feed-url-error' : undefined}
                />
                {errors.feedUrl && (
                    <div id="feed-url-error" className="error" role="alert" aria-live="polite">
                        {String(errors.feedUrl.message)}
                    </div>
                )}
            </div>
        </>
    )
}
