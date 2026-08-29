import {UseFormReturn} from 'react-hook-form'

import {MoviePreferredFormatReg} from '../../types/local_media_profile'
import ReadMore from '../../utils/ReadMore'
import LocalMediaProfileTypeFields from './LocalMediaProfileTypeFields'

export default function MovieLocalMediaProfileForm({form}: {form: UseFormReturn<any>}) {
    const {register, formState: {errors}} = form

    return (
        <>
            <LocalMediaProfileTypeFields
                form={form}
                pathPlaceholder="/downloads/movies/{movie_title}/{title}.ext"
                formatRegistry={MoviePreferredFormatReg}
                templateHelp={(
                    <ReadMore summary={<span>Output path where Wireloft will download movies and trailers</span>}>
                        <p>
                            Placeholders beginning with <b>movie</b> always describe the movie a media item belongs to.
                            The alternatives without <b>movie</b> describe the item being downloaded, so for a trailer
                            <b> {'{title}'}</b>, <b>{'{dw_id}'}</b> and <b>{'{duration_seconds}'}</b> describe the trailer itself.
                        </p>
                        <p>Supported placeholders:</p>
                        <ul>
                            <li><b>{'{movie}'}</b> or <b>{'{movie_slug}'}</b>: The parent movie slug used in its Daily Wire URL</li>
                            <li><b>{'{movie_title}'}</b>: The parent movie title</li>
                            <li><b>{'{title}'}</b>: The downloaded item's title (movie or trailer)</li>
                            <li><b>{'{movie_extended_title}'}</b>: The full parent movie title supplied by Daily Wire</li>
                            <li><b>{'{extended_title}'}</b>: The downloaded item's full title; trailers use their trailer title</li>
                            <li><b>{'{movie_dw_id}'}</b>: The parent movie's Daily Wire ID</li>
                            <li><b>{'{dw_id}'}</b>: The downloaded item's Daily Wire ID</li>
                            <li><b>{'{movie_author}'}</b>: The parent movie author or host</li>
                            <li><b>{'{author}'}</b>: The downloaded item's author when available</li>
                            <li><b>{'{movie_mature_rating}'}</b>: The parent movie rating</li>
                            <li><b>{'{mature_rating}'}</b> or <b>{'{rating}'}</b>: The downloaded item's rating when available</li>
                            <li><b>{'{movie_duration_seconds}'}</b>: The parent movie runtime in seconds</li>
                            <li><b>{'{duration_seconds}'}</b>: The downloaded item's runtime in seconds</li>
                            <li><b>{'{media_type}'}</b>: <b>movie</b> or <b>trailer</b></li>
                        </ul>
                        <p>
                            To prevent a trailer from overwriting its movie, keep <b>Append media type to filename</b> enabled.
                            If you disable it, the path must contain at least one placeholder that describes the actual downloaded
                            item, such as <b>{'{title}'}</b>, <b>{'{dw_id}'}</b>, <b>{'{duration_seconds}'}</b>, or <b>{'{media_type}'}</b>.
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
                    />
                    <span>Append media type to filename with a dash</span>
                </label>
                <div className="help">
                    Recommended for Plex and similar media servers. A trailer gets <b>-trailer</b> appended immediately
                    before the file extension; a movie gets no suffix. For example, <code>Run Hide Fight.ext</code> and
                    <code> Official Trailer-trailer.ext</code> cannot overwrite each other.
                </div>
                {errors.appendMediaTypeToFilename && (
                    <div className="error" role="alert" aria-live="polite">
                        {String(errors.appendMediaTypeToFilename.message)}
                    </div>
                )}
            </div>
        </>
    )
}
