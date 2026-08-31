import {UseFormReturn} from 'react-hook-form'

import {MoviePreferredFormatReg} from '../../types/local_media_profile'
import LocalMediaProfileTypeFields from './LocalMediaProfileTypeFields'

export default function MovieLocalMediaProfileForm({form}: { form: UseFormReturn<any> }) {
    return (
        <LocalMediaProfileTypeFields
            form={form}
            mode="movie"
            pathPlaceholder={'/downloads/movies/{{ movie_title }}{% if year %} ({{ year }}){% endif %}/{{ title }}.ext'}
            formatRegistry={MoviePreferredFormatReg}
            templateHelp={(
                <>
                    <p>
                        Variables beginning with <b>movie_</b> always describe the parent movie. Variables such as
                        <b> {'{{ title }}'}</b>, <b> {'{{ dw_id }}'}</b>, and <b> {'{{ media_type }}'}</b> describe the
                        item being downloaded, which may be the movie or one of its extras.
                    </p>
                    <p>
                        Conditional year example:<br/>
                        <code>{"{{ movie_title }}{% if year %} ({{ year }}){% endif %}"}</code>
                    </p>
                    <p>
                        Add an extra type without changing movie filenames:<br/>
                        <code>{"{{ title }}{% if media_type != 'movie' %}-{{ media_type }}{% endif %}.ext"}</code>
                    </p>
                    <p>
                        Date variables describe the parent movie's canonical release date. If WireLoft does not have a
                        release date, those values are empty so a Jinja conditional can omit the surrounding text.
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
