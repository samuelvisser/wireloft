import {useEffect} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import DownloadProfilePodcastForm from '../../DownloadProfile/DownloadProfilePodcastForm'
import {buildServerAwareSubmit} from '../../../utils/buildServerAwareSubmit'
import {
    DownloadProfileUnifiedCreateIn, DownloadProfileUnifiedCreateOut,
    DownloadProfileUnifiedCreateSchema
} from "../../../types/schemas/show_with_profiles";

export type DownloadProfilePodcastProps = {
    value: Partial<DownloadProfileUnifiedCreateIn>
    onChange: (v: Partial<DownloadProfileUnifiedCreateIn>) => void;
    onSubmit: (v: DownloadProfileUnifiedCreateOut) => void;
    onBack: () => void
    onFinish: () => void
    onCancel: () => void
}

export default function DownloadProfilePodcastStep({value, onChange, onSubmit: onSubmitParent, onBack, onFinish, onCancel}: DownloadProfilePodcastProps) {
    const form = useForm<DownloadProfileUnifiedCreateIn>({
        resolver: zodResolver(DownloadProfileUnifiedCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: value,
    })

    const {watch, setValue, formState: {isSubmitting}} = form

    // Subscribe to ALL changes
    useEffect(() => {
        const subscription = watch((values) => {
            onChange(values as any); // push up on every change
        });
        return () => subscription.unsubscribe();
    }, [watch, onChange]);

    // If countdown is disabled, redownload final becomes irrelevant and is hidden
    const withCountdown = watch('downloadWithCountdown')
    useEffect(() => {
        if (!withCountdown) {
            setValue('redownloadFinal', true, {shouldDirty: true, shouldValidate: false})
        }
    }, [withCountdown, setValue])


    const onSubmit = buildServerAwareSubmit(form, async (dataOut: DownloadProfileUnifiedCreateOut) => {
        onSubmitParent(dataOut)
        onFinish()
    })

    return (
        <form className="form form-fluid" onSubmit={onSubmit} noValidate>
            <DownloadProfilePodcastForm form={form}/>

            <div className="actions">
                <button type="button" className="btn" onClick={onBack}>Back</button>
                <input type="submit" className="btn btn-primary" value="Finish" disabled={isSubmitting}/>
                <button type="button" className="btn" onClick={onCancel}>Cancel</button>
            </div>
        </form>
    )
}
