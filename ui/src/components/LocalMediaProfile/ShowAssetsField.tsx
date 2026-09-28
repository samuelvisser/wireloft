import {Controller, type UseFormReturn} from 'react-hook-form'
import Select from 'react-select'

import type {LocalMediaProfilePreviewState} from '../../lib/localMediaProfilePreview'
import ReadMore from "../../utils/ReadMore";

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
    const showRootSummary = preview.error
        ? preview.error
        : root?.path
            ? root.path
            : root?.reason
                ? root.reason
                : preview.loading
                    ? 'Resolving show root...'
                    : 'Select an episode and enter an output template to preview the shared show root.'


    return (
        <div className="form-row">
            <label htmlFor="mp-show-assets">Download show images</label>
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
                <ReadMore summary={<>
                    Save show assets to show root: <code style={{overflowWrap: 'anywhere'}}>{showRootSummary}</code>
                </>}>
                    <p>
                        Save available poster, background and square artwork in the show root folder. This
                        is particularly useful if you consume the show through a media server.
                    </p>
                    <p>
                        <strong>System</strong> follows the current system-wide default shown in parentheses.
                    </p>
                    <p>
                        <strong>Enabled</strong> downloads show assets to show root folder.
                    </p>
                    <p>
                        <strong>Disabled</strong> does not download show assets.
                    </p>
                    <p>
                        Existing custom artwork is preserved.
                    </p>
                    <p>
                        WireLoft dynamically tries to resolve the root folder for your show. This resolver is very powerful
                        and takes into account even conditional Jinja paths. To make sure WireLoft actually finds your show
                        root folder correctly, select any episode in the 'example source' below, and the path above will automatically
                        show you what WireLoft resolved as your show root, without changing any files or saving anything yet.
                    </p>
                    <p>
                        If the show root WireLoft found is not correct, this is likely due to an ambiguous path in your output
                        template. Please review it below.
                    </p>
                </ReadMore>
            </div>
        </div>
    )
}
