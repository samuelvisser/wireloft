import Switch from 'react-switch'
import {Controller, UseFormReturn} from 'react-hook-form'

type Props = {
    mode?: 'create' | 'update'
    form: UseFormReturn<any>
}

export default function MediaProfileForm({form}: Props) {

    const {register, control, formState: {errors}} = form;


    return (
        <>
            {errors.root && (
                <div className="form-error-card" role="alert" aria-live="polite">
                    {String(errors.root.message)}
                </div>
            )}


            <div className="form-row">
                <label htmlFor="mp-name">Name</label>
                <input
                    id="mp-name"
                    className="input"
                    type="text"
                    placeholder="My 4k Profile"
                    {...register('name')}
                    aria-invalid={!!errors.name}
                    aria-describedby={errors.name ? 'mp-name-validate' : undefined}
                />
                {(errors.name || errors.slug) && (
                    <div id="mp-name-validate" className="error" role="alert" aria-live="polite">
                        {String((errors.name ?? errors.slug)?.message)}
                    </div>
                )}
            </div>

            <div className="form-row">
                <label htmlFor="mp-path">Output path template</label>
                <input
                    id="mp-path"
                    className="input"
                    type="text"
                    placeholder="D:/Media/Shows/{show}/{season}"
                    {...register('outputTemplate')}
                    aria-invalid={!!errors.outputTemplate}
                    aria-describedby={errors.outputTemplate ? 'mp-path-error' : undefined}
                />
                {errors.outputTemplate && (
                    <div id="mp-path-error" className="error" role="alert" aria-live="polite">
                        {String(errors.outputTemplate.message)}
                    </div>
                )}
                <div className="help">Use placeholders like {`{show}`} and {`{season}`}.</div>
            </div>

            <div className="form-row">
                <label htmlFor="mp-format">Preferred format</label>
                <select
                    id="mp-format"
                    className="input"
                    {...register('preferredFormat')}
                    aria-invalid={!!errors.preferredFormat}
                    aria-describedby={errors.preferredFormat ? 'mp-format-error' : undefined}
                >
                    <option value="4k">4k</option>
                    <option value="1080p">1080p</option>
                    <option value="720p">720p</option>
                    <option value="audio_only">Audio Only</option>
                </select>
                {errors.preferredFormat && (
                    <div id="mp-format-error" className="error" role="alert" aria-live="polite">
                        {String(errors.preferredFormat.message)}
                    </div>
                )}
            </div>

            <div className="form-row" style={{alignItems: 'center'}}>
                <label htmlFor="mp-images">Download series images</label>
                <Controller
                    control={control}
                    name="downloadSeriesImages"
                    render={({field: {value: checked, onChange: setChecked}}) => (
                        <Switch
                            id="mp-images"
                            checked={!!checked}
                            onChange={setChecked}
                            onColor="#0ea5e9"
                            offColor="#d1d5db"
                            uncheckedIcon={false}
                            checkedIcon={false}
                        />
                    )}
                />
                {errors.downloadSeriesImages && (
                    <div id="mp-download-images-error" className="error" role="alert" aria-live="polite">
                        {String(errors.downloadSeriesImages.message)}
                    </div>
                )}
            </div>
        </>
    )
}
