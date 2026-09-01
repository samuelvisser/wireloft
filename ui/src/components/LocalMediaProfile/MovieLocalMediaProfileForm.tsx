import {UseFormReturn} from 'react-hook-form'

import {MoviePreferredFormatReg} from '../../types/local_media_profile'
import LocalMediaProfileTypeFields from './LocalMediaProfileTypeFields'

export default function MovieLocalMediaProfileForm({form}: { form: UseFormReturn<any> }) {
    return (
        <LocalMediaProfileTypeFields
            form={form}
            mode="movie"
            pathPlaceholder={'/downloads/movies/{{ movie_title }}{% if movie_year %} ({{ movie_year }}){% endif %}/{{ title }}.ext'}
            formatRegistry={MoviePreferredFormatReg}
            templateHelp={(
                <>
                    <p>
                        Every variable beginning with <b>movie_</b> describes the parent movie. Every variable without
                        that prefix describes the item being downloaded. For a movie download both contexts describe
                        the movie; for an extra download variables such as <b> {'{{ title }}'}</b>,
                        <b> {'{{ slug }}'}</b>, and <b> {'{{ year }}'}</b> describe that extra.
                    </p>
                    <p>
                        Add the parent movie's release year when known:<br/>
                        <code>{"{{ movie_title }}{% if movie_year %} ({{ movie_year }}){% endif %}"}</code>
                    </p>
                    <p>
                        Add an extra type without changing movie filenames:<br/>
                        <code>{"{{ title }}{% if media_type != 'movie' %}-{{ media_type }}{% endif %}.ext"}</code>
                    </p>
                    <p>
                        Unprefixed date variables use the current item's date: the release date for a movie or the
                        publication timestamp for an extra. The <b>movie_</b> date variables always use the parent
                        movie's release date. Dates WireLoft does not know are empty, so a conditional can omit them.
                    </p>
                    <p>
                        Daily Wire does not currently provide separate author or rating metadata for movie extras, so
                        unprefixed <b>{'{{ author }}'}</b>, <b>{'{{ mature_rating }}'}</b>, and
                        <b> {'{{ rating }}'}</b> are empty for those items. Their <b>movie_</b> equivalents remain
                        available from the parent movie.
                    </p>
                    <p>
                        The filename should reference an item-specific variable such as <b>{'{{ title }}'}</b> or
                        <b> {'{{ media_type }}'}</b> so an extra cannot overwrite its movie.
                    </p>
                </>
            )}
        />
    )
}
