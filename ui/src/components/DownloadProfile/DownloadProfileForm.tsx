import {Controller, UseFormReturn} from 'react-hook-form'
import Switch from 'react-switch'
import ReadMore from '../../utils/ReadMore'
import PodcastDownloadProfileForm from './PodcastDownloadProfileForm'
import SeriesDownloadProfileForm, {SeasonItem} from './SeriesDownloadProfileForm'
import Select from "react-select";
import {EpisodeTypeReg} from "../../types/episode";
import {useMemo} from "react";

export type DownloadProfileMode = 'podcast' | 'series' | 'base'

type Props = {
    form: UseFormReturn<any>
    mode: DownloadProfileMode
    seasons?: SeasonItem[]
    profileMode?: 'create' | 'update'
    showRoot?: boolean
}

// Simple option model for react-select
type UIOption = { value: string; label: string }

export default function DownloadProfileForm({form, mode, seasons, showRoot}: Props) {
    const {control, watch, setValue, formState: {errors}} = form
    showRoot ??= true

    // Episode types multiselect wiring
    const selectedTypes: string[] = watch('epIdTypeList') || []
    const selectValue: UIOption[] = useMemo(() => (
        (selectedTypes || []).map((v) => ({ value: v, label: EpisodeTypeReg.getLabelLoose(v) }))
    ), [selectedTypes])

    const handleSelectChange = (opts: readonly UIOption[] | null) => {
        const arr = Array.isArray(opts) ? opts : []
        const values = arr.map((o) => o.value)
        setValue('epIdTypeList', values, {shouldDirty: true, shouldValidate: true})
    }

    const handleSelectAll = () => {
        setValue('epIdTypeList', [...EpisodeTypeReg.values], {shouldDirty: true, shouldValidate: true})
    }

    return (
        <>
            {showRoot && errors.root && (
                <div className="form-error-card" role="alert" aria-live="polite">
                    {String(errors.root.message)}
                </div>
            )}

            {/* Enable automatic downloads */}
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
                            aria-describedby={errors.enableProfile ? 'enable-profile-errors' : 'enable-profile-help'}
                        />
                    )}
                />
                {errors.enableProfile && (
                    <div id="enable-profile-errors" className="error" role="alert" aria-live="polite">
                        {errors.enableProfile.message as string}
                    </div>
                )}
                <div className="help" id="enable-profile-help">
                    <ReadMore summary={<span>Whether to automatically download episodes</span>}>
                        If you disable the download profile, the show will still be indexed and you can still manually
                        download episodes in the show.
                    </ReadMore>
                </div>
            </div>

            {/* Episode types to download */}
            <div className="form-row">
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                    <label htmlFor="ep-id-type-select">Episode types</label>
                    <div>
                        <button type="button" className="btn btn-link" onClick={handleSelectAll}>
                            Select all
                        </button>
                    </div>
                </div>
                <Controller
                    control={control}
                    name="epIdTypeList"
                    render={() => (
                        <Select
                            inputId="ep-id-type-select"
                            isMulti
                            options={EpisodeTypeReg.options}
                            value={selectValue}
                            onChange={handleSelectChange as any}
                            closeMenuOnSelect={false}
                            getOptionValue={(o: UIOption) => o.value}
                            getOptionLabel={(o: UIOption) => o.label}
                            aria-invalid={!!errors.epIdTypeList}
                            aria-describedby={errors.epIdTypeList ? 'ep-id-type-errors' : 'ep-id-type-help'}
                        />
                    )}
                />

                {errors.epIdTypeList && (
                    <div id="ep-id-type-errors" className="error" role="alert" aria-live="polite">
                        {errors.epIdTypeList.message as string}
                    </div>
                )}
                <div className="help" id="ep-id-type-help">
                    <ReadMore summary={<span>Whether to automatically download episodes</span>}>
                        If you disable the download profile, the show will still be indexed and you can still manually
                        download episodes in the show.
                    </ReadMore>
                </div>
            </div>

            {/* Variant-specific fields */}
            {mode === 'podcast' ? (
                <PodcastDownloadProfileForm form={form}/>
            ) : mode === 'series' ? (
                <SeriesDownloadProfileForm form={form} seasons={seasons ?? []}/>
            ) : undefined }
        </>
    )
}
