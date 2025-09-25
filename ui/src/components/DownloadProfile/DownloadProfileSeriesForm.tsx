import {Controller, UseFormReturn} from 'react-hook-form'
import Select from 'react-select'
import Switch from 'react-switch'
import {useMemo} from 'react'
import ReadMore from "../../utils/ReadMore";
import {SeasonDetachedOut} from "../../types/schemas/season";

export type SeasonItem = SeasonDetachedOut

type Props = {
    form: UseFormReturn<any>
    seasons: SeasonItem[]
    mode?: 'create' | 'update'
}

// Special value to represent the boolean includeUpcomingSeasons inside the select UI
const INCLUDE_UPCOMING_VALUE = '__include_upcoming__'

export default function DownloadProfileSeriesForm({form, seasons}: Props) {
    const {control, setValue, watch, formState: {errors}} = form

    // Prepare season options
    const seasonOptions = useMemo(() => (
        seasons.map(s => ({value: s.slug, label: s.name})).reverse()
    ), [seasons])

    // Build the select value from form state (multi select + special include option)
    const selectedSeasonSlugs = watch('seasons') || []
    const selectedInclude = watch('includeUpcomingSeasons') || false
    const selectValue = useMemo(() => {
        const vals = [...selectedSeasonSlugs.map((slug: string) => ({
            value: slug,
            label: seasonOptions.find(o => o.value === slug)?.label || slug
        }))]
        if (selectedInclude) vals.push({value: INCLUDE_UPCOMING_VALUE, label: 'Include upcoming seasons'})
        return vals
    }, [selectedSeasonSlugs, selectedInclude, seasonOptions])

    const handleSelectChange = (opts: readonly { value: string; label: string }[] | null) => {
        const arr = Array.isArray(opts) ? [...opts] : []
        const include = arr.some(o => o.value === INCLUDE_UPCOMING_VALUE)
        const slugs = arr.filter(o => o.value !== INCLUDE_UPCOMING_VALUE).map(o => o.value)
        setValue('includeUpcomingSeasons', include, {shouldDirty: true, shouldValidate: true})
        setValue('seasons', slugs, {shouldDirty: true, shouldValidate: true})
    }

    const handleSelectAll = () => {
        // Select all seasons and also include upcoming seasons
        setValue('includeUpcomingSeasons', true, {shouldDirty: true, shouldValidate: true})
        setValue('seasons', seasonOptions.map(o => o.value), {shouldDirty: true, shouldValidate: true})
    }

    return (
        <>
            {errors.root && (
                <div className="form-error-card" role="alert" aria-live="polite">
                    {String(errors.root.message)}
                </div>
            )}

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
                            aria-describedby={errors.type ? 'profile-enable-validate' : 'profile-enable-help'}
                        />
                    )}
                />
                {errors.enableProfile && (
                    <div id="profile-enable-validate" className="error" role="alert" aria-live="polite">
                        {errors.enableProfile.message as string}
                    </div>
                )}
                <div className="help" id="profile-enable-help">
                    <ReadMore summary={<span>Whether to automatically download episodes</span>}>
                        If you disable the download profile, the show will still be indexed and you can still manually
                        download episodes in the show.
                    </ReadMore>
                </div>
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
                    name="seasons"
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
                {errors.seasons && (
                    <div className="error" role="alert" aria-live="polite">
                        {errors.seasons.message as string}
                    </div>
                )}
            </div>
        </>
    )
}
