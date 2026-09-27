import {Controller, type UseFormReturn} from 'react-hook-form'
import Select from 'react-select'

import type {LocalMediaProfilePreviewState} from '../../lib/localMediaProfilePreview'

export default function ShowAssetsField({form, preview}: {
    form: UseFormReturn<any>
    preview: LocalMediaProfilePreviewState
}) {
    const {control, formState: {errors}} = form
    const root = preview.result?.showRoot
    const options = [
        {value: 'system', label: root ? `System (${root.systemEnabled ? 'enabled' : 'disabled'})` : 'System'},
        {value: 'enabled', label: 'Enabled'},
        {value: 'disabled', label: 'Disabled'},
    ]
    const fieldError = errors.downloadShowAssets

    return (
        <div className="form-row">
            <label htmlFor="mp-show-assets">Download show assets</label>
            <Controller
                control={control}
                name="downloadShowAssets"
                render={({field}) => (
                    <Select
                        inputId="mp-show-assets"
                        ref={field.ref}
                        name={field.name}
                        classNamePrefix="select"
                        options={options}
                        value={options.find(({value}) => value === (field.value == null ? 'system' : field.value ? 'enabled' : 'disabled'))}
                        onChange={(option) => field.onChange(option?.value === 'enabled' ? true : option?.value === 'disabled' ? false : null)}
                        onBlur={field.onBlur}
                        isClearable={false}
                        aria-invalid={!!fieldError}
                        aria-describedby={`mp-show-assets-help${fieldError ? ' mp-show-assets-error' : ''}`}
                    />
                )}
            />
            {fieldError && <div id="mp-show-assets-error" className="error" role="alert">{String(fieldError.message)}</div>}
            <div id="mp-show-assets-help" className="help">
                <p>
                    Save available poster, background and square artwork in the shared show folder.
                    System inherits Settings / Downloads. Episode thumbnails are controlled separately.
                    Existing custom artwork is preserved.
                </p>
                <div role="status" aria-live="polite">
                    {preview.loading ? 'Resolving show root...' : preview.error || (root?.path ? (
                        <>
                            Resolved show root{root.showTitle ? ` for ${root.showTitle}` : ''}:<br/>
                            <code style={{overflowWrap: 'anywhere'}}>{root.path}</code>
                        </>
                    ) : root?.reason ?? 'Select an episode and enter an output template to preview the shared show root.')}
                </div>
                <p>
                    Uses the same selected example and editable test values as the episode path,
                    including unsaved template changes. Previewing does not change saved metadata or files.
                    Ambiguous or shared library folders are skipped.
                </p>
            </div>
        </div>
    )
}
