import type {ReactNode} from 'react'
import {Controller, UseFormReturn} from 'react-hook-form'
import Select from 'react-select'

type FormatRegistry = {
    options: readonly {value: string; label: string}[]
}

type Props = {
    form: UseFormReturn<any>
    pathPlaceholder: string
    formatRegistry: FormatRegistry
    templateHelp: ReactNode
}

export default function LocalMediaProfileTypeFields({
    form,
    pathPlaceholder,
    formatRegistry,
    templateHelp,
}: Props) {
    const {register, control, formState: {errors}} = form

    return (
        <>
            <div className="form-row">
                <label htmlFor="mp-path">Output path template</label>
                <input
                    id="mp-path"
                    className="input"
                    type="text"
                    placeholder={pathPlaceholder}
                    {...register('outputTemplate')}
                    aria-invalid={!!errors.outputTemplate}
                    aria-describedby={errors.outputTemplate ? 'mp-path-error' : 'mp-path-help'}
                />
                {errors.outputTemplate && (
                    <div id="mp-path-error" className="error" role="alert" aria-live="polite">
                        {String(errors.outputTemplate.message)}
                    </div>
                )}
                <div className="help" id="mp-path-help">{templateHelp}</div>
            </div>

            <div className="form-row">
                <label htmlFor="mp-format">Preferred format</label>
                <Controller
                    control={control}
                    name="preferredFormat"
                    render={({field}) => (
                        <Select
                            inputId="mp-format"
                            classNamePrefix="select"
                            options={formatRegistry.options}
                            value={formatRegistry.options.find((option) => option.value === field.value) ?? null}
                            onChange={(option) => field.onChange((option as any)?.value ?? null)}
                            onBlur={field.onBlur}
                            aria-invalid={!!errors.preferredFormat}
                            aria-describedby={errors.preferredFormat ? 'mp-format-error' : undefined}
                            isClearable={false}
                        />
                    )}
                />
                {errors.preferredFormat && (
                    <div id="mp-format-error" className="error" role="alert" aria-live="polite">
                        {String(errors.preferredFormat.message)}
                    </div>
                )}
            </div>
        </>
    )
}
