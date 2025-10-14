import {Controller, UseFormReturn} from 'react-hook-form'
import Switch from 'react-switch'
import ReadMore from '../../utils/ReadMore'
import PodcastDownloadProfileForm from './PodcastDownloadProfileForm'
import SeriesDownloadProfileForm, {SeasonItem} from './SeriesDownloadProfileForm'

export type DownloadProfileMode = 'podcast' | 'series' | 'base'

type Props = {
    form: UseFormReturn<any>
    mode: DownloadProfileMode
    seasons?: SeasonItem[]
    profileMode?: 'create' | 'update'
    showRoot?: boolean
}

export default function DownloadProfileForm({form, mode, seasons, showRoot}: Props) {
    const {control, formState: {errors}} = form
    showRoot ??= true

    return (
        <>
            {showRoot && errors.root && (
                <div className="form-error-card" role="alert" aria-live="polite">
                    {String(errors.root.message)}
                </div>
            )}

            {/* Common: Enable automatic downloads */}
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

            {/* Variant-specific fields */}
            {mode === 'podcast' ? (
                <PodcastDownloadProfileForm form={form}/>
            ) : mode === 'series' ? (
                <SeriesDownloadProfileForm form={form} seasons={seasons ?? []}/>
            ) : undefined }
        </>
    )
}
