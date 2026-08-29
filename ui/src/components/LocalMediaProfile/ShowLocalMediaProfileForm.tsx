import {UseFormReturn} from 'react-hook-form'

import {PreferredFormatReg} from '../../types/local_media_profile'
import ReadMore from '../../utils/ReadMore'
import LocalMediaProfileTypeFields from './LocalMediaProfileTypeFields'

export default function ShowLocalMediaProfileForm({form}: {form: UseFormReturn<any>}) {
    return (
        <LocalMediaProfileTypeFields
            form={form}
            pathPlaceholder="/downloads/shows/{show}/{episode_title}.ext"
            formatRegistry={PreferredFormatReg}
            templateHelp={(
                <ReadMore summary={<span>Output path where Wireloft will download show episodes</span>}>
                    <p>This path can be dynamically generated based on placeholders. Supported placeholders:</p>
                    <ul>
                        <li><b>{'{show}'}</b>: The slug of the show (the show's name in the URL)</li>
                        <li><b>{'{show_title}'}</b>: The title of the show</li>
                        <li><b>{'{season}'}</b>: The slug of the season (the season's name in the URL)</li>
                        <li><b>{'{season_name}'}</b>: The name of the season</li>
                        <li><b>{'{episode}'}</b>: The slug of the episode (the episode's name in the URL)</li>
                        <li><b>{'{episode_title}'}</b> or <b>{'{title}'}</b>: The title of the episode</li>
                        <li><b>{'{episode_type}'}</b>: The episode type as categorized by Wireloft<br/>
                            Supported types are: 'ep', 'ep-extra', 'auxiliary', 'trailer'</li>
                        <li><b>{'{episode_number}'}</b>: The episode number</li>
                        <li><b>{'{ep_id}'}</b>: The full episode identifier</li>
                        <li><b>{'{episode_published_date}'}</b> or <b>{'{date}'}</b>: The published date of the episode (Y-m-d)</li>
                        <li><b>{'{episode_published_time}'}</b> or <b>{'{time}'}</b>: The published time of the episode (H:M:S)</li>
                        <li><b>{'{episode_published_datetime}'}</b> or <b>{'{datetime}'}</b>: The published date and time of the episode (Y-m-d H:M:S)</li>
                    </ul>
                </ReadMore>
            )}
        />
    )
}
