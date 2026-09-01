import {useEffect} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import DailywireShowCard from './DailywireShowCard'
import StreamProfileForm, {StreamDownloadProfileDefault} from '../StreamProfile/StreamProfileForm'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {
    RssStreamProfileBundleIn,
    RssStreamProfileBundleOut,
    RssStreamProfileBundleSchema,
} from '../../types/schemas/show_as_bundle'

type Props = {
    value: Partial<RssStreamProfileBundleIn>
    onChange: (value: Partial<RssStreamProfileBundleIn>) => void
    onSubmit: (value: RssStreamProfileBundleOut) => void
    onBack: () => void
    onFinish: () => void
    onCancel: () => void
    showSlug?: string
    downloadProfileDefaults?: StreamDownloadProfileDefault[]
    episodeTypesManuallyChanged?: boolean
    onEpisodeTypesManuallyChanged?: () => void
}

export default function StreamProfileStep({
    value,
    onChange,
    onSubmit: onSubmitParent,
    onBack,
    onFinish,
    onCancel,
    showSlug,
    downloadProfileDefaults,
    episodeTypesManuallyChanged,
    onEpisodeTypesManuallyChanged,
}: Props) {
    const form = useForm<RssStreamProfileBundleIn>({
        resolver: zodResolver(RssStreamProfileBundleSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: value as RssStreamProfileBundleIn,
    })
    const {watch, formState: {isSubmitting}} = form

    useEffect(() => {
        const subscription = watch((values) => onChange(values))
        return () => subscription.unsubscribe()
    }, [watch, onChange])

    const onSubmit = buildServerAwareSubmit(form as any, async (dataIn: RssStreamProfileBundleIn) => {
        const dataOut = RssStreamProfileBundleSchema.parse(dataIn)
        onSubmitParent(dataOut)
        onFinish()
    }, {
        rootClientValidationMessage: 'Please fix the highlighted fields.',
    })

    return (
        <div className="wizard-with-aside">
            <div className="wizard-main">
                <form className="form form-fluid" onSubmit={onSubmit} noValidate>
                    <StreamProfileForm
                        form={form as any}
                        mode="rss"
                        showRoot
                        isCreating
                        downloadProfileDefaults={downloadProfileDefaults}
                        episodeTypesManuallyChanged={episodeTypesManuallyChanged}
                        onEpisodeTypesManuallyChanged={onEpisodeTypesManuallyChanged}
                    />
                    <div className="actions">
                        <button type="button" className="btn" onClick={onBack}>Back</button>
                        <input type="submit" className="btn btn-primary" value="Save show" disabled={isSubmitting}/>
                        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    </div>
                </form>
            </div>

            {showSlug ? (
                <aside className="wizard-aside" aria-label="Selected show details">
                    <DailywireShowCard showSlug={showSlug}/>
                </aside>
            ) : null}
        </div>
    )
}
