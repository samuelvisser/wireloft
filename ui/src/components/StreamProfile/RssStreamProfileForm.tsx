import {UseFormReturn} from 'react-hook-form'

// Only renders fields specific to the RSS stream profile implementation
// Common stream profile fields are rendered by StreamProfileForm

type Props = {
    form: UseFormReturn<any>
}

export default function RssStreamProfileForm({form}: Props) {
    const {formState: {errors}, register} = form

    return (
        <>
            {/* RSS Feed URL */}
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
