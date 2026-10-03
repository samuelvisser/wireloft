import {Controller, UseFormReturn} from 'react-hook-form'
import Select from 'react-select'
import {useMemo} from 'react'
import {SeasonDetachedOut} from "../../types/schemas/season";
import ReadMore from "../../utils/ReadMore";
import {createSelectRegistry} from "../../utils/selectRegistry";

export type SeasonItem = SeasonDetachedOut

type Props = {
    form: UseFormReturn<any>
    seasons: SeasonItem[]
    mode?: 'create' | 'update'
}

// Special value to represent the boolean includeUpcomingSeasons inside the select UI
const INCLUDE_UPCOMING_VALUE = '__include_upcoming__'

type UIOption = {value: string; label: string}

export default function SeriesDownloadProfileForm({form, seasons}: Props) {
    const {control, setValue, watch, formState: {errors}} = form

    const seasonReg = useMemo(() => {
        const spec: Record<string, {label: string}> = {
            [INCLUDE_UPCOMING_VALUE]: {label: 'Include upcoming seasons'},
        }
        const values = [INCLUDE_UPCOMING_VALUE]
        for (const season of [...seasons].reverse()) {
            spec[season.slug] = {label: season.name}
            values.push(season.slug)
        }
        return createSelectRegistry('DownloadProfileSeason', spec, values)
    }, [seasons])
    const seasonsBySlug = useMemo(
        () => new Map(seasons.map((season) => [season.slug, season])),
        [seasons],
    )

    // Build the select value from form state (multi select + special include option)
    const selectedSeasons: SeasonItem[] = watch('seasons') || []
    const selectedInclude: boolean = watch('includeUpcomingSeasons') || false

    const selectValue: UIOption[] = useMemo(() => {
        const selectedOptions = selectedSeasons
            .map((season) => seasonReg.options.find((option) => option.value === season.slug))
            .filter((option): option is UIOption => option !== undefined)
        const includeUpcomingOption = seasonReg.options.find(
            (option) => option.value === INCLUDE_UPCOMING_VALUE,
        )
        if (selectedInclude && includeUpcomingOption) selectedOptions.push(includeUpcomingOption)
        return selectedOptions
    }, [seasonReg, selectedInclude, selectedSeasons])

    // When the user changes the multiselect, persist SeasonItem[] to the form
    const handleSelectChange = (opts: readonly UIOption[] | null) => {
        const arr = Array.isArray(opts) ? [...opts] : []

        const include = arr.some((o) => o.value === INCLUDE_UPCOMING_VALUE)

        // Map chosen registry values back to the full SeasonItem objects saved by the form.
        const chosenSeasons: SeasonItem[] = arr
            .filter((option) => option.value !== INCLUDE_UPCOMING_VALUE)
            .map((option) => seasonsBySlug.get(option.value))
            .filter((season): season is SeasonItem => season !== undefined)

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
                            options={seasonReg.options}
                            value={selectValue}
                            onChange={handleSelectChange as any}
                            closeMenuOnSelect={false}
                            getOptionValue={(o: UIOption) => o.value}
                            getOptionLabel={(o: UIOption) => o.label}
                            aria-invalid={!!errors.seasons}
                            aria-describedby={errors.seasons ? 'profile-seasons-validate' : 'profile-seasons-help'}
                        />
                    )}
                />
                {errors.seasons && (
                    <div id="profile-seasons-validate" className="error" role="alert" aria-live="polite">
                        {errors.seasons.message as string}
                    </div>
                )}
                <div className="help" id="profile-seasons-help">
                    <ReadMore summary={<span>Which seasons to download</span>}>
                        Select which seasons to download. If you select "Include upcoming seasons", episodes from upcoming seasons
                        will be downloaded as they become available.
                    </ReadMore>
                </div>
            </div>
        </>
    )
}
