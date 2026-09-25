import {UseFormReturn} from 'react-hook-form'

import OutputTemplateEditor from './OutputTemplateEditor'

export default function ShowLocalMediaProfileOutputTemplate({form}: { form: UseFormReturn<any> }) {
    return (
        <OutputTemplateEditor
            form={form}
            mode="show"
            placeholder={'/downloads/shows/{{ show }}/{{ episode_title }}.ext'}
            help={(
                <>
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
                </>
            )}
        />
    )
}
