import {ReactNode, useState} from 'react'
import {Controller, UseFormReturn} from 'react-hook-form'
import Select from 'react-select'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import ReadMore from '../../utils/ReadMore'
import {RssDwVideoMethodReg} from '../../types/stream_profile'


const VIDEO_FORMATS = new Set(['format_4k', 'format_1080p', 'format_720p'])

type Props = {
    form: UseFormReturn<any>
    isCreating?: boolean
    onRegenerateToken?: () => void | Promise<void>
    regeneratingToken?: boolean
    videoMethodAdvisory?: ReactNode
}

export default function RssStreamProfileForm({form, isCreating, onRegenerateToken, regeneratingToken, videoMethodAdvisory}: Props) {
    const {control, formState: {errors}, register, watch} = form
    const [copied, setCopied] = useState(false)

    const feedUrl: string | undefined = watch('feedUrl')
    const useDwStream: boolean = watch('useDwStream')
    const preferredFormat: string | undefined = watch('preferredFormat')
    const usesDwVideo = useDwStream && VIDEO_FORMATS.has(preferredFormat ?? '')

    const onCopy = async () => {
        if (!feedUrl) return
        try {
            await navigator.clipboard.writeText(feedUrl)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        } catch {
            // The field remains selectable when clipboard access is unavailable.
        }
    }

    return (
        <>
            <div className="form-row">
                <label htmlFor="rss-max-items">Maximum episodes in RSS feed</label>
                <input
                    id="rss-max-items"
                    className="input"
                    type="number"
                    inputMode="numeric"
                    min={0}
                    step={1}
                    {...register('maxItems', {valueAsNumber: true})}
                    aria-invalid={!!errors.maxItems}
                    aria-describedby={errors.maxItems ? 'rss-max-items-error' : 'rss-max-items-help'}
                />
                {errors.maxItems && (
                    <div id="rss-max-items-error" className="error" role="alert" aria-live="polite">
                        {String(errors.maxItems.message)}
                    </div>
                )}
                <div className="help" id="rss-max-items-help">
                    Only the newest episodes are included. Set to 0 to expose the complete episode history.
                </div>
            </div>

            {usesDwVideo && (
                <div className="form-row">
                    <label htmlFor="rss-dw-video-method">Stream DW video method</label>
                    <Controller
                        control={control}
                        name="dwVideoMethod"
                        render={({field}) => (
                            <Select
                                inputId="rss-dw-video-method"
                                classNamePrefix="select"
                                options={RssDwVideoMethodReg.options}
                                value={RssDwVideoMethodReg.options.find(option => option.value === field.value) ?? null}
                                onChange={(option) => field.onChange((option as any)?.value)}
                                onBlur={field.onBlur}
                                isClearable={false}
                                aria-invalid={!!errors.dwVideoMethod}
                                aria-describedby={errors.dwVideoMethod ? 'rss-dw-video-method-error' : 'rss-dw-video-method-help'}
                            />
                        )}
                    />
                    {errors.dwVideoMethod && (
                        <div id="rss-dw-video-method-error" className="error" role="alert" aria-live="polite">
                            {String(errors.dwVideoMethod.message)}
                        </div>
                    )}
                    <div className="help" id="rss-dw-video-method-help">
                        <ReadMore summary={<span>Choose how Daily Wire video is exposed to podcast apps.</span>}>
                            <p>
                                The <strong>Control</strong> methods preserve the behavior already tested with Pocket Casts. Embedded HLS is known to stream video, but it writes short-lived Daily Wire URLs into the RSS and therefore has to resolve them while the feed is generated. Prepared MP4 is stable and compatible, but cannot start until the complete file has been prepared.
                            </p>
                            <p>
                                The <strong>Experiment</strong> methods all put a stable WireLoft URL ending in <code>.m3u8</code> into the RSS. Redirect and proxy variants resolve the currently valid Daily Wire HLS URL only when the podcast player requests that episode. The filename, redirect status and MIME variants intentionally isolate the signals Pocket Casts/AVPlayer may use when classifying HLS media.
                            </p>
                            <p>
                                The prepared local HLS experiment creates a conventional VOD HLS package with local MPEG-TS segments. Its first request can be slow because WireLoft has to prepare the whole package. Opening that episode's <code>prepared/video.m3u8</code> once before subscribing pre-warms the test.
                            </p>
                            <p>
                                Experiment methods use method- and feed-specific episode GUIDs so switching methods does not silently reuse Pocket Casts' previous enclosure classification. Downloaded files are always served directly and are not affected by these HLS experiments.
                            </p>
                        </ReadMore>
                    </div>
                </div>
            )}

            {usesDwVideo ? videoMethodAdvisory : null}

            {!isCreating && (
                <div className="form-row">
                    <label htmlFor="feed-url">RSS feed URL</label>
                    <div className={`rss-feed-url-group${errors.feedUrl ? ' rss-feed-url-group-invalid' : ''}`}>
                        <input
                            id="feed-url"
                            className="input rss-feed-url-input"
                            type="text"
                            placeholder="https://example.com/feed.xml"
                            {...register('feedUrl')}
                            aria-invalid={!!errors.feedUrl}
                            aria-describedby={errors.feedUrl ? 'feed-url-error' : 'feed-url-help'}
                        />
                        <div className="rss-feed-url-actions">
                            <button
                                type="button"
                                className="rss-feed-url-action"
                                onClick={onCopy}
                                disabled={!feedUrl}
                                aria-label={copied ? 'RSS feed URL copied' : 'Copy RSS feed URL'}
                                title={copied ? 'Copied!' : 'Copy RSS feed URL'}
                                aria-live="polite"
                            >
                                <FontAwesomeIcon
                                    className="rss-feed-url-action-icon"
                                    icon={['fas', copied ? 'check' : 'copy'] as any}
                                    aria-hidden="true"
                                />
                                <span className="rss-feed-url-action-text">{copied ? 'Copied!' : 'Copy'}</span>
                            </button>
                            {onRegenerateToken && (
                                <button
                                    type="button"
                                    className="rss-feed-url-action rss-feed-url-action-danger"
                                    onClick={onRegenerateToken}
                                    disabled={!!regeneratingToken}
                                    aria-label={regeneratingToken ? 'Regenerating RSS feed URL' : 'Regenerate RSS feed URL'}
                                    title={regeneratingToken ? 'Regenerating…' : 'Regenerate RSS feed URL'}
                                >
                                    <FontAwesomeIcon
                                        className="rss-feed-url-action-icon"
                                        icon={['fas', regeneratingToken ? 'spinner' : 'arrows-rotate'] as any}
                                        spin={!!regeneratingToken}
                                        aria-hidden="true"
                                    />
                                    <span className="rss-feed-url-action-text">
                                        {regeneratingToken ? 'Regenerating…' : 'Regenerate'}
                                    </span>
                                </button>
                            )}
                        </div>
                    </div>
                    {errors.feedUrl && (
                        <div id="feed-url-error" className="error" role="alert" aria-live="polite">
                            {String(errors.feedUrl.message)}
                        </div>
                    )}
                    <div className="help" id="feed-url-help">
                        <ReadMore summary={<span>Paste this URL into your podcast app.</span>}>
                            <p>
                                This feed stays reachable even when local authentication is enabled for the WireLoft UI, so your podcast app never needs to log in. You can freely edit this text, for example to use a different hostname.
                            </p>
                            <p>
                                If this URL ever leaks, use <strong>Regenerate</strong> to mint a new one and immediately invalidate the old one.
                            </p>
                        </ReadMore>
                    </div>
                </div>
            )}
        </>
    )
}
