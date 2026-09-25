import {ReactNode, useEffect, useState} from 'react'
import {Controller, UseFormReturn} from 'react-hook-form'
import Select from 'react-select'
import Switch from 'react-switch'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import ReadMore from '../../utils/ReadMore'
import {RssHlsOutputModes, RssVideoOutputModeReg} from '../../types/stream_profile'


const VIDEO_FORMATS = new Set(['format_4k', 'format_1080p', 'format_720p', 'format_hls'])

type Props = {
    form: UseFormReturn<any>
    isCreating?: boolean
    onRegenerateToken?: () => void | Promise<void>
    regeneratingToken?: boolean
    advisory?: ReactNode
}

export default function RssStreamProfileForm({
    form,
    isCreating,
    onRegenerateToken,
    regeneratingToken,
    advisory,
}: Props) {
    const {control, formState: {errors}, register, setValue, watch} = form
    const [copied, setCopied] = useState(false)

    const feedUrl: string | undefined = watch('feedUrl')
    const useDwStream: boolean = watch('useDwStream')
    const preferredFormat: string | undefined = watch('preferredFormat')
    const videoOutputMode: string | null | undefined = watch('videoOutputMode')
    const streamLiveEpisodes: boolean = watch('streamLiveEpisodes')
    const usesVideo = VIDEO_FORMATS.has(preferredFormat ?? '')
    const usesHlsVideo = usesVideo && RssHlsOutputModes.has(videoOutputMode ?? '')

    useEffect(() => {
        if (preferredFormat === 'format_audio_only') {
            if (videoOutputMode !== null) {
                setValue('videoOutputMode', null, {
                    shouldDirty: true,
                    shouldValidate: true,
                })
            }
            return
        }

        if (usesVideo && videoOutputMode == null) {
            setValue('videoOutputMode', 'audio_hls', {
                shouldDirty: true,
                shouldValidate: true,
            })
        }
    }, [preferredFormat, setValue, usesVideo, videoOutputMode])

    useEffect(() => {
        if (!usesHlsVideo && streamLiveEpisodes) {
            setValue('streamLiveEpisodes', false, {
                shouldDirty: true,
                shouldValidate: true,
            })
        }
    }, [setValue, streamLiveEpisodes, usesHlsVideo])

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
                    <ReadMore summary={<span>Include only the newest episodes. Keeping this low speeds up RSS experience.</span>}>
                        <p>
                            Capping the amount of included episodes usually greatly improves the performance of your RSS feed.
                        </p>
                        <p>
                            Set to 0 to remove all limits.
                        </p>
                    </ReadMore>
                </div>
            </div>

            {usesVideo && (
                <div className="form-row">
                    <label htmlFor="rss-video-output-mode">Video podcast output</label>
                    <Controller
                        control={control}
                        name="videoOutputMode"
                        render={({field}) => (
                            <Select
                                inputId="rss-video-output-mode"
                                classNamePrefix="select"
                                options={RssVideoOutputModeReg.options}
                                value={RssVideoOutputModeReg.options.find(option => option.value === field.value) ?? null}
                                onChange={(option) => field.onChange((option as any)?.value)}
                                onBlur={field.onBlur}
                                isClearable={false}
                                aria-invalid={!!errors.videoOutputMode}
                                aria-describedby={errors.videoOutputMode ? 'rss-video-output-mode-error' : 'rss-video-output-mode-help'}
                            />
                        )}
                    />
                    {errors.videoOutputMode && (
                        <div id="rss-video-output-mode-error" className="error" role="alert" aria-live="polite">
                            {String(errors.videoOutputMode.message)}
                        </div>
                    )}
                    <div className="help" id="rss-video-output-mode-help">
                        <ReadMore summary={<span>Choose how to serve video in your RSS feed depending on what your podcast player supports.</span>}>
                            <p>
                                <strong>{RssVideoOutputModeReg.getLabel('audio_hls')}</strong> {RssVideoOutputModeReg.getHelp('audio_hls')}
                            </p>
                            <p>
                                <strong>{RssVideoOutputModeReg.getLabel('audio_mp4')}</strong> {RssVideoOutputModeReg.getHelp('audio_mp4')}
                            </p>
                            <p>
                                <strong>{RssVideoOutputModeReg.getLabel('mp4')}</strong> {RssVideoOutputModeReg.getHelp('mp4')}
                            </p>
                            <p>
                                <strong>{RssVideoOutputModeReg.getLabel('mp4_hls')}</strong> {RssVideoOutputModeReg.getHelp('mp4_hls')}
                            </p>
                            <p>
                                The episode URLs in the RSS never change when a local download appears. The same WireLoft URL resolves to local media when available and to The Daily Wire only when the profile permits that fallback.
                            </p>
                        </ReadMore>
                    </div>
                </div>
            )}

            {usesHlsVideo && (
                <div className="form-row">
                    <label htmlFor="rss-stream-live-episodes">Stream live episodes</label>
                    <Controller
                        control={control}
                        name="streamLiveEpisodes"
                        render={({field}) => (
                            <Switch
                                id="rss-stream-live-episodes"
                                checked={!!field.value}
                                onChange={(checked) => field.onChange(checked)}
                                onColor="#0ea5e9"
                                offColor="#d1d5db"
                                uncheckedIcon={false}
                                checkedIcon={false}
                                aria-invalid={!!errors.streamLiveEpisodes}
                                aria-describedby={errors.streamLiveEpisodes ? 'rss-stream-live-episodes-error' : 'rss-stream-live-episodes-help'}
                            />
                        )}
                    />
                    {errors.streamLiveEpisodes && (
                        <div id="rss-stream-live-episodes-error" className="error" role="alert" aria-live="polite">
                            {String(errors.streamLiveEpisodes.message)}
                        </div>
                    )}
                    <div className="help" id="rss-stream-live-episodes-help">
                        <ReadMore summary={<span>Include matching episodes while they are live.</span>}>
                            <p>
                                With this setting enabled, you can view even episodes that are currently live at DW straight in your podcast player!
                            </p>
                            <p>
                                Live episodes still have to match this Stream Profile&apos;s episode-type filter in order to show up in the feed.
                            </p>
                            {!useDwStream && (
                                <>
                                    <p>
                                        Even though streaming from Daily Wire is disabled for this stream profile, streaming live episodes from DW
                                        still works. WireLoft even provides a clean handoff to the downloaded HLS file after the episode is no longer
                                        live: it waits for the download to finish first, and only then switches to streaming from your local file.
                                        Your podcasting app should not even notice this switch!
                                    </p>
                                    <p>
                                        NOTE: The profile does check whether the episode in question, when no longer live, will be
                                        downloaded by your download profiles as HLS. If not, the episode is not considered part of this
                                        downloads- only feed and will also not be included as a live episode.
                                    </p>
                                </>
                            )}
                            <p>
                                NOTE: live video only works if your podcast player supports playing HLS video.
                            </p>
                        </ReadMore>
                    </div>
                </div>
            )}

            {advisory}

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
