import {useEffect} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import DownloadProfileForm from '../../DownloadProfile/DownloadProfileForm'
import {buildServerAwareSubmit} from '../../../utils/buildServerAwareSubmit'
import {
    DownloadProfileUnifiedCreateIn,
    DownloadProfileUnifiedCreateOut, DownloadProfileUnifiedCreateSchema
} from "../../../types/schemas/show_as_bundle";
import {SeasonDetachedOut} from "../../../types/schemas/season";

export type SeasonItem = SeasonDetachedOut

export type SeriesDownloadProfileProps = {
    value: Partial<DownloadProfileUnifiedCreateIn>
    onChange: (v: Partial<DownloadProfileUnifiedCreateIn>) => void;
    onSubmit: (v: DownloadProfileUnifiedCreateOut) => void;
    seasons: SeasonItem[]
    onBack: () => void
    onContinue: () => void
    onCancel: () => void
    continueLabel?: string
}


export default function SeriesDownloadProfileStep({
                                                      value, onChange, onSubmit: onSubmitParent, seasons, onBack,
                                                      onContinue, onCancel, continueLabel = 'Continue'
                                                  }: SeriesDownloadProfileProps) {
    const latestSeason = seasons.length > 0 ? seasons[seasons.length - 1] : undefined
    const selectedSeasons = (value as {seasons?: SeasonItem[]}).seasons
    const defaultValues: Partial<DownloadProfileUnifiedCreateIn> = {
        ...value,
        seasons: selectedSeasons === undefined
            ? (latestSeason ? [latestSeason] : [])
            : selectedSeasons,
    } as Partial<DownloadProfileUnifiedCreateIn>

    const form = useForm<DownloadProfileUnifiedCreateIn>({
        resolver: zodResolver(DownloadProfileUnifiedCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues,
    })
    const {watch} = form

    // Subscribe to ALL changes
    useEffect(() => {
        const subscription = watch((values) => {
            onChange(values as any); // push up on every change
        });
        return () => subscription.unsubscribe();
    }, [watch, onChange]);

    const onSubmit = buildServerAwareSubmit(form, async (dataOut: DownloadProfileUnifiedCreateOut) => {
        onSubmitParent(dataOut)
        onContinue()
    })

    return (
        <form className="form form-fluid" onSubmit={onSubmit} noValidate>
            <DownloadProfileForm form={form} mode="series" seasons={seasons}/>

            <div className="actions">
                <button type="button" className="btn" onClick={onBack}>Back</button>
                <input type="submit" className="btn btn-primary" value={continueLabel} />
                <button type="button" className="btn" onClick={onCancel}>Cancel</button>
            </div>
        </form>
    )
}
