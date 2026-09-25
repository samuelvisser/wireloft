import {Controller, UseFormReturn} from 'react-hook-form'
import Select from 'react-select'

import {PreferredFormatReg, ShowLocalMediaProfileScopeReg} from '../../types/local_media_profile'
import ReadMore from '../../utils/ReadMore'
import LocalMediaProfilePreferredFormatField from './LocalMediaProfilePreferredFormatField'

export default function ShowLocalMediaProfileFields({form}: { form: UseFormReturn<any> }) {
    const {control, formState: {errors}} = form

    return (
        <>
            <div className="form-row">
                <label htmlFor="mp-show-scope">Available for</label>
                <Controller
                    control={control}
                    name="showScope"
                    render={({field}) => (
                        <Select
                            inputId="mp-show-scope"
                            classNamePrefix="select"
                            options={ShowLocalMediaProfileScopeReg.options}
                            value={ShowLocalMediaProfileScopeReg.options.find((option) => option.value === field.value) ?? null}
                            onChange={(option) => field.onChange((option as any)?.value ?? null)}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.showScope}
                            aria-describedby={errors.showScope ? 'mp-show-scope-error' : 'mp-show-scope-help'}
                            isClearable={false}
                        />
                    )}
                />
                {errors.showScope && (
                    <div id="mp-show-scope-error" className="error" role="alert" aria-live="polite">
                        {String(errors.showScope.message)}
                    </div>
                )}
                <div className="help" id="mp-show-scope-help">
                    <ReadMore summary={<span>Controls where this profile is offered within WireLoft</span>}>
                        <p>This will not change anything technical about this Local Media Profile, but acts as a filter where WireLoft shows this profile as an option</p>
                    </ReadMore>
                </div>
            </div>

            <LocalMediaProfilePreferredFormatField form={form} formatRegistry={PreferredFormatReg}/>
        </>
    )
}
