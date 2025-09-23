import {useEffect} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {
    DownloadProfilePodcastCreateSchema,
    type DownloadProfilePodcastCreateOut, DownloadProfilePodcastCreateIn
} from '../../../types/schemas/download_profile_podcast'
import DownloadProfilePodcastForm from '../../DownloadProfile/DownloadProfilePodcastForm'
import {buildServerAwareSubmit} from '../../../utils/buildServerAwareSubmit'

export type DownloadProfilePodcastProps = {
    value: Partial<DownloadProfilePodcastCreateIn>
    onChange: (v: Partial<DownloadProfilePodcastCreateIn>) => void;
    onSubmit: (v: DownloadProfilePodcastCreateOut) => void;
    onBack: () => void
    onFinish: () => void
    onCancel: () => void
}

export default function DownloadProfilePodcastStep({
                                                   value, onChange, onSubmit: onSubmitParent, onBack, onFinish, onCancel
                                               }: DownloadProfilePodcastProps) {
    const form = useForm<DownloadProfilePodcastCreateIn>({
        resolver: zodResolver(DownloadProfilePodcastCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: value,
    })

    const {watch, setValue, formState: {isSubmitting}} = form

    // Subscribe to ALL changes
    useEffect(() => {
        const subscription = watch((values) => {
            onChange(values); // push up on every change
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


    const onSubmit = buildServerAwareSubmit(form, async (dataIn: DownloadProfilePodcastCreateIn) => {
        console.log('submitting', dataIn)
        const dataOut = DownloadProfilePodcastCreateSchema.parse(dataIn)
        onSubmitParent(dataOut)
        onFinish()
    }, {
        fallbackField: 'enableProfile',
        aliasToFallback: ['showId'],
        rootClientValidationMessage: 'Please fix the highlighted fields.',
    })

    return (
        <form className="form form-fluid" onSubmit={onSubmit} noValidate>
            <DownloadProfilePodcastForm form={form} />

            <div className="actions">
                <button type="button" className="btn" onClick={onBack}>Back</button>
                <input type="submit" className="btn btn-primary" value="Finish" disabled={isSubmitting}/>
                <button type="button" className="btn" onClick={onCancel}>Cancel</button>
            </div>
        </form>
    )
}
