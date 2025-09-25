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

type SeasonOption = { value: string; label: string; season: SeasonItem }
type IncludeOption = { value: typeof INCLUDE_UPCOMING_VALUE; label: string }
type UIOption = SeasonOption | IncludeOption

export default function DownloadProfileSeriesForm({form, seasons}: Props) {
    const {control, setValue, watch, formState: {errors}} = form

    // Prepare season options
    const seasonOptions: SeasonOption[] = useMemo(
        () => seasons.map((s) => ({
            value: s.slug,
            label: s.name,
            season: s
        })).reverse(), [seasons]
    )

    const includeUpcomingOption: IncludeOption = {
        value: INCLUDE_UPCOMING_VALUE,
        label: 'Include upcoming seasons'
    }

    // Build the select value from form state (multi select + special include option)
    const selectedSeasons: SeasonItem[] = watch('seasons') || []
    const selectedInclude: boolean = watch('includeUpcomingSeasons') || false

    const selectValue: UIOption[] = useMemo(() => {
        const vals: UIOption[] = selectedSeasons
            .map((s) => ({
                value: s.slug,
                label: s.name,
                season: s
            }))
        if (selectedInclude) vals.push(includeUpcomingOption)
        return vals
    }, [selectedSeasons, selectedInclude, includeUpcomingOption])

    // When the user changes the multiselect, persist SeasonItem[] to the form
    const handleSelectChange = (opts: readonly UIOption[] | null) => {
        const arr = Array.isArray(opts) ? [...opts] : []

        const include = arr.some((o) => o.value === INCLUDE_UPCOMING_VALUE)

        // Map chosen UI options back to full SeasonItem objects using the prepared option list
        const chosenSeasons: SeasonItem[] = arr
            .filter((o): o is SeasonOption => o.value !== INCLUDE_UPCOMING_VALUE)
            .map((o) => o.season)
            .filter(Boolean)

        setValue('includeUpcomingSeasons', include, {shouldDirty: true, shouldValidate: true})
        setValue('seasons', chosenSeasons, {shouldDirty: true, shouldValidate: true})
    }

    const handleSelectAll = () => {
        // Select all seasons and also include upcoming seasons
        setValue('includeUpcomingSeasons', true, {shouldDirty: true, shouldValidate: true})
        setValue('seasons', [...seasons], {shouldDirty: true, shouldValidate: true})
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
                        <button type="button" className="btn btn-link" onClick={handleSelectAll}>
                            Select all
                        </button>
                    </div>
                </div>
                <Controller
                    control={control}
                    name="seasons"
                    render={() => (
                        <Select
                            inputId="season-select"
                            isMulti
                            options={[
                                includeUpcomingOption,
                                ...seasonOptions
                            ]}
                            value={selectValue}
                            onChange={handleSelectChange as any}
                            closeMenuOnSelect={false}
                            getOptionValue={(o: UIOption) => o.value}
                            getOptionLabel={(o: UIOption) => o.label}
                            aria-invalid={!!errors.seasons}
                            aria-describedby={errors.seasons ? 'profile-seasons-validate' : undefined}
                        />
                    )}
                />
                {errors.seasons && (
                    <div id="profile-seasons-validate" className="error" role="alert" aria-live="polite">
                        {errors.seasons.message as string}
                    </div>
                )}
            </div>
        </>
    )
}
