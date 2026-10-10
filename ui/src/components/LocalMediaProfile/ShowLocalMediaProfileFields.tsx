import {type UseFormReturn} from 'react-hook-form'

import {PreferredFormatReg} from '../../types/local_media_profile'
import LocalMediaProfilePreferredFormatField from './LocalMediaProfilePreferredFormatField'

export default function ShowLocalMediaProfileFields({form}: {form: UseFormReturn<any>}) {
    return <LocalMediaProfilePreferredFormatField form={form} formatRegistry={PreferredFormatReg}/>
}
