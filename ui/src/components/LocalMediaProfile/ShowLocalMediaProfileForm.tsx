import {Controller, UseFormReturn} from 'react-hook-form'
import Select from 'react-select'

import {PreferredFormatReg, ShowLocalMediaProfileScopeReg} from '../../types/local_media_profile'
import LocalMediaProfileTypeFields from './LocalMediaProfileTypeFields'
import ReadMore from "../../utils/ReadMore";

export default function ShowLocalMediaProfileForm({form}: { form: UseFormReturn<any> }) {
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
            <LocalMediaProfileTypeFields
                form={form}
                mode="show"
                pathPlaceholder={'/downloads/shows/{{ show }}/{{ episode_title }}.ext'}
                formatRegistry={PreferredFormatReg}
                templateHelp={(
                    <>
                        <p>
                            Show, season, episode, and publication-date values are available. The editor's variable menu
                            lists every supported value and explains what it represents.
                        </p>
                        <p>
                            Conditional year example:<br/>
                            <code>{"{{ episode_title }}{% if year %} ({{ year }}){% endif %}.ext"}</code>
                        </p>
                        <p>
                            If a date, season, or another optional value is not known, it is an empty string. Use an
                            <b> if</b> block to omit any punctuation or folders that belong with it.
                        </p>
                    </>
                )}
            />
        </>
    )
}
