import {UseFormReturn} from 'react-hook-form'

import {MoviePreferredFormatReg} from '../../types/local_media_profile'
import ReadMore from '../../utils/ReadMore'
import LocalMediaProfileTypeFields from './LocalMediaProfileTypeFields'

export default function MovieLocalMediaProfileForm({form}: {form: UseFormReturn<any>}) {
    return (
        <LocalMediaProfileTypeFields
            form={form}
            pathPlaceholder="/downloads/movies/{movie_title}/{movie_title}.ext"
            formatRegistry={MoviePreferredFormatReg}
            templateHelp={(
                <ReadMore summary={<span>Output path where Wireloft will download movies</span>}>
                    <p>This path can be dynamically generated based on placeholders. Supported placeholders:</p>
                    <ul>
                        <li><b>{'{movie}'}</b> or <b>{'{movie_slug}'}</b>: The movie slug used in its Daily Wire URL</li>
                        <li><b>{'{movie_title}'}</b> or <b>{'{title}'}</b>: The shortened movie title</li>
                        <li><b>{'{movie_extended_title}'}</b> or <b>{'{extended_title}'}</b>: The full title supplied by Daily Wire</li>
                        <li><b>{'{movie_dw_id}'}</b> or <b>{'{dw_id}'}</b>: The Daily Wire movie ID</li>
                        <li><b>{'{movie_author}'}</b> or <b>{'{author}'}</b>: The movie author or host</li>
                        <li><b>{'{movie_mature_rating}'}</b>, <b>{'{mature_rating}'}</b> or <b>{'{rating}'}</b>: The movie rating</li>
                        <li><b>{'{movie_duration_seconds}'}</b> or <b>{'{duration_seconds}'}</b>: The runtime in seconds</li>
                    </ul>
                </ReadMore>
            )}
        />
    )
}
