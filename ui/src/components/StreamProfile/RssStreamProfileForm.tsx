import {useState} from 'react'
import {UseFormReturn} from 'react-hook-form'
import ReadMore from '../../utils/ReadMore'

// Only renders fields specific to the RSS stream profile implementation
// Common stream profile fields are rendered by StreamProfileForm

type Props = {
    form: UseFormReturn<any>
    // Creating a profile: the feed URL doesn't exist yet (it needs the
    // profile's secret token, minted server-side), so the field is optional
    // and there's nothing to copy or regenerate yet.
    isCreating?: boolean
    onRegenerateToken?: () => void | Promise<void>
    regeneratingToken?: boolean
}

export default function RssStreamProfileForm({form, isCreating, onRegenerateToken, regeneratingToken}: Props) {
    const {formState: {errors}, register, watch} = form
    const [copied, setCopied] = useState(false)

    const feedUrl: string | undefined = watch('feedUrl')

    const onCopy = async () => {
        if (!feedUrl) return
        try {
            await navigator.clipboard.writeText(feedUrl)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        } catch {
            // Clipboard access can be denied by the browser; the field is still selectable/copyable by hand.
        }
    }

    return (
        <>
            {/* RSS Feed URL */}
            <div className="form-row">
                <label htmlFor="feed-url">RSS feed URL</label>
                <input
                    id="feed-url"
                    className="input"
                    type="text"
                    placeholder={isCreating ? 'Leave blank to auto-generate' : 'https://example.com/feed.xml'}
                    {...register('feedUrl')}
                    aria-invalid={!!errors.feedUrl}
                    aria-describedby={errors.feedUrl ? 'feed-url-error' : 'feed-url-help'}
                />
                {errors.feedUrl && (
                    <div id="feed-url-error" className="error" role="alert" aria-live="polite">
                        {String(errors.feedUrl.message)}
                    </div>
                )}
                <div className="help" id="feed-url-help">
                    <ReadMore summary={<span>Paste this URL into your podcast app.</span>}>
                        <p>
                            {isCreating
                                ? 'WireLoft generates a working feed URL automatically once you create this profile. You can leave this blank, or set your own if you access WireLoft through a different address (e.g. a reverse proxy).'
                                : 'This feed stays reachable even when local authentication is enabled for the WireLoft UI, so your podcast app never needs to log in. You can freely edit this text (for example to reflect a different hostname); the feed itself keeps working either way.'}
                        </p>
                        {!isCreating && (
                            <p>
                                If this URL ever leaks, use <strong>Regenerate</strong> below to mint a new one and immediately invalidate the old one.
                            </p>
                        )}
                    </ReadMore>
                </div>
                {!isCreating && (
                    <div className="actions" style={{marginTop: 8}}>
                        <button type="button" className="btn" onClick={onCopy} disabled={!feedUrl}>
                            {copied ? 'Copied!' : 'Copy'}
                        </button>
                        {onRegenerateToken && (
                            <button type="button" className="btn btn-danger" onClick={onRegenerateToken} disabled={!!regeneratingToken}>
                                {regeneratingToken ? 'Regenerating…' : 'Regenerate'}
                            </button>
                        )}
                    </div>
                )}
            </div>
        </>
    )
}
