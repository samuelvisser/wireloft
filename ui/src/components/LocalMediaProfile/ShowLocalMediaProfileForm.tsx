import {UseFormReturn} from 'react-hook-form'

import ShowLocalMediaProfileFields from './ShowLocalMediaProfileFields'
import ShowLocalMediaProfileOutputTemplate from './ShowLocalMediaProfileOutputTemplate'

export default function ShowLocalMediaProfileForm({form}: { form: UseFormReturn<any> }) {
    return (
        <>
            <ShowLocalMediaProfileFields form={form}/>
            <ShowLocalMediaProfileOutputTemplate form={form}/>
        </>
    )
}
