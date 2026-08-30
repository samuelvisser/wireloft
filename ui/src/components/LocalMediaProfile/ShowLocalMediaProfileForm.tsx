import {UseFormReturn} from 'react-hook-form'

import {PreferredFormatReg} from '../../types/local_media_profile'
import ReadMore from '../../utils/ReadMore'
import LocalMediaProfileTypeFields from './LocalMediaProfileTypeFields'

export default function ShowLocalMediaProfileForm({form}: {form: UseFormReturn<any>}) {
    return (
        <LocalMediaProfileTypeFields
            form={form}
            mode="show"
            pathPlaceholder={'/downloads/shows/{{ show }}/{{ episode_title }}.ext'}
            formatRegistry={PreferredFormatReg}
            templateHelp={(
                <ReadMore summary={<span>Use Jinja to organize show episodes. Type <code>{'{{'}</code> to choose a variable.</span>}>
                    <p>
                        Show, season, episode, and publication-date values are available. The editor's variable menu
                        lists every supported value and explains what it represents.
                    </p>
                    <p>
                        Conditional year example:<br/>
                        <code>{"{{ episode_title }}{% if year %} ({{ year }}){% endif %}.ext"}</code>
                    </p>
                    <p>
                        If a date, season, or another optional value is not known, it is an empty string. Use an
                        <b> if</b> block to omit any punctuation or folders that belong with it.
                    </p>
                </ReadMore>
            )}
        />
    )
}
