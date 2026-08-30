import type {ReactNode} from 'react'
import {Controller, UseFormReturn} from 'react-hook-form'
import Select from 'react-select'
import type {LocalMediaProfileMode} from './LocalMediaProfileForm'
import OutputTemplateEditor from './OutputTemplateEditor'

type FormatRegistry = {
    options: readonly { value: string; label: string }[]
}

type Props = {
    form: UseFormReturn<any>
    mode: LocalMediaProfileMode
    pathPlaceholder: string
    formatRegistry: FormatRegistry
    templateHelp: ReactNode
}

export default function LocalMediaProfileTypeFields({
                                                        form,
                                                        mode,
                                                        pathPlaceholder,
                                                        formatRegistry,
                                                        templateHelp,
                                                    }: Props) {
    const {control, formState: {errors}} = form

    return (
        <>
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
            <OutputTemplateEditor
                form={form}
                mode={mode}
                placeholder={pathPlaceholder}
                help={templateHelp}
            />
        </>
    )
}
