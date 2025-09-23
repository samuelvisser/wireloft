import {useEffect} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {
    DownloadProfileSeriesCreateIn, DownloadProfileSeriesCreateOut,
    DownloadProfileSeriesCreateSchema,
} from '../../../types/schemas/download_profile_series'
import DownloadProfileSeriesForm from '../../DownloadProfile/DownloadProfileSeriesForm'
import {buildServerAwareSubmit} from '../../../utils/buildServerAwareSubmit'

export type SeasonItem = { slug: string; name: string }

export type DownloadProfileSeriesProps = {
    value: Partial<DownloadProfileSeriesCreateIn>
    onChange: (v: Partial<DownloadProfileSeriesCreateIn>) => void;
    onSubmit: (v: DownloadProfileSeriesCreateOut) => void;
    seasons: SeasonItem[]
    onBack: () => void
    onFinish: () => void
    onCancel: () => void
}


export default function DownloadProfileSeriesStep({
                                                  value, onChange, onSubmit: onSubmitParent, seasons, onBack,
                                                  onFinish, onCancel
                                              }: DownloadProfileSeriesProps) {
    // Extend schema to require at least one season chosen if includeUpcomingSeasons is false
    const Schema = DownloadProfileSeriesCreateSchema.superRefine((v, ctx) => {
        if (!v.includeUpcomingSeasons && (!v.downloadSeasonList || v.downloadSeasonList.length === 0)) {
            ctx.addIssue({
                code: 'custom',
                path: ['downloadSeasonList'],
                message: 'Choose at least one season or enable "Include upcoming seasons".',
            })
        }
    })

    const form = useForm<DownloadProfileSeriesCreateIn>({
        resolver: zodResolver(Schema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: value,
    })
    const {watch, formState: {isSubmitting}} = form

    // Subscribe to ALL changes
    useEffect(() => {
        const subscription = watch((values) => {
            onChange(values); // push up on every change
        });
        return () => subscription.unsubscribe();
    }, [watch, onChange]);

    const onSubmit = buildServerAwareSubmit(form, async (dataIn: DownloadProfileSeriesCreateIn) => {
        const dataOut = Schema.parse(dataIn)
        onSubmitParent(dataOut)
        onFinish()
    }, {
        fallbackField: 'enableProfile',
        rootClientValidationMessage: 'Please fix the highlighted fields.',
    })

    return (
        <form className="form form-fluid" onSubmit={onSubmit} noValidate>
            <DownloadProfileSeriesForm form={form} seasons={seasons} />

            <div className="actions">
                <button type="button" className="btn" onClick={onBack}>Back</button>
                <input type="submit" className="btn btn-primary" value="Finish" disabled={isSubmitting}/>
                <button type="button" className="btn" onClick={onCancel}>Cancel</button>
            </div>
        </form>
    )
}
