import {UseFormReturn} from 'react-hook-form'

import {MoviePreferredFormatReg} from '../../types/local_media_profile'
import ReadMore from '../../utils/ReadMore'
import LocalMediaProfileTypeFields from './LocalMediaProfileTypeFields'

export default function MovieLocalMediaProfileForm({form}: { form: UseFormReturn<any> }) {
    const {register, formState: {errors}} = form

    return (
        <>
            <LocalMediaProfileTypeFields
                form={form}
                pathPlaceholder="/downloads/movies/{movie_title} ({year})/{title}.ext"
                formatRegistry={MoviePreferredFormatReg}
                templateHelp={(
                    <ReadMore summary={<span>Output path where WireLoft will download movies and their extras</span>}>
                        <p>
                            Placeholders beginning with <b>movie</b> always describe the movie a media item belongs to.
                            The alternatives without <b>movie</b> describe the item being downloaded, so for an extra
                            <b> {'{title}'}</b>, <b>{'{dw_id}'}</b> and <b>{'{duration_seconds}'}</b> describe the extra itself.
                        </p>
                        <p>Supported placeholders:</p>
                        <ul>
                            <li><b>{'{movie}'}</b> or <b>{'{movie_slug}'}</b>: The movie slug used in its Daily Wire URL</li>
                            <li><b>{'{movie_title}'}</b>: The movie title</li>
                            <li><b>{'{title}'}</b>: The downloaded item's title</li>
                            <li><b>{'{movie_extended_title}'}</b>: The full movie title supplied by Daily Wire</li>
                            <li><b>{'{extended_title}'}</b>: The downloaded item's full title; extras use their own title</li>
                            <li><b>{'{movie_dw_id}'}</b>: The movie's Daily Wire ID</li>
                            <li><b>{'{dw_id}'}</b>: The downloaded item's Daily Wire ID</li>
                            <li><b>{'{movie_author}'}</b>: The movie author or host</li>
                            <li><b>{'{author}'}</b>: The downloaded item's author when available</li>
                            <li><b>{'{movie_mature_rating}'}</b>: The movie rating</li>
                            <li><b>{'{mature_rating}'}</b> or <b>{'{rating}'}</b>: The downloaded item's rating when available</li>
                            <li><b>{'{movie_duration_seconds}'}</b>: The movie runtime in seconds</li>
                            <li><b>{'{duration_seconds}'}</b>: The downloaded item's runtime in seconds</li>
                            <li><b>{'{media_type}'}</b>: <b>movie</b>, <b>trailer</b>, <b>interview</b>, <b>behindthescenes</b>, or another extra type</li>
                            <li><b>{'{date}'}</b>: The parent movie's canonical release date (YYYY-MM-DD)</li>
                            <li><b>{'{year}'}</b>, <b>{'{month}'}</b>, <b>{'{day}'}</b>: Components of the parent movie's release date</li>
                            <li><b>{'{time}'}</b> or <b>{'{datetime}'}</b>: The release time or date and time</li>
                            <li><b>{'{hour}'}</b>, <b>{'{minute}'}</b>, <b>{'{second}'}</b>: Components of the release time</li>
                        </ul>
                        <p>
                            WireLoft obtains the canonical release date from TMDB once, when the movie is first indexed by
                            adding or downloading it, and saves it in the local database. TMDB provides a date without a release
                            time, so movie time placeholders resolve to midnight. The same parent movie release date is used for
                            a movie and all of its extras.
                        </p>
                        <p>
                            To prevent an extra from overwriting its movie, keep <b>Append media type to filename</b> enabled.
                            If you disable it, the path must contain at least one placeholder that describes the actual downloaded
                            item, such as <b>{'{title}'}</b>, <b>{'{duration_seconds}'}</b>, or <b>{'{media_type}'}</b>.
                        </p>
                    </ReadMore>
                )}
            />

            <div className="form-row">
                <label className="checkbox-label" htmlFor="mp-append-media-type">
                    <input
                        id="mp-append-media-type"
                        type="checkbox"
                        {...register('appendMediaTypeToFilename')}
                        aria-invalid={!!errors.appendMediaTypeToFilename}
                        aria-describedby={errors.appendMediaTypeToFilename ? 'append-type-error' : 'append-type-help'}
                    />
                    <span>Append media type to filename with a dash</span>
                </label>
                {errors.appendMediaTypeToFilename && (
                    <div id="append-type-error" className="error" role="alert" aria-live="polite">
                        {String(errors.appendMediaTypeToFilename.message)}
                    </div>
                )}
                <div id="append-type-help" className="help">
                    <ReadMore summary={<span>Appends any non-movie media types to the file name, e.g. adds "<code>-trailer</code>" before the file extension</span>}>
                        <p>Recommended for use with self-hosted media servers. Extras get their type appended immediately
                        before the file extension, such as <b>-trailer</b> or <b>-interview</b>; a movie gets no suffix.</p>

                        <p>For example, the movie would be downloaded as "<code>Run Hide Fight.mp4</code>" and
                            its trailer as "<code>Run Hide Fight-trailer.mp4</code>". Media servers often require this for
                        proper organization and playback, and it prevents an extra from overwriting the movie download.</p>
                    </ReadMore>
                </div>
            </div>
        </>
    )
}
