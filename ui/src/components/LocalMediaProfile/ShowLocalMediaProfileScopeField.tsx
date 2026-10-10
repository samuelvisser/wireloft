import {Controller, type UseFormReturn} from 'react-hook-form'

import {ShowLocalMediaProfileScopeReg, type ShowLocalMediaProfileScope} from '../../types/local_media_profile'
import ReadMore from '../../utils/ReadMore'
import SimpleSelect from '../common/SimpleSelect'

export default function ShowLocalMediaProfileScopeField({
    form,
    onScopeChange,
}: {
    form: UseFormReturn<any>
    onScopeChange: (scope: ShowLocalMediaProfileScope) => void
}) {
    const {control, formState: {errors}} = form

    return (
        <div className="form-row">
            <label htmlFor="mp-show-scope">Available for</label>
            <Controller
                control={control}
                name="showScope"
                render={({field}) => (
                    <SimpleSelect
                        inputId="mp-show-scope"
                        registry={ShowLocalMediaProfileScopeReg}
                        value={field.value ?? 'both'}
                        onChange={(value) => {
                            const nextScope = value as ShowLocalMediaProfileScope
                            // Let the defaulting logic read the previous scope before
                            // updating the form with the new one.
                            onScopeChange(nextScope)
                            field.onChange(nextScope)
                        }}
                        onBlur={field.onBlur}
                        aria-invalid={!!errors.showScope}
                        aria-describedby={errors.showScope ? 'mp-show-scope-error' : 'mp-show-scope-help'}
                    />
                )}
            />
            {errors.showScope && (
                <div id="mp-show-scope-error" className="error" role="alert" aria-live="polite">
                    {String(errors.showScope.message)}
                </div>
            )}
            <div className="help" id="mp-show-scope-help">
                <ReadMore summary="Controls where this profile is available and its initial subtitle behavior.">
                    <p>Podcast-only profiles default to no subtitles. Series and mixed profiles default to downloading subtitles beside the media.</p>
                    <p>Changing this selection adjusts the subtitle default only until you explicitly choose a subtitle option.</p>
                </ReadMore>
            </div>
        </div>
    )
}
