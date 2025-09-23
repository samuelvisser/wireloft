import {useEffect, useMemo} from 'react'
import {Controller, SubmitHandler, useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import Select from 'react-select'
import Switch from 'react-switch'
import {
    DownloadProfileSeriesCreateIn, DownloadProfileSeriesCreateOut,
    DownloadProfileSeriesCreateSchema,
} from '../../types/schemas/download_profile_series'


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

// Special value to represent the boolean includeUpcomingSeasons inside the select UI
const INCLUDE_UPCOMING_VALUE = '__include_upcoming__'

export default function DownloadProfileSeries({
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
    const {control, setValue, watch, handleSubmit, formState: {errors, isSubmitting}} = form

    // Subscribe to ALL changes
    useEffect(() => {
        const subscription = watch((values) => {
            onChange(values); // push up on every change
        });
        return () => subscription.unsubscribe();
    }, [watch, onChange]);

    // Prepare season options
    const seasonOptions = useMemo(() => (
        seasons.map(s => ({value: s.slug, label: s.name})).reverse()
    ), [seasons])

    // Build the select value from form state (multi select + special include option)
    const selectedSeasonSlugs = watch('downloadSeasonList') || []
    const selectedInclude = watch('includeUpcomingSeasons') || false
    const selectValue = useMemo(() => {
        const vals = [...selectedSeasonSlugs.map(slug => ({
            value: slug,
            label: seasonOptions.find(o => o.value === slug)?.label || slug
        }))]
        if (selectedInclude) vals.push({value: INCLUDE_UPCOMING_VALUE, label: 'Include upcoming seasons'})
        return vals
    }, [selectedSeasonSlugs, selectedInclude, seasonOptions])

    const onSubmit: SubmitHandler<DownloadProfileSeriesCreateIn> = (dataIn: DownloadProfileSeriesCreateIn) => {
        const dataOut = Schema.parse(dataIn)
        onSubmitParent(dataOut)
        onFinish()
    }

    const handleSelectChange = (opts: readonly { value: string; label: string }[] | null) => {
        const arr = Array.isArray(opts) ? [...opts] : []
        const include = arr.some(o => o.value === INCLUDE_UPCOMING_VALUE)
        const slugs = arr.filter(o => o.value !== INCLUDE_UPCOMING_VALUE).map(o => o.value)
        setValue('includeUpcomingSeasons', include, {shouldDirty: true, shouldValidate: true})
        setValue('downloadSeasonList', slugs, {shouldDirty: true, shouldValidate: true})
    }

    const handleSelectAll = () => {
        // Select all seasons and also include upcoming seasons
        setValue('includeUpcomingSeasons', true, {shouldDirty: true, shouldValidate: true})
        setValue('downloadSeasonList', seasonOptions.map(o => o.value), {shouldDirty: true, shouldValidate: true})
    }

    return (
        <form className="form form-fluid" onSubmit={handleSubmit(onSubmit)} noValidate>
            <div className="form-row">
                <label htmlFor="enable-profile">Enable automatic downloads</label>
                <Controller
                    control={control}
                    name="enableProfile"
                    render={({field}) => (
                        <Switch
                            id="enable-profile"
                            checked={!!field.value}
                            onChange={(checked) => field.onChange(checked)}
                            onColor="#0ea5e9"
                            offColor="#d1d5db"
                            uncheckedIcon={false}
                            checkedIcon={false}
                            aria-invalid={!!errors.enableProfile}
                        />
                    )}
                />
            </div>

            <div className="form-row">
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                    <label htmlFor="season-select">Seasons to download</label>
                    <div>
                        <button type="button" className="btn btn-link" onClick={handleSelectAll}>Select all</button>
                    </div>
                </div>
                <Controller
                    control={control}
                    name="downloadSeasonList"
                    render={() => (
                        <Select
                            inputId="season-select"
                            isMulti
                            options={[{
                                value: INCLUDE_UPCOMING_VALUE,
                                label: 'Include upcoming seasons'
                            }, ...seasonOptions]}
                            value={selectValue}
                            onChange={handleSelectChange as any}
                            closeMenuOnSelect={false}
                        />
                    )}
                />
                {errors.downloadSeasonList && (
                    <div className="error" role="alert" aria-live="polite">
                        {errors.downloadSeasonList.message as string}
                    </div>
                )}
            </div>

            <div className="actions">
                <button type="button" className="btn" onClick={onBack}>Back</button>
                <input type="submit" className="btn btn-primary" value="Finish" disabled={isSubmitting}/>
                <button type="button" className="btn" onClick={onCancel}>Cancel</button>
            </div>
        </form>
    )
}
