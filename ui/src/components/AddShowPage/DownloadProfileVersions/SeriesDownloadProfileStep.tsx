import {useEffect} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import DownloadProfileForm from '../../DownloadProfile/DownloadProfileForm'
import {buildServerAwareSubmit} from '../../../utils/buildServerAwareSubmit'
import {
    DownloadProfileUnifiedCreateIn,
    DownloadProfileUnifiedCreateOut, DownloadProfileUnifiedCreateSchema
} from "../../../types/schemas/show_with_profiles";
import {SeasonDetachedOut} from "../../../types/schemas/season";

export type SeasonItem = SeasonDetachedOut

export type SeriesDownloadProfileProps = {
    value: Partial<DownloadProfileUnifiedCreateIn>
    onChange: (v: Partial<DownloadProfileUnifiedCreateIn>) => void;
    onSubmit: (v: DownloadProfileUnifiedCreateOut) => void;
    seasons: SeasonItem[]
    onBack: () => void
    onFinish: () => void
    onCancel: () => void
}


export default function SeriesDownloadProfileStep({
                                                      value, onChange, onSubmit: onSubmitParent, seasons, onBack,
                                                      onFinish, onCancel
                                                  }: SeriesDownloadProfileProps) {
    const form = useForm<DownloadProfileUnifiedCreateIn>({
        resolver: zodResolver(DownloadProfileUnifiedCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: value,
    })
    const {watch, formState: {isSubmitting}} = form

    // Subscribe to ALL changes
    useEffect(() => {
        const subscription = watch((values) => {
            onChange(values as any); // push up on every change
        });
        return () => subscription.unsubscribe();
    }, [watch, onChange]);

    const onSubmit = buildServerAwareSubmit(form, async (dataOut: DownloadProfileUnifiedCreateOut) => {
        onSubmitParent(dataOut)
        onFinish()
    })

    return (
        <form className="form form-fluid" onSubmit={onSubmit} noValidate>
            <DownloadProfileForm form={form} mode="series" seasons={seasons}/>

            <div className="actions">
                <button type="button" className="btn" onClick={onBack}>Back</button>
                <input type="submit" className="btn btn-primary" value="Finish" disabled={isSubmitting}/>
                <button type="button" className="btn" onClick={onCancel}>Cancel</button>
            </div>
        </form>
    )
}
